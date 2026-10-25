"""The deployment of a release to production (scripts/deploy.sh), and its rehearsal on a throwaway stack, in throwaway
installations (installation_support.py) whose production api is a fake that reports its health.

Needs git, bash, curl, flock and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_deploy.py'
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sqlite3
import unittest
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, NamedTuple

from docker_shim import LoggedCall, Rule
from installation_support import (
    BOUNDED_ENGINE_CHECK,
    COPIED,
    ENGINE_CHECK,
    ENGINE_CHECK_MODULE,
    PRODUCTION_ENGINE_CHECK_STEPS,
    SANDBOX_OUTPUT,
    SANDBOX_TEXTS,
    TIMED_OUT_STATUS,
    VERSION,
    Installation,
    InstallationTestCase,
    ScriptRun,
    build_production_container_rules,
    build_running_sandbox_rules,
    find_free_port,
    list_writing_calls,
    make_installation,
    read_gradle_tasks,
    read_text_if_present,
    start_fake_api,
)


class Tags(NamedTuple):
    checkout: str
    origin: tuple[str, ...]


@dataclass(frozen=True)
class BrokenPrecondition:
    break_it: Callable[[Installation], None]
    refusal: str


RELEASE_TAGS_ALONE = Tags(f"v{VERSION}\n", (f"refs/tags/v{VERSION}", f"refs/tags/v{VERSION}^{{}}"))
REHEARSAL_PROJECT = "scanmylib-review-test"
REHEARSAL_ENVIRONMENT = MappingProxyType({"SCANMYLIB_DEPLOY_REHEARSAL": REHEARSAL_PROJECT})
REHEARSED_APP_VERSION = "0.2.4-dev+g1a2b3c4d5e6f.dirty"
RUNNING_IMAGES_TAGGED_DEPLOYED: list[Rule] = [
    {"match": r"^image inspect --format \{\{\.Id\}\} scanmylib-(api|ocr):deployed$", "stdout": "sha256:good\n"},
    {"match": r"^inspect --format \{\{\.Image\}\} (api|ocr)id$", "stdout": "sha256:good\n"},
]


def build_running_images_never_tagged_deployed() -> list[Rule]:
    rules: list[Rule] = []
    for service in ("api", "ocr"):
        rules += [
            {
                "match": rf"^ps --all --quiet --filter label=com\.docker\.compose\.project=scanmylib "
                rf"--filter label=com\.docker\.compose\.service={service} "
                rf"--filter label=com\.docker\.compose\.oneoff=False$",
                "stdout": f"{service}id\n",
            },
            {"match": rf"^inspect --format \{{\{{\.Image\}}\}} {service}id$", "stdout": f"sha256:old{service}\n"},
            {
                "match": rf"^image inspect --format \{{\{{\.Id\}}\}} scanmylib-{service}:latest$",
                "stdout": f"sha256:old{service}\n",
            },
        ]
    return rules


def deploy(
    installation: Installation,
    *arguments: str,
    rules: list[Rule] | None = None,
    checkout: Path | None = None,
) -> ScriptRun:
    production_data = installation.production_data
    sandbox = build_running_sandbox_rules(f"{production_data}/sandbox", str(production_data))
    installation.answer_docker((rules or []) + build_running_images_never_tagged_deployed() + sandbox)
    return installation.run_script(
        checkout or installation.production_checkout, "deploy.sh", *arguments, timeout_seconds=120
    )


def list_backups(installation: Installation) -> list[str]:
    directory = installation.production_data / "backups"
    return sorted(entry.name for entry in directory.iterdir()) if directory.exists() else []


def read_tags(installation: Installation) -> Tags:
    checkout = installation.production_checkout
    origin_tags = installation.run_git(checkout, "ls-remote", "--tags", "origin").splitlines()
    return Tags(installation.run_git(checkout, "tag"), tuple(line.split("\t")[1] for line in origin_tags))


def read_documents(database_path: Path) -> list[tuple[str, ...]] | None:
    if not database_path.exists():
        return None
    with closing(sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)) as database:
        documents: list[tuple[str, ...]] = database.execute("SELECT id FROM documents").fetchall()
        return documents


def read_logs(installation: Installation) -> list[str]:
    logs = installation.production_data / "logs"
    return [log.read_text() for log in logs.iterdir()] if logs.exists() else []


def find_command(commands: list[str], fragment: str) -> str:
    """The first of `commands` that holds `fragment`: raises StopIteration when none does, so that a test of a command
    that never ran fails rather than finds nothing wrong with it."""
    return next(command for command in commands if fragment in command)


def read_option_value(command: str, option: str) -> str:
    return "".join(command.partition(f"{option} ")[2].split()[:1])


def replace_once(text: str, old: str, new: str) -> str:
    """`text` with its first `old` replaced by `new`: refuses a text without `old`, which the change would leave as
    it is."""
    if old not in text:
        raise ValueError(f"{old!r} is not in the text to change")
    return text.replace(old, new, 1)


def write_rehearsal_env(installation: Installation, rehearsal_data: Path, api_port: int) -> None:
    (installation.worktree / ".env").write_text(
        installation.build_development_env(
            COMPOSE_PROJECT_NAME=REHEARSAL_PROJECT,
            IMAGE_PREFIX=REHEARSAL_PROJECT,
            DATA_DIR=str(rehearsal_data),
            LIBRARY_DIR=f"{rehearsal_data}/library",
            ANDROID_DIR=f"{rehearsal_data}/android",
            API_PORT=str(api_port),
        )
    )


def prepare_rehearsal(installation: Installation, api_port: int, export_copy: Path) -> None:
    rehearsal_data = installation.directory / "rehearsal"
    write_rehearsal_env(installation, rehearsal_data, api_port)
    compose = installation.worktree / "compose.yaml"
    compose.write_text(compose.read_text() + "# uncommitted\n")
    (installation.worktree / "untracked.txt").write_text("x")
    installation.answer_docker(
        [
            {"match": r"^compose .* build api ocr$", "snapshot": str(export_copy)},
            *build_running_sandbox_rules(
                f"{installation.production_data}/sandbox", str(rehearsal_data), kind="ocr-fake"
            ),
        ]
    )
    # The rehearsal publishes the dev app, a development build, whose metadata the stand-in leaves to the test.
    (rehearsal_data / "app").mkdir(parents=True)
    (rehearsal_data / "app" / "scanmylib.json").write_text(json.dumps({"version_name": REHEARSED_APP_VERSION}))


def commit_rehearsal(installation: Installation, compose_text: str) -> None:
    write_rehearsal_env(installation, installation.directory / "rehearsal", find_free_port())
    (installation.worktree / "compose.yaml").write_text(compose_text)
    installation.run_git(installation.worktree, "add", "--all")
    installation.run_git(installation.worktree, "commit", "--quiet", "--message", "Relative paths in compose.yaml")


def rehearse(installation: Installation, *arguments: str) -> ScriptRun:
    return installation.run_script(
        installation.worktree,
        "deploy.sh",
        "--first-install",
        *arguments,
        timeout_seconds=120,
        environment=REHEARSAL_ENVIRONMENT,
    )


def remove_the_database(installation: Installation) -> None:
    (installation.production_data / "state" / "scanmylib.db").unlink()


def write_a_comment_in_env(installation: Installation) -> None:
    env = installation.build_production_env(DATA_DIR=f"{installation.production_data} # data")
    (installation.production_checkout / ".env").write_text(env)


def move_the_library_away(installation: Installation) -> None:
    env = installation.build_production_env(LIBRARY_DIR=f"{installation.directory}/missing")
    (installation.production_checkout / ".env").write_text(env)


def write_a_development_env(installation: Installation) -> None:
    env = installation.build_production_env(COMPOSE_PROJECT_NAME="scanmylib-dev")
    (installation.production_checkout / ".env").write_text(env)


def empty_the_env(installation: Installation) -> None:
    (installation.production_checkout / ".env").write_text("# nothing\n")


def remove_the_sandbox_manifest(installation: Installation) -> None:
    (installation.production_data / "sandbox" / "MANIFEST.json").unlink()


class WhenItIsADryRun(InstallationTestCase):
    production_checkout: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]
    api_request_count: ClassVar[int]
    backups: ClassVar[list[str]]
    is_log_written: ClassVar[bool]
    tags: ClassVar[Tags]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        cls.production_checkout = installation.production_checkout
        cls.deploy_run = deploy(installation, "--dry-run", "--apk")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())
        cls.api_request_count = api.request_count
        cls.backups = list_backups(installation)
        cls.is_log_written = (installation.production_data / "logs").exists()
        cls.tags = read_tags(installation)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_say_that_it_changed_nothing(self) -> None:
        self.assertIn("Dry run: nothing was changed.", self.deploy_run.stdout)

    def test_should_name_production_s_checkout(self) -> None:
        self.assertIn(f"production's checkout ({self.production_checkout})", self.deploy_run.stdout)

    def test_should_check_the_release_as_published_on_origin(self) -> None:
        self.assertIn(f"the release v{VERSION}, as published on origin", self.deploy_run.stdout)

    def test_should_check_that_production_holds_the_database(self) -> None:
        self.assertIn("holds the database", self.deploy_run.stdout)

    def test_should_say_which_images_it_would_tag_deployed(self) -> None:
        self.assertIn("would run: docker tag sha256:oldapi scanmylib-api:deployed", self.deploy_run.stdout)

    def test_should_say_that_it_would_check_the_engine_s_environment_bounded_in_time_and_without_its_output(
        self,
    ) -> None:
        self.assertRegex(
            self.deploy_run.stdout,
            rf"would run: timeout --kill-after=10 \d+ docker exec <the ocr container> python3 -m "
            rf"{re.escape(ENGINE_CHECK_MODULE)}, its output discarded",
        )

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])

    def test_should_send_no_request_to_the_api(self) -> None:
        self.assertEqual(self.api_request_count, 0)

    def test_should_back_up_nothing(self) -> None:
        self.assertEqual(self.backups, [])

    def test_should_write_no_log(self) -> None:
        self.assertFalse(self.is_log_written)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)


class WhenTheReleaseIsDeployedWithTheApp(InstallationTestCase):
    temporary_directory: ClassVar[Path]
    production_checkout: ClassVar[Path]
    production_data: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    gradle_tasks: ClassVar[list[str]]
    temporary_entries: ClassVar[list[str]]
    built_files: ClassVar[list[str]]
    backups: ClassVar[list[str]]
    backed_up_files: ClassVar[dict[str, list[str]]]
    backed_up_documents: ClassVar[dict[str, list[tuple[str, ...]] | None]]
    tags: ClassVar[Tags]
    logs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.temporary_directory = installation.directory
        cls.production_checkout = installation.production_checkout
        cls.production_data = installation.production_data
        export_copy = installation.directory / "built"
        cls.deploy_run = deploy(
            installation, "--apk", rules=[{"match": r"^compose .* build api ocr$", "snapshot": str(export_copy)}]
        )
        cls.commands = installation.read_docker_commands()
        cls.gradle_tasks = read_gradle_tasks(installation.read_docker_calls())
        cls.temporary_entries = sorted(path.name for path in installation.directory.iterdir())
        built_paths = [path for path in export_copy.rglob("*") if path.is_file()]
        cls.built_files = sorted(str(path.relative_to(export_copy)) for path in built_paths)
        cls.backups = list_backups(installation)
        backups = installation.production_data / "backups"
        cls.backed_up_files = {name: sorted(path.name for path in (backups / name).iterdir()) for name in cls.backups}
        cls.backed_up_documents = {name: read_documents(backups / name / "scanmylib.db") for name in cls.backups}
        cls.tags = read_tags(installation)
        cls.logs = read_logs(installation)

    def find_build(self) -> str:
        return find_command([command for command in self.commands if command.startswith("compose")], " build api ocr")

    def find_export(self) -> Path:
        return Path(read_option_value(self.find_build(), "--project-directory"))

    def find_command_index(self, fragment: str) -> int:
        return self.commands.index(find_command(self.commands, fragment))

    def find_isolation_check_indexes(self) -> list[int]:
        return [
            index
            for index, command in enumerate(self.commands)
            if command.startswith("exec ") and command != ENGINE_CHECK
        ]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_build_an_export_in_the_temporary_directory(self) -> None:
        self.assertTrue(
            str(self.find_export()).startswith(f"{self.temporary_directory}/scanmylib-deploy."), self.find_build()
        )

    def test_should_remove_the_export(self) -> None:
        export = self.find_export()
        self.assertEqual(export.parent, self.temporary_directory)
        self.assertNotIn(export.name, self.temporary_entries)

    def test_should_export_the_commit_without_env(self) -> None:
        self.assertEqual(self.built_files, sorted(COPIED))

    def test_should_build_with_production_s_env(self) -> None:
        self.assertIn(f"--env-file {self.production_checkout}/.env", self.find_build())

    def test_should_build_an_api_that_reports_the_version_of_the_release(self) -> None:
        self.assertNotIn("DEV_VERSION", self.find_build())

    def test_should_run_no_test_suite_since_the_release_was_tested_before_it_was_published(self) -> None:
        before_the_restart = self.commands[: self.find_command_index(" up -d --no-build --wait")]
        containers_and_image_builds = [
            command for command in before_the_restart if command.startswith(("run ", "build "))
        ]
        self.assertIn(self.find_build(), before_the_restart)
        self.assertEqual(containers_and_image_builds, [])

    def test_should_build_the_release_app_without_its_tests_and_lint_since_ci_ran_them_on_the_release(self) -> None:
        self.assertEqual(self.gradle_tasks, ["assembleRelease"])

    def test_should_start_production_from_its_checkout_with_the_compose_yaml_of_the_commit(self) -> None:
        up = find_command(self.commands, " up -d --no-build --wait")
        self.assertIn(f"--project-directory {self.production_checkout} --file {self.find_export()}/compose.yaml ", up)

    def test_should_run_every_compose_command_with_the_compose_yaml_of_the_commit(self) -> None:
        compose_commands = [command for command in self.commands if command.startswith("compose")]
        export = self.find_export()
        self.assertNotEqual(compose_commands, [])
        for command in compose_commands:
            with self.subTest(command):
                self.assertIn(f"--file {export}/compose.yaml ", command)

    def test_should_print_its_commands_as_those_of_prod_sh(self) -> None:
        self.assertIn("$ scripts/prod.sh compose up -d --no-build", self.deploy_run.stdout)

    def test_should_never_print_plain_docker_compose(self) -> None:
        self.assertNotIn("$ docker compose", self.deploy_run.stdout)

    def test_should_sign_the_app_with_production_s_key_read_only(self) -> None:
        sign = find_command(self.commands, "scanmylib-android-sign")
        self.assertIn(f"{self.production_data}/android/keystore:/keystore:ro", sign)

    def test_should_have_the_signer_refuse_any_other_app_than_the_production_app(self) -> None:
        self.assertIn("EXPECTED_PACKAGE=fr.scanmylib ", find_command(self.commands, "scanmylib-android-sign"))

    def test_should_back_up_the_state_once(self) -> None:
        self.assertEqual(len(self.backups), 1)

    def test_should_name_the_backup_after_its_time_and_the_release(self) -> None:
        self.assertRegex(self.backups[0], rf"^state-\d{{8}}-\d{{6}}\.\d+-v{VERSION}$")

    def test_should_back_up_the_database_and_the_token_not_the_thumbnails(self) -> None:
        self.assertEqual(self.backed_up_files[self.backups[0]], ["scanmylib.db", "token"])

    def test_should_back_up_the_documents_of_the_database(self) -> None:
        self.assertEqual(self.backed_up_documents[self.backups[0]], [("d1",)])

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)

    def test_should_tag_deployed_the_api_image_that_ran_before_the_build(self) -> None:
        tag_index = self.commands.index("tag sha256:oldapi scanmylib-api:deployed")
        self.assertLess(tag_index, self.commands.index(self.find_build()))

    def test_should_tag_deployed_the_sandbox_image_that_ran_before_the_build(self) -> None:
        tag_index = self.commands.index("tag sha256:oldocr scanmylib-ocr:deployed")
        self.assertLess(tag_index, self.commands.index(self.find_build()))

    def test_should_tag_the_new_api_image_deployed_once(self) -> None:
        self.assertEqual(self.commands.count("tag scanmylib-api:latest scanmylib-api:deployed"), 1)

    def test_should_tag_the_new_images_deployed_once_they_pass_the_isolation_check(self) -> None:
        last_check_index = max(self.find_isolation_check_indexes())
        tag_index = self.commands.index("tag scanmylib-api:latest scanmylib-api:deployed")
        self.assertGreater(tag_index, last_check_index)

    def test_should_check_the_engine_s_environment_in_the_new_sandbox(self) -> None:
        self.assertIn(ENGINE_CHECK, self.commands)

    def test_should_show_that_it_bounds_the_check_of_the_engine_s_environment_in_time(self) -> None:
        self.assertRegex(self.deploy_run.stdout, BOUNDED_ENGINE_CHECK)

    def test_should_check_the_engine_only_once_the_sandbox_passed_the_isolation_check(self) -> None:
        self.assertGreater(self.commands.index(ENGINE_CHECK), max(self.find_isolation_check_indexes()))

    def test_should_tag_the_new_images_deployed_once_the_engine_s_environment_passed(self) -> None:
        tag_indexes = [
            self.commands.index(f"tag scanmylib-{service}:latest scanmylib-{service}:deployed")
            for service in ("api", "ocr")
        ]
        self.assertGreater(min(tag_indexes), self.commands.index(ENGINE_CHECK))

    def test_should_tag_the_new_images_deployed_before_the_app_is_built(self) -> None:
        app_build_index = min(
            index for index, command in enumerate(self.commands) if "scanmylib-android-build" in command
        )
        tag_index = self.commands.index("tag scanmylib-api:latest scanmylib-api:deployed")
        self.assertLess(tag_index, app_build_index)

    def test_should_tag_the_new_sandbox_image_deployed_once_it_runs(self) -> None:
        up_index = self.find_command_index(" up -d --no-build --wait")
        self.assertIn("tag scanmylib-ocr:latest scanmylib-ocr:deployed", self.commands[up_index:])

    def test_should_write_one_log(self) -> None:
        self.assertEqual(len(self.logs), 1)

    def test_should_log_the_release_it_deployed(self) -> None:
        self.assertIn(f"Deployed scanmylib {VERSION}", self.logs[0])


class WhenLatestWasRebuiltSinceTheContainersStarted(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        rebuilt_latest: list[Rule] = [
            {"match": r"^image inspect --format \{\{\.Id\}\} scanmylib-api:latest$", "stdout": "sha256:newer\n"}
        ]
        cls.deploy_run = deploy(installation, "--dry-run", rules=rebuilt_latest)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_say_that_latest_is_not_the_image_that_runs(self) -> None:
        self.assertIn("scanmylib-api:latest (sha256:newer) is not the image api runs", self.deploy_run.stdout)

    def test_should_tag_deployed_the_image_that_the_containers_run(self) -> None:
        self.assertIn("would run: docker tag sha256:oldapi scanmylib-api:deployed", self.deploy_run.stdout)


class WhenTheBuildFails(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    backups: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.deploy_run = deploy(installation, rules=[{"match": r"^compose .* build api ocr$", "exit": 1}])
        cls.commands = installation.read_docker_commands()
        cls.backups = list_backups(installation)

    def test_should_fail_at_the_images(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "images"', self.deploy_run.stdout)

    def test_should_say_that_production_is_unchanged(self) -> None:
        self.assertIn("Production is unchanged", self.deploy_run.stdout)

    def test_should_tag_latest_the_images_that_production_runs_again(self) -> None:
        self.assertIn("tag scanmylib-api:deployed scanmylib-api:latest", self.commands)
        self.assertIn("tag scanmylib-ocr:deployed scanmylib-ocr:latest", self.commands)

    def test_should_start_nothing(self) -> None:
        self.assertEqual([command for command in self.commands if " up " in command], [])

    def test_should_back_up_nothing(self) -> None:
        self.assertEqual(self.backups, [])


class WhenTheBackupFails(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    backups: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        not_a_database = b"not a database\n" * 100
        (installation.production_data / "state" / "scanmylib.db").write_bytes(not_a_database)
        cls.deploy_run = deploy(installation)
        cls.commands = installation.read_docker_commands()
        cls.backups = list_backups(installation)

    def test_should_fail_at_the_backup(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "backup"', self.deploy_run.stdout)

    def test_should_say_that_production_is_unchanged(self) -> None:
        self.assertIn("Production is unchanged", self.deploy_run.stdout)

    def test_should_tag_latest_the_images_that_production_runs_again(self) -> None:
        self.assertIn("tag scanmylib-api:deployed scanmylib-api:latest", self.commands)
        self.assertIn("tag scanmylib-ocr:deployed scanmylib-ocr:latest", self.commands)

    def test_should_start_nothing(self) -> None:
        self.assertEqual([command for command in self.commands if " up " in command], [])

    def test_should_leave_no_backup_and_no_partial_one(self) -> None:
        self.assertEqual(self.backups, [])


class WhenTheApiReportsAnotherVersionAfterTheRestart(InstallationTestCase):
    production_data: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    backups: ClassVar[list[str]]
    tags: ClassVar[Tags]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        cls.production_data = installation.production_data
        api.version = "0.0.1"
        cls.deploy_run = deploy(installation)
        cls.commands = installation.read_docker_commands()
        cls.backups = list_backups(installation)
        cls.tags = read_tags(installation)

    def test_should_fail_at_the_restart(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "restart"', self.deploy_run.stdout)

    def test_should_have_backed_up_the_state_once(self) -> None:
        self.assertEqual(len(self.backups), 1)

    def test_should_say_how_to_tag_latest_the_images_that_production_ran(self) -> None:
        self.assertIn("docker tag scanmylib-api:deployed scanmylib-api:latest", self.deploy_run.stdout)

    def test_should_say_how_to_restart_them_with_prod_sh(self) -> None:
        rollback = self.deploy_run.stdout.split("DEPLOY FAILED", 1)[1]
        self.assertIn("scripts/prod.sh compose up -d --no-build api ocr", rollback)

    def test_should_never_say_to_run_plain_docker_compose(self) -> None:
        rollback = self.deploy_run.stdout.split("DEPLOY FAILED", 1)[1]
        self.assertNotIn("docker compose", rollback)

    def test_should_say_how_to_restore_the_backup(self) -> None:
        backup = f"{self.production_data}/backups/{self.backups[0]}"
        self.assertIn(f"cp -a {backup} {self.production_data}/state", self.deploy_run.stdout)

    def test_should_say_how_to_set_the_failed_state_aside(self) -> None:
        production_data = self.production_data
        self.assertIn(f"mv {production_data}/state {production_data}/state.failed-", self.deploy_run.stdout)

    def test_should_never_tag_the_new_images_deployed(self) -> None:
        self.assertNotIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)


class WhenDeployedNamesWhatRunsAndTheRestartFails(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        api.version = "0.0.1"
        cls.deploy_run = deploy(installation, rules=RUNNING_IMAGES_TAGGED_DEPLOYED)
        cls.commands = installation.read_docker_commands()

    def test_should_fail_at_the_restart(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "restart"', self.deploy_run.stdout)

    def test_should_keep_deployed_on_the_images_that_ran_for_a_rollback(self) -> None:
        self.assertNotIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands)

    def test_should_tag_no_image_by_its_id(self) -> None:
        self.assertEqual([command for command in self.commands if command.startswith("tag sha256:")], [])

    def test_should_say_how_to_tag_latest_the_images_that_ran(self) -> None:
        self.assertIn("docker tag scanmylib-api:deployed scanmylib-api:latest", self.deploy_run.stdout)


class WhenDeployedNamesWhatRunsAndADeploySucceedsAfterAFailedOne(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        api.version = "0.0.1"
        deploy(installation, rules=RUNNING_IMAGES_TAGGED_DEPLOYED)
        installation.forget_docker_calls()
        api.version = VERSION
        cls.deploy_run = deploy(installation, rules=RUNNING_IMAGES_TAGGED_DEPLOYED)
        cls.commands = installation.read_docker_commands()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_tag_the_new_api_image_deployed_once(self) -> None:
        self.assertEqual(self.commands.count("tag scanmylib-api:latest scanmylib-api:deployed"), 1)

    def test_should_tag_the_new_images_deployed_only_once_they_run(self) -> None:
        up_index = self.commands.index(find_command(self.commands, " up -d --no-build"))
        self.assertGreater(self.commands.index("tag scanmylib-api:latest scanmylib-api:deployed"), up_index)


class WhenDeployedLagsBehindWhatRuns(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        # A deploy failed once the containers ran the new images, and :deployed still names the previous ones.
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        lagging: list[Rule] = [
            {
                "match": r"^image inspect --format \{\{\.Id\}\} scanmylib-(api|ocr):deployed$",
                "stdout": "sha256:older\n",
            },
            {"match": r"^compose .* build api ocr$", "exit": 1},
        ]
        cls.deploy_run = deploy(installation, rules=lagging)
        cls.commands = installation.read_docker_commands()

    def test_should_fail_at_the_images(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "images"', self.deploy_run.stdout)

    def test_should_warn_that_deployed_is_not_what_runs(self) -> None:
        self.assertIn(
            "warn  scanmylib-api:deployed (sha256:older) is not the image api runs (sha256:oldapi)",
            self.deploy_run.stdout,
        )

    def test_should_tag_deployed_what_runs_before_the_build_since_it_is_the_truth_to_roll_back_to(self) -> None:
        build_index = self.commands.index(find_command(self.commands, " build api ocr"))
        self.assertLess(self.commands.index("tag sha256:oldapi scanmylib-api:deployed"), build_index)

    def test_should_roll_back_to_what_ran(self) -> None:
        self.assertGreater(
            self.commands.index("tag scanmylib-api:deployed scanmylib-api:latest"),
            self.commands.index("tag sha256:oldapi scanmylib-api:deployed"),
        )


class WhenTheAppFailsToBuild(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    tags: ClassVar[Tags]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.deploy_run = deploy(installation, "--apk", rules=[{"match": "^run .*scanmylib-android-build", "exit": 1}])
        cls.commands = installation.read_docker_commands()
        cls.tags = read_tags(installation)

    def test_should_fail_at_the_app(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "apk"', self.deploy_run.stdout)

    def test_should_say_that_the_images_production_runs_are_tagged_deployed(self) -> None:
        self.assertIn("its images tagged :deployed", self.deploy_run.stdout)

    def test_should_have_tagged_the_new_images_deployed_since_they_run(self) -> None:
        self.assertIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)


class WhenTheApiDoesNotOfferTheNewApp(InstallationTestCase):
    offered_apps: ClassVar[Mapping[str, str | None]] = MappingProxyType({"no app": None, "an older app": "0.0.1"})
    deploy_runs: ClassVar[dict[str, ScriptRun]]
    tags: ClassVar[dict[str, Tags]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        cls.deploy_runs, cls.tags = {}, {}
        for row, apk_version in cls.offered_apps.items():
            installation.forget_docker_calls()
            api.apk_version = apk_version
            cls.deploy_runs[row] = deploy(installation, "--apk")
            cls.tags[row] = read_tags(installation)

    def test_should_fail_at_the_app(self) -> None:
        self.assertEqual(sorted(self.deploy_runs), sorted(self.offered_apps))
        for row, deploy_run in self.deploy_runs.items():
            with self.subTest(row):
                self.assertNotEqual(deploy_run.returncode, 0)
                self.assertIn('DEPLOY FAILED during the step "apk"', deploy_run.stdout)

    def test_should_say_which_app_the_api_offers(self) -> None:
        self.assertEqual(sorted(self.deploy_runs), sorted(self.offered_apps))
        for row, deploy_run in self.deploy_runs.items():
            with self.subTest(row):
                offered = f"the api offers the APK '{self.offered_apps[row]}', not {VERSION}"
                self.assertIn(offered, deploy_run.output)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, dict.fromkeys(self.offered_apps, RELEASE_TAGS_ALONE))


class WhenTheSandboxIsNotIsolated(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    tags: ClassVar[Tags]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        production_data = installation.production_data
        on_a_network = build_running_sandbox_rules(f"{production_data}/sandbox", str(production_data), network="bridge")
        cls.deploy_run = deploy(installation, rules=on_a_network)
        cls.commands = installation.read_docker_commands()
        cls.tags = read_tags(installation)

    def test_should_fail_at_the_isolation_check(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "isolation"', self.deploy_run.stdout)

    def test_should_stop_the_ocr_service(self) -> None:
        compose_commands = [command for command in self.commands if command.startswith("compose")]
        self.assertTrue(any(command.endswith(" stop ocr") for command in compose_commands), compose_commands)

    def test_should_never_tag_the_new_images_deployed(self) -> None:
        self.assertNotIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)

    def test_should_not_check_the_engine_of_a_sandbox_that_is_not_isolated(self) -> None:
        self.assertEqual([command for command in self.commands if ENGINE_CHECK_MODULE in command], [])


class WhenTheEngineEnvironmentIsBroken(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    logs: ClassVar[list[str]]
    tags: ClassVar[Tags]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        broken_engine: list[Rule] = [
            {"match": rf"^{re.escape(ENGINE_CHECK)}$", "exit": 1, "stdout": SANDBOX_OUTPUT, "stderr": SANDBOX_OUTPUT}
        ]
        cls.deploy_run = deploy(installation, rules=broken_engine)
        cls.commands = installation.read_docker_commands()
        cls.logs = read_logs(installation)
        cls.tags = read_tags(installation)

    def test_should_fail_at_the_engine_s_environment(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "engine"', self.deploy_run.stdout)

    def test_should_show_the_command_it_ran(self) -> None:
        self.assertRegex(self.deploy_run.stdout, BOUNDED_ENGINE_CHECK)

    def test_should_show_nothing_the_sandbox_printed_since_it_is_untrusted(self) -> None:
        self.assertEqual([text[:40] for text in SANDBOX_TEXTS if text in self.deploy_run.output], [])

    def test_should_log_nothing_the_sandbox_printed(self) -> None:
        self.assertEqual(len(self.logs), 1)
        self.assertEqual([text[:40] for text in SANDBOX_TEXTS if text in self.logs[0]], [])

    def test_should_say_how_to_see_why_the_check_failed(self) -> None:
        self.assertEqual([step for step in PRODUCTION_ENGINE_CHECK_STEPS if step not in self.deploy_run.stdout], [])

    def test_should_stop_the_ocr_service(self) -> None:
        compose_commands = [command for command in self.commands if command.startswith("compose")]
        self.assertTrue(any(command.endswith(" stop ocr") for command in compose_commands), compose_commands)

    def test_should_never_tag_the_new_images_deployed(self) -> None:
        self.assertNotIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands)
        self.assertNotIn("tag scanmylib-ocr:latest scanmylib-ocr:deployed", self.commands)

    def test_should_say_how_to_tag_latest_the_images_that_production_ran(self) -> None:
        self.assertIn("docker tag scanmylib-api:deployed scanmylib-api:latest", self.deploy_run.stdout)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)


class WhenTheCheckOfTheEngineEnvironmentDoesNotFinishInTime(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    tags: ClassVar[Tags]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        timed_out: list[Rule] = [{"match": rf"^{re.escape(ENGINE_CHECK)}$", "exit": TIMED_OUT_STATUS}]
        cls.deploy_run = deploy(installation, rules=timed_out)
        cls.commands = installation.read_docker_commands()
        cls.tags = read_tags(installation)

    def test_should_fail_at_the_engine_s_environment(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "engine"', self.deploy_run.stdout)

    def test_should_say_how_to_see_why_the_check_failed(self) -> None:
        self.assertEqual([step for step in PRODUCTION_ENGINE_CHECK_STEPS if step not in self.deploy_run.stdout], [])

    def test_should_stop_the_ocr_service(self) -> None:
        compose_commands = [command for command in self.commands if command.startswith("compose")]
        self.assertTrue(any(command.endswith(" stop ocr") for command in compose_commands), compose_commands)

    def test_should_never_tag_the_new_images_deployed(self) -> None:
        self.assertNotIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands)
        self.assertNotIn("tag scanmylib-ocr:latest scanmylib-ocr:deployed", self.commands)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)


class WhenOlderBackupsPileUp(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    backups: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        backups = installation.production_data / "backups"
        for day in range(1, 13):
            (backups / f"state-202001{day:02d}-000000-v0.0.1").mkdir(parents=True)
        (backups / "state-20200113-000000-v0.0.1.partial").mkdir()
        cls.deploy_run = deploy(installation)
        cls.backups = list_backups(installation)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_keep_ten_backups(self) -> None:
        self.assertEqual(len(self.backups), 10)

    def test_should_remove_the_oldest_ones_and_the_partial_one(self) -> None:
        self.assertEqual(self.backups[0], "state-20200104-000000-v0.0.1")

    def test_should_keep_the_new_backup(self) -> None:
        self.assertTrue(self.backups[-1].endswith(f"-v{VERSION}"), self.backups)


class WhenAPreconditionDoesNotHold(InstallationTestCase):
    preconditions: ClassVar[Mapping[str, BrokenPrecondition]] = MappingProxyType(
        {
            "no database": BrokenPrecondition(remove_the_database, "no database in"),
            "a comment in .env": BrokenPrecondition(write_a_comment_in_env, "line"),
            "a library that is not a directory": BrokenPrecondition(move_the_library_away, "is not a directory"),
            "an untracked file": BrokenPrecondition(Installation.add_an_untracked_file, "untracked changes"),
            "a hidden change": BrokenPrecondition(
                Installation.hide_a_change_with_skip_worktree, "assume-unchanged or skip-worktree"
            ),
            "a commit after the release": BrokenPrecondition(
                Installation.commit_after_the_release, f"is not the release v{VERSION}"
            ),
            "a release not published": BrokenPrecondition(
                Installation.unpublish_the_release, f"v{VERSION} is not published on origin"
            ),
            "a development .env": BrokenPrecondition(write_a_development_env, "not production's"),
            "an empty .env": BrokenPrecondition(empty_the_env, "not production's"),
            "no OCR sandbox": BrokenPrecondition(remove_the_sandbox_manifest, "no OCR sandbox in SANDBOX_DIR"),
        }
    )
    deploy_runs: ClassVar[dict[str, ScriptRun]]
    docker_calls: ClassVar[dict[str, list[LoggedCall]]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.deploy_runs, cls.docker_calls = {}, {}
        for row, broken_precondition in cls.preconditions.items():
            installation = make_installation(cls)
            start_fake_api(cls, installation.production_api_port)
            broken_precondition.break_it(installation)
            cls.deploy_runs[row] = deploy(installation)
            cls.docker_calls[row] = installation.read_docker_calls()

    def test_should_refuse_and_say_why(self) -> None:
        self.assertEqual(sorted(self.deploy_runs), sorted(self.preconditions))
        for row, deploy_run in self.deploy_runs.items():
            with self.subTest(row):
                self.assertNotEqual(deploy_run.returncode, 0)
                self.assertIn(self.preconditions[row].refusal, deploy_run.output)

    def test_should_say_that_it_refuses_to_deploy(self) -> None:
        self.assertEqual(sorted(self.deploy_runs), sorted(self.preconditions))
        for row, deploy_run in self.deploy_runs.items():
            with self.subTest(row):
                self.assertIn("Refusing to deploy", deploy_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(sorted(self.docker_calls), sorted(self.preconditions))
        for row, docker_calls in self.docker_calls.items():
            with self.subTest(row):
                self.assertEqual(list_writing_calls(docker_calls), [])


class WhenProductionRunsANewerRelease(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        api.version = "99.0.0"
        cls.deploy_run = deploy(installation)
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_it_would_be_older(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn(f"production runs 99.0.0, newer than this release {VERSION}", self.deploy_run.stdout)

    def test_should_say_that_it_refuses_to_deploy(self) -> None:
        self.assertIn("Refusing to deploy", self.deploy_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenProductionRunsANewerReleaseOnADryRun(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    api_request_count: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        api.version = "99.0.0"
        cls.deploy_run = deploy(installation, "--dry-run")
        cls.api_request_count = api.request_count

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_say_that_a_real_run_checks_it(self) -> None:
        self.assertIn("a real run checks that production does not run a release newer", self.deploy_run.stdout)

    def test_should_send_no_request_to_the_api(self) -> None:
        self.assertEqual(self.api_request_count, 0)


class WhenTheRunningApiReportsNoRelease(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        api.version = "unknown"
        cls.deploy_run = deploy(installation)

    def test_should_say_that_the_api_reports_no_release(self) -> None:
        self.assertIn("reports 'unknown', not a release", self.deploy_run.stdout)

    def test_should_compare_no_release(self) -> None:
        self.assertNotIn("newer than this release", self.deploy_run.stdout)


class WhenTheRunningApiCannotBeRead(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.deploy_run = deploy(installation)

    def test_should_say_that_it_cannot_read_the_version(self) -> None:
        self.assertIn("cannot read the version of the running api", self.deploy_run.stdout)

    def test_should_compare_no_release(self) -> None:
        self.assertNotIn("newer than this release", self.deploy_run.stdout)


class WhenProductionRunsANewerReleaseAndADowngradeIsWanted(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        # The fake api then never reports VERSION, so the deploy fails later: only its checks are read.
        installation = make_installation(cls)
        api = start_fake_api(cls, installation.production_api_port)
        api.version = "99.0.0"
        cls.deploy_run = deploy(installation, "--allow-downgrade")

    def test_should_say_that_production_runs_a_newer_release(self) -> None:
        self.assertIn("production runs 99.0.0, newer than", self.deploy_run.stdout)

    def test_should_say_it_is_a_downgrade(self) -> None:
        self.assertIn("a downgrade (--allow-downgrade)", self.deploy_run.stdout)

    def test_should_not_refuse_to_deploy(self) -> None:
        self.assertNotIn("Refusing to deploy", self.deploy_run.stderr)


class WhenProductionsCheckoutHoldsTheReleasesTag(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        installation.run_git(installation.production_checkout, "checkout", "--quiet", f"v{VERSION}")
        cls.deploy_run = deploy(installation, "--dry-run")

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_check_the_release_as_published_on_origin(self) -> None:
        self.assertIn(f"the release v{VERSION}, as published on origin", self.deploy_run.stdout)


class WhenItIsAFirstInstallWithoutDatabase(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        remove_the_database(installation)
        cls.deploy_run = deploy(installation, "--first-install")

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)


class WhenAnotherDeployIsRunning(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    docker_calls: ClassVar[list[LoggedCall]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        lock = os.open(installation.production_checkout, os.O_RDONLY)
        cls.addClassCleanup(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cls.deploy_run = deploy(installation)
        cls.docker_calls = installation.read_docker_calls()

    def test_should_refuse_since_another_deploy_runs(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn("another deploy is running", self.deploy_run.stderr)

    def test_should_call_docker_for_nothing(self) -> None:
        self.assertEqual(self.docker_calls, [])


class WhenGivenTheRemovedSkipTestsOption(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    docker_calls: ClassVar[list[LoggedCall]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.deploy_run = deploy(installation, "--skip-tests")
        cls.docker_calls = installation.read_docker_calls()

    def test_should_stop_with_its_usage(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 2)
        self.assertIn("Usage: scripts/deploy.sh", self.deploy_run.stderr)

    def test_should_call_docker_for_nothing(self) -> None:
        self.assertEqual(self.docker_calls, [])


class WhenRunInAWorktree(InstallationTestCase):
    production_checkout: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.production_checkout = installation.production_checkout
        cls.deploy_run = deploy(installation, checkout=installation.worktree)

    def test_should_refuse_and_name_production_s_checkout(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        refusal = f"not production's checkout: production runs from {self.production_checkout}"
        self.assertIn(refusal, self.deploy_run.stdout)


class WhenRunInAnotherCloneWithACopyOfProductionsEnv(InstallationTestCase):
    production_checkout: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.production_checkout = installation.production_checkout
        cls.deploy_run = deploy(installation, checkout=installation.make_clone())
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_and_name_production_s_checkout(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        refusal = f"not production's checkout: production runs from {self.production_checkout}"
        self.assertIn(refusal, self.deploy_run.stdout)

    def test_should_say_that_it_refuses_to_deploy(self) -> None:
        self.assertIn("Refusing to deploy", self.deploy_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenProductionsContainersRunFromAnotherClone(InstallationTestCase):
    clone: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        # ~/Dev/scanmylib is then not production's checkout.
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.clone = installation.make_clone()
        installation.answer_docker(build_production_container_rules(cls.clone))
        cls.deploy_run = installation.run_script(
            installation.production_checkout, "deploy.sh", "--dry-run", timeout_seconds=120
        )

    def test_should_refuse_and_name_the_clone_as_production_s_checkout(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn(f"not production's checkout: production runs from {self.clone}", self.deploy_run.stdout)


class WhenRehearsedOnAStackWhoseApiOffersAnotherApp(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api_port = find_free_port()
        start_fake_api(cls, api_port)
        prepare_rehearsal(installation, api_port, installation.directory / "built")
        cls.rehearsal = rehearse(installation, "--apk")

    def test_should_fail_and_say_which_app_the_api_offers(self) -> None:
        self.assertNotEqual(self.rehearsal.returncode, 0)
        self.assertIn(f"the api offers the APK '{VERSION}', not {REHEARSED_APP_VERSION} ", self.rehearsal.output)


class WhenRehearsedOnAThrowawayStack(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]
    built_compose: ClassVar[str | None]
    built_files: ClassVar[list[str]]
    tags: ClassVar[Tags]
    commands: ClassVar[list[str]]
    gradle_tasks: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api_port = find_free_port()
        api = start_fake_api(cls, api_port)
        api.apk_version = REHEARSED_APP_VERSION
        export_copy = installation.directory / "built"
        prepare_rehearsal(installation, api_port, export_copy)
        cls.rehearsal = rehearse(installation, "--apk")
        cls.built_compose = read_text_if_present(export_copy / "compose.yaml")
        cls.built_files = sorted(str(path.relative_to(export_copy)) for path in export_copy.rglob("*"))
        cls.tags = read_tags(installation)
        cls.commands = installation.read_docker_commands()
        cls.gradle_tasks = read_gradle_tasks(installation.read_docker_calls())

    def test_should_succeed(self) -> None:
        self.assertEqual(self.rehearsal.returncode, 0, self.rehearsal.output)

    def test_should_build_the_dev_app_with_its_tests_and_lint_as_every_development_build(self) -> None:
        self.assertEqual(self.gradle_tasks, ["test", "assembleDev", "lint"])

    def test_should_check_that_the_api_offers_the_app_it_published(self) -> None:
        self.assertIn(f"the api offers the APK {REHEARSED_APP_VERSION} to the phones", self.rehearsal.stdout)

    def test_should_skip_the_check_of_the_release_on_origin(self) -> None:
        self.assertIn("skip  the release on origin (rehearsal", self.rehearsal.stdout)

    def test_should_report_the_uncommitted_and_untracked_changes(self) -> None:
        self.assertIn("uncommitted or untracked changes", self.rehearsal.stdout)

    def test_should_build_the_commit_without_its_uncommitted_change(self) -> None:
        self.assertIsNotNone(self.built_compose)
        self.assertNotIn("# uncommitted", self.built_compose or "")

    def test_should_build_the_commit_without_the_untracked_file(self) -> None:
        self.assertIn("compose.yaml", self.built_files)
        self.assertNotIn("untracked.txt", self.built_files)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)

    def test_should_change_no_image_of_production(self) -> None:
        changes = [command for command in self.commands if not command.startswith(("ps", "inspect"))]
        production_images = [command for command in changes if "scanmylib-api" in command]
        self.assertEqual([command for command in production_images if "scanmylib-review" not in command], [])

    def test_should_tag_the_images_of_the_stack_deployed(self) -> None:
        self.assertIn(f"tag {REHEARSAL_PROJECT}-api:latest {REHEARSAL_PROJECT}-api:deployed", self.commands)

    def test_should_print_its_commands_as_those_of_dev_sh(self) -> None:
        self.assertIn("$ scripts/dev.sh compose up -d --no-build", self.rehearsal.stdout)

    def test_should_skip_the_engine_s_environment_since_the_fake_ocr_runs_no_engine(self) -> None:
        self.assertEqual([command for command in self.commands if ENGINE_CHECK_MODULE in command], [])
        self.assertIn("skipped (the fake OCR runs no engine)", self.rehearsal.stdout)


class WhenRehearsedOnTheFakeOcrWithoutASandbox(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        write_rehearsal_env(installation, installation.directory / "rehearsal", find_free_port())
        remove_the_sandbox_manifest(installation)
        cls.rehearsal = rehearse(installation, "--dry-run")

    def test_should_succeed(self) -> None:
        self.assertEqual(self.rehearsal.returncode, 0, self.rehearsal.output)

    def test_should_not_ask_for_an_ocr_sandbox(self) -> None:
        self.assertNotIn("no OCR sandbox", self.rehearsal.output)


class WhenRehearsedWithAnEnvThatPointsAtProduction(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        api_port = find_free_port()
        prepare_rehearsal(installation, api_port, installation.directory / "built")
        (installation.worktree / ".env").write_text(
            installation.build_development_env(
                COMPOSE_PROJECT_NAME=REHEARSAL_PROJECT,
                IMAGE_PREFIX=REHEARSAL_PROJECT,
                DATA_DIR=str(installation.production_data),
                API_PORT=str(api_port),
            )
        )
        cls.rehearsal = installation.run_script(
            installation.worktree, "deploy.sh", timeout_seconds=120, environment=REHEARSAL_ENVIRONMENT
        )
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_the_stack_is_not_isolated_from_production(self) -> None:
        self.assertNotEqual(self.rehearsal.returncode, 0)
        self.assertIn("not isolated from production", self.rehearsal.stdout)

    def test_should_only_read_from_docker_before_it_refuses(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenRehearsedFromACommitThatNamesProductionsImage(InstallationTestCase):
    arguments: ClassVar[Mapping[str, tuple[str, ...]]] = MappingProxyType(
        {"a dry run": ("--dry-run",), "a real run": ()}
    )
    rehearsals: ClassVar[dict[str, ScriptRun]]
    docker_calls: ClassVar[dict[str, list[LoggedCall]]]
    exports_left: ClassVar[list[Path]]

    @classmethod
    def setUpClass(cls) -> None:
        # A committed mistake that the working tree no longer shows: the commit is what would be built, so the commit
        # is what is checked.
        installation = make_installation(cls)
        write_rehearsal_env(installation, installation.directory / "rehearsal", find_free_port())
        compose = installation.worktree / "compose.yaml"
        original = compose.read_text()
        api_image = "image: ${IMAGE_PREFIX:-${COMPOSE_PROJECT_NAME}}-api:latest"
        compose.write_text(replace_once(original, api_image, "image: scanmylib-api:latest"))
        installation.run_git(installation.worktree, "commit", "--quiet", "--all", "--message", "Wrong image")
        compose.write_text(original)
        cls.rehearsals, cls.docker_calls = {}, {}
        for row, row_arguments in cls.arguments.items():
            installation.forget_docker_calls()
            cls.rehearsals[row] = rehearse(installation, *row_arguments)
            cls.docker_calls[row] = installation.read_docker_calls()
        cls.exports_left = list(installation.directory.glob("scanmylib-deploy.*"))

    def test_should_refuse_since_the_stack_is_not_isolated_from_production(self) -> None:
        self.assertEqual(sorted(self.rehearsals), sorted(self.arguments))
        for row, rehearsal in self.rehearsals.items():
            with self.subTest(row):
                self.assertNotEqual(rehearsal.returncode, 0)
                self.assertIn("not isolated from production", rehearsal.stdout)

    def test_should_name_production_s_image(self) -> None:
        self.assertEqual(sorted(self.rehearsals), sorted(self.arguments))
        for row, rehearsal in self.rehearsals.items():
            with self.subTest(row):
                self.assertIn("the image scanmylib-api:latest is production's", rehearsal.stdout)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(sorted(self.docker_calls), sorted(self.arguments))
        for row, docker_calls in self.docker_calls.items():
            with self.subTest(row):
                self.assertEqual(list_writing_calls(docker_calls), [])

    def test_should_remove_the_export(self) -> None:
        self.assertEqual(self.exports_left, [])


class WhenRehearsedWithAnExtendsFileChangedInTheCheckout(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        # up reads relative extends files from this checkout, not from the export: an uncommitted change there is what
        # would start.
        installation = make_installation(cls)
        compose = (installation.worktree / "compose.yaml").read_text()
        extra = installation.worktree / "fake-extra.yaml"
        extra.write_text("services:\n  extra:\n    environment:\n      EXTRA: '1'\n")
        extends = "  ocr-fake:\n    extends: {file: fake-extra.yaml, service: extra}\n"
        commit_rehearsal(installation, replace_once(compose, "  ocr-fake:\n", extends))
        extra.write_text("services:\n  extra:\n    privileged: true\n")
        cls.rehearsal = rehearse(installation)
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_the_stack_is_not_isolated_from_production(self) -> None:
        self.assertNotEqual(self.rehearsal.returncode, 0)
        self.assertIn("not isolated from production", self.rehearsal.stdout)

    def test_should_name_the_setting_of_the_extends_file(self) -> None:
        self.assertIn("privileged", self.rehearsal.stdout)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenRehearsedWithABindSourceMissingFromTheExport(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        # A relative bind source missing from the export is never mounted by the build's resolution, but up resolves it
        # in this checkout, where it exists.
        installation = make_installation(cls)
        compose = (installation.worktree / "compose.yaml").read_text()
        # The last volume of ocr-fake comes right before its environment.
        anchor = "    environment:\n      SCANMYLIB_PROJECT:"
        bind = "      - {type: bind, source: ./.git, target: /repo, bind: {create_host_path: false}}\n"
        commit_rehearsal(installation, replace_once(compose, anchor, bind + anchor))
        cls.rehearsal = rehearse(installation)
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_the_stack_is_not_isolated_from_production(self) -> None:
        self.assertNotEqual(self.rehearsal.returncode, 0)
        self.assertIn("not isolated from production", self.rehearsal.stdout)

    def test_should_name_the_bind_source(self) -> None:
        self.assertIn(".git", self.rehearsal.stdout)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


if __name__ == "__main__":
    unittest.main()
