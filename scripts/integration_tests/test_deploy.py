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
import shlex
import sqlite3
import subprocess
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
    CLIPBOARD_SEQUENCE,
    COPIED,
    ENGINE_CHECK,
    ENGINE_CHECK_MODULE,
    ENGINE_CHECK_MODULE_COMMAND,
    NEW_API_IMAGE_ID,
    NEW_OCR_IMAGE_ID,
    PRODUCTION_ENGINE_CHECK_STEPS,
    RUNNING_OCR_IMAGE_ID,
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
COMPOSE_BUILD = r"^compose .* build (--[a-z-]+ )*api ocr$"
SANDBOX_CHECK = rf"^run .* python3 -m {re.escape(ENGINE_CHECK_MODULE)}$"
SANDBOX_CHECK_NAME = re.compile(r"scanmylib-sandbox-check-\d{8}-\d{6}")
#: What keeps the check of the sandbox before the restart as isolated as the ocr service, after its --name.
ISOLATED_SANDBOX_CHECK = (
    "--network", "none", "--read-only", "--tmpfs", "/tmp", "--tmpfs", "/var/cache/ocr:mode=1777", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true", "--user", f"{os.getuid()}:{os.getgid()}",
    "--device", "nvidia.com/gpu=all",
)  # fmt: skip
INSTALL_SANDBOX = r"^compose .* run --rm -T --pull never ocr-setup$"
#: The free space of a new sandbox, which the disk of a test cannot give: the tests lower it to nothing.
ROOM_FOR_A_NEW_SANDBOX = MappingProxyType(
    {"scripts/deploy.sh": ("NEW_SANDBOX_BYTES=$((36 * 1024 * 1024 * 1024))", "NEW_SANDBOX_BYTES=0")}
)
REPLACED_MANIFEST = '{"sandbox": "replaced"}'
NEW_MANIFEST = '{"sandbox": "new"}'
INSTALLATION_LOG = "the installation's log\n"
#: The options of the ocr service's own settings that the check takes from compose.yaml.
SERVICE_SETTINGS_OF_THE_CHECK = ("--env=HOME=/tmp/home", "--env=HF_HUB_OFFLINE=1", "--memory=17179869184",
                                 "--pids-limit=4096")  # fmt: skip
#: The ocr image that the deploy builds, which :latest names until a failure puts it back on :deployed.
NEW_OCR_IMAGE: Rule = {
    "match": r"^image inspect --format \{\{\.Id\}\} [a-z0-9-]+-ocr:latest$",
    "stdout": f"{NEW_OCR_IMAGE_ID}\n",
}
#: What a successful deploy tags :deployed: the images that the containers it started run (build_running_sandbox_rules).
NEW_API_IMAGE_TAGGED_DEPLOYED = f"tag {NEW_API_IMAGE_ID} scanmylib-api:deployed"
NEW_OCR_IMAGE_TAGGED_DEPLOYED = f"tag {RUNNING_OCR_IMAGE_ID} scanmylib-ocr:deployed"
RUNNING_IMAGES_TAGGED_DEPLOYED: list[Rule] = [
    {"match": r"^image inspect --format \{\{\.Id\}\} scanmylib-(api|ocr):deployed$", "stdout": "sha256:good\n"},
    {"match": r"^inspect --format \{\{\.Image\}\} previous(api|ocr)id$", "stdout": "sha256:good\n"},
]


def build_running_images_never_tagged_deployed() -> list[Rule]:
    rules: list[Rule] = []
    for service in ("api", "ocr"):
        rules += [
            {
                "match": rf"^ps --all --quiet --filter label=com\.docker\.compose\.project=scanmylib "
                rf"--filter label=com\.docker\.compose\.service={service} "
                rf"--filter label=com\.docker\.compose\.oneoff=False$",
                "stdout": f"previous{service}id\n",
            },
            {
                "match": rf"^inspect --format \{{\{{\.Image\}}\}} previous{service}id$",
                "stdout": f"sha256:old{service}\n",
            },
        ]
    # The sandbox's :latest names the new image whenever it is read (NEW_OCR_IMAGE), since the deploy reads it again
    # before the restart.
    rules.append({"match": r"^image inspect --format \{\{\.Id\}\} scanmylib-api:latest$", "stdout": "sha256:oldapi\n"})
    return rules


def deploy(
    installation: Installation,
    *arguments: str,
    rules: list[Rule] | None = None,
    checkout: Path | None = None,
) -> ScriptRun:
    production_data = installation.production_data
    sandbox = build_running_sandbox_rules(f"{production_data}/sandbox", str(production_data))
    installation.answer_docker((rules or []) + build_running_images_never_tagged_deployed() + [NEW_OCR_IMAGE] + sandbox)
    return installation.run_script(
        checkout or installation.production_checkout, "deploy.sh", *arguments, timeout_seconds=120
    )


def make_installation_with_a_sandbox_to_replace(test_case: type[InstallationTestCase]) -> Installation:
    installation = make_installation(test_case, ROOM_FOR_A_NEW_SANDBOX)
    (installation.production_data / "sandbox" / "MANIFEST.json").write_text(REPLACED_MANIFEST)
    return installation


def build_sandbox_installation(sandbox: Path, *, exit_status: int = 0) -> Rule:
    """ocr-setup, which installs the new sandbox next to `sandbox`, its log first and its manifest last, and prints what
    a sandbox may."""
    log = {f"{sandbox}.new/setup.log": INSTALLATION_LOG}
    manifest = {f"{sandbox}.new/MANIFEST.json": NEW_MANIFEST} if exit_status == 0 else {}
    return {"match": INSTALL_SANDBOX, "stdout": SANDBOX_OUTPUT, "exit": exit_status, "host_files": log | manifest}


def find_sandbox_check(calls: list[LoggedCall]) -> list[str]:
    """The arguments of the check of the sandbox before the restart: raises StopIteration when it never ran, as
    find_command does."""
    return next(call["argv"] for call in calls if re.search(SANDBOX_CHECK, " ".join(call["argv"])))


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


def find_compose_build(commands: list[str]) -> str:
    """Raises StopIteration when no command builds the images, as find_command does, so that a test of a build that
    never ran fails rather than finds nothing wrong with it."""
    return next(command for command in commands if re.search(COMPOSE_BUILD, command))


def parse_env(env_text: str | None) -> dict[str, str]:
    if env_text is None:
        raise FileNotFoundError("no .env to read")
    return dict(line.split("=", 1) for line in env_text.splitlines() if line and not line.startswith("#"))


def read_option_value(command: str, option: str) -> str:
    return "".join(command.partition(f"{option} ")[2].split()[:1])


def replace_once(text: str, old: str, new: str) -> str:
    """`text` with its first `old` replaced by `new`: refuses a text without `old`, which the change would leave as
    it is."""
    if old not in text:
        raise ValueError(f"{old!r} is not in the text to change")
    return text.replace(old, new, 1)


def write_rehearsal_env(installation: Installation, rehearsal_data: Path, api_port: int, **changes: str) -> None:
    (installation.worktree / ".env").write_text(
        installation.build_development_env(
            COMPOSE_PROJECT_NAME=REHEARSAL_PROJECT,
            IMAGE_PREFIX=REHEARSAL_PROJECT,
            DATA_DIR=str(rehearsal_data),
            LIBRARY_DIR=f"{rehearsal_data}/library",
            ANDROID_DIR=f"{rehearsal_data}/android",
            API_PORT=str(api_port),
            **changes,
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
            {"match": COMPOSE_BUILD, "snapshot": str(export_copy)},
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


def put_a_comma_in_the_sandbox_path(installation: Installation) -> None:
    sandbox = installation.production_data / "sand,box"
    (installation.production_data / "sandbox").rename(sandbox)
    env = installation.build_production_env(SANDBOX_DIR=str(sandbox), SANDBOX_SETUP_DIR=str(sandbox))
    (installation.production_checkout / ".env").write_text(env)


def run_the_sandbox_as_root(installation: Installation) -> None:
    (installation.production_checkout / ".env").write_text(installation.build_production_env(SCANMYLIB_UID="0"))


def run_the_sandbox_in_a_group_named_by_its_name(installation: Installation) -> None:
    (installation.production_checkout / ".env").write_text(installation.build_production_env(SCANMYLIB_GID="root"))


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

    def test_should_say_that_it_would_tag_deployed_the_images_that_the_restarted_containers_run(self) -> None:
        self.assertIn("would tag scanmylib-api:deployed on the image that api runs", self.deploy_run.stdout)
        self.assertIn("would tag scanmylib-ocr:deployed on the image that ocr runs", self.deploy_run.stdout)

    def test_should_say_that_it_would_check_the_engine_s_environment_bounded_in_time_and_without_its_output(
        self,
    ) -> None:
        self.assertRegex(
            self.deploy_run.stdout,
            rf"would run: timeout --kill-after=10 \d+ docker exec <the ocr container> python3 -m "
            rf"{re.escape(ENGINE_CHECK_MODULE)}, its output discarded",
        )

    def test_should_say_that_it_would_check_the_new_image_against_the_sandbox_before_the_restart(self) -> None:
        self.assertRegex(
            self.deploy_run.stdout,
            rf"would run: timeout --kill-after=10 \d+ docker run --rm --init --name {SANDBOX_CHECK_NAME.pattern} .* "
            rf"scanmylib-ocr:latest python3 -m {re.escape(ENGINE_CHECK_MODULE)}\n",
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
    sandbox_check: ClassVar[list[str]]
    compose_builds: ClassVar[list[str]]
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
        cls.deploy_run = deploy(installation, "--apk", rules=[{"match": COMPOSE_BUILD, "snapshot": str(export_copy)}])
        cls.commands = installation.read_docker_commands()
        cls.sandbox_check = find_sandbox_check(installation.read_docker_calls())
        cls.compose_builds = [command for command in cls.commands if re.search(r"^compose .* build ", command)]
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
        return find_compose_build(self.commands)

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

    def test_should_build_the_images_once_on_the_current_image_of_their_base_tag_since_a_local_copy_can_lack_its_fixes(
        self,
    ) -> None:
        self.assertEqual(len(self.compose_builds), 1)
        self.assertRegex(self.compose_builds[0], r" build --pull api ocr$")

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
        self.assertEqual(containers_and_image_builds, [" ".join(self.sandbox_check)])

    def test_should_check_the_new_image_against_the_sandbox_in_a_container_as_isolated_as_the_ocr_service(
        self,
    ) -> None:
        self.assertEqual(
            self.sandbox_check[: 5 + len(ISOLATED_SANDBOX_CHECK)],
            ["run", "--rm", "--init", "--name", self.sandbox_check[4], *ISOLATED_SANDBOX_CHECK],
        )

    def test_should_name_the_container_of_the_check_after_the_stack_and_the_deploy(self) -> None:
        self.assertRegex(self.sandbox_check[4], rf"^{SANDBOX_CHECK_NAME.pattern}$")

    def test_should_mount_only_the_sandbox_read_only_and_import_the_engine_s_libraries_in_the_new_image(
        self,
    ) -> None:
        self.assertEqual(
            self.sandbox_check[-6:],
            [
                "--mount",
                f"type=bind,src={self.production_data}/sandbox,dst=/opt/sandbox,readonly",
                NEW_OCR_IMAGE_ID,
                *ENGINE_CHECK_MODULE_COMMAND,
            ],
        )

    def test_should_give_the_check_the_environment_and_the_limits_of_the_ocr_service(self) -> None:
        service_options = self.sandbox_check[5 + len(ISOLATED_SANDBOX_CHECK) : -6]
        self.assertEqual([option for option in SERVICE_SETTINGS_OF_THE_CHECK if option not in service_options], [])

    def test_should_give_the_check_nothing_but_the_environment_and_the_limits_of_the_ocr_service(self) -> None:
        service_options = self.sandbox_check[5 + len(ISOLATED_SANDBOX_CHECK) : -6]
        self.assertNotEqual(service_options, [])
        self.assertEqual(
            [option for option in service_options if not option.startswith(("--env=", "--memory=", "--pids-limit="))],
            [],
        )

    def test_should_check_the_sandbox_once_the_new_images_are_built(self) -> None:
        self.assertGreater(self.commands.index(" ".join(self.sandbox_check)), self.commands.index(self.find_build()))

    def test_should_check_the_sandbox_before_the_backup_so_that_a_failure_leaves_production_as_it_was(self) -> None:
        stdout = self.deploy_run.stdout
        self.assertLess(stdout.index("$ timeout --kill-after=10 "), stdout.index("Backup of the state"))

    def test_should_show_that_it_bounds_the_check_of_the_sandbox_in_time(self) -> None:
        self.assertRegex(self.deploy_run.stdout, r"\$ timeout --kill-after=10 \d+ docker run --rm --init ")

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
        self.assertEqual(self.commands.count(NEW_API_IMAGE_TAGGED_DEPLOYED), 1)

    def test_should_tag_deployed_the_images_its_containers_run_whatever_latest_names_by_then(self) -> None:
        tagged = [
            command for command in self.commands if re.fullmatch(r"tag \S+ scanmylib-(api|ocr):deployed", command)
        ]
        self.assertEqual(tagged[-2:], [NEW_API_IMAGE_TAGGED_DEPLOYED, NEW_OCR_IMAGE_TAGGED_DEPLOYED])

    def test_should_tag_the_new_images_deployed_once_they_pass_the_isolation_check(self) -> None:
        last_check_index = max(self.find_isolation_check_indexes())
        tag_index = self.commands.index(NEW_API_IMAGE_TAGGED_DEPLOYED)
        self.assertGreater(tag_index, last_check_index)

    def test_should_check_the_engine_s_environment_in_the_new_sandbox(self) -> None:
        self.assertIn(ENGINE_CHECK, self.commands)

    def test_should_show_that_it_bounds_the_check_of_the_engine_s_environment_in_time(self) -> None:
        self.assertRegex(self.deploy_run.stdout, BOUNDED_ENGINE_CHECK)

    def test_should_check_the_engine_only_once_the_sandbox_passed_the_isolation_check(self) -> None:
        self.assertGreater(self.commands.index(ENGINE_CHECK), max(self.find_isolation_check_indexes()))

    def test_should_tag_the_new_images_deployed_once_the_engine_s_environment_passed(self) -> None:
        tag_indexes = [
            self.commands.index(command) for command in (NEW_API_IMAGE_TAGGED_DEPLOYED, NEW_OCR_IMAGE_TAGGED_DEPLOYED)
        ]
        self.assertGreater(min(tag_indexes), self.commands.index(ENGINE_CHECK))

    def test_should_tag_the_new_images_deployed_before_the_app_is_built(self) -> None:
        app_build_index = min(
            index for index, command in enumerate(self.commands) if "scanmylib-android-build" in command
        )
        tag_index = self.commands.index(NEW_API_IMAGE_TAGGED_DEPLOYED)
        self.assertLess(tag_index, app_build_index)

    def test_should_tag_the_new_sandbox_image_deployed_once_it_runs(self) -> None:
        up_index = self.find_command_index(" up -d --no-build --wait")
        self.assertIn(NEW_OCR_IMAGE_TAGGED_DEPLOYED, self.commands[up_index:])

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


class WhenTheImageThatTheRestartedApiRunsCannotBeRead(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands_after_the_restart: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        no_api_container: list[Rule] = [{"match": r" ps -q api$", "stdout": ""}]
        cls.deploy_run = deploy(installation, rules=no_api_container)
        commands = installation.read_docker_commands()
        up_index = commands.index(find_command(commands, " up -d --no-build --wait"))
        cls.commands_after_the_restart = commands[up_index:]

    def test_should_succeed_since_the_new_release_runs(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_warn_that_deployed_still_names_the_previous_api_image(self) -> None:
        self.assertIn(
            "warning: cannot read the image that api runs: scanmylib-api:deployed still names the previous image",
            self.deploy_run.stdout,
        )

    def test_should_never_tag_the_api_image_deployed_once_restarted(self) -> None:
        tagged = [
            command
            for command in self.commands_after_the_restart
            if re.fullmatch(r"tag \S+ scanmylib-api:deployed", command)
        ]
        self.assertEqual(tagged, [])

    def test_should_still_tag_deployed_the_image_that_the_sandbox_runs(self) -> None:
        self.assertIn(NEW_OCR_IMAGE_TAGGED_DEPLOYED, self.commands_after_the_restart)


class WhenTheBuildFails(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    backups: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.deploy_run = deploy(installation, rules=[{"match": COMPOSE_BUILD, "exit": 1}])
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
        self.assertNotIn(NEW_API_IMAGE_TAGGED_DEPLOYED, self.commands)

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
        self.assertNotIn(NEW_API_IMAGE_TAGGED_DEPLOYED, self.commands)

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
        self.assertEqual(self.commands.count(NEW_API_IMAGE_TAGGED_DEPLOYED), 1)

    def test_should_tag_the_new_images_deployed_only_once_they_run(self) -> None:
        up_index = self.commands.index(find_command(self.commands, " up -d --no-build"))
        self.assertGreater(self.commands.index(NEW_API_IMAGE_TAGGED_DEPLOYED), up_index)


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
            {"match": COMPOSE_BUILD, "exit": 1},
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
        build_index = self.commands.index(find_compose_build(self.commands))
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
        self.assertIn(NEW_API_IMAGE_TAGGED_DEPLOYED, self.commands)

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


class WhenLatestNamesAnotherImageOnceTheNewImageIsChecked(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        latest_moved: list[Rule] = [
            *RUNNING_IMAGES_TAGGED_DEPLOYED,
            {**NEW_OCR_IMAGE, "max_calls": 1},
            {"match": NEW_OCR_IMAGE["match"], "stdout": "sha256:rebuilt\n"},
        ]
        cls.deploy_run = deploy(installation, rules=latest_moved)
        cls.commands = installation.read_docker_commands()

    def test_should_refuse_to_restart_on_an_image_that_the_sandbox_s_check_did_not_pass(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn("not the image checked against the sandbox", self.deploy_run.stdout)

    def test_should_say_that_production_is_unchanged(self) -> None:
        self.assertIn("Production is unchanged", self.deploy_run.stdout)

    def test_should_start_nothing(self) -> None:
        self.assertEqual([command for command in self.commands if " up " in command], [])

    def test_should_never_tag_the_new_images_deployed(self) -> None:
        self.assertNotIn(NEW_OCR_IMAGE_TAGGED_DEPLOYED, self.commands)


class WhenTheCheckOfTheSandboxCannotTakeASettingOfTheOcrService(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        # What docker compose resolves for a variable listed without a value, which it would take from the caller.
        variable_without_a_value = {"services": {"ocr": {"environment": {"HOME": None}}}}
        resolved: list[Rule] = [
            {"match": r"^compose .* config --format json$", "stdout": json.dumps(variable_without_a_value)}
        ]
        cls.deploy_run = deploy(installation, rules=resolved)
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_and_say_why(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn("the variable HOME of the ocr service has no value", self.deploy_run.output)

    def test_should_refuse_before_the_hour_of_a_build_or_an_installation(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenTheNewImageFailsTheCheckOfTheSandbox(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    sandbox_check: ClassVar[list[str]]
    backups: ClassVar[list[str]]
    logs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        broken_sandbox: list[Rule] = [
            {"match": SANDBOX_CHECK, "exit": 1, "stdout": SANDBOX_OUTPUT, "stderr": SANDBOX_OUTPUT}
        ]
        cls.deploy_run = deploy(installation, rules=broken_sandbox)
        cls.commands = installation.read_docker_commands()
        cls.sandbox_check = find_sandbox_check(installation.read_docker_calls())
        cls.backups = list_backups(installation)
        cls.logs = read_logs(installation)

    def find_diagnostic(self) -> list[str]:
        line = next(line for line in self.deploy_run.stdout.splitlines() if line.startswith("  docker run "))
        return shlex.split(line)

    def test_should_fail_at_the_check_of_the_sandbox(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "check"', self.deploy_run.stdout)

    def test_should_say_that_production_is_unchanged(self) -> None:
        self.assertIn("Production is unchanged", self.deploy_run.stdout)

    def test_should_tag_latest_the_images_that_production_runs_again(self) -> None:
        self.assertIn("tag scanmylib-api:deployed scanmylib-api:latest", self.commands)
        self.assertIn("tag scanmylib-ocr:deployed scanmylib-ocr:latest", self.commands)

    def test_should_back_up_nothing(self) -> None:
        self.assertEqual(self.backups, [])

    def test_should_start_nothing(self) -> None:
        self.assertEqual([command for command in self.commands if " up " in command], [])

    def test_should_never_tag_the_new_images_deployed(self) -> None:
        self.assertNotIn(NEW_OCR_IMAGE_TAGGED_DEPLOYED, self.commands)

    def test_should_print_the_check_it_ran_as_one_command_that_shows_why_through_cat_v(self) -> None:
        self.assertEqual(self.find_diagnostic(), ["docker", *self.sandbox_check, "2>&1", "|", "cat", "-v"])

    def test_should_name_the_refused_image_by_its_id_since_latest_names_the_previous_one_again_by_then(self) -> None:
        diagnostic = self.find_diagnostic()
        self.assertEqual(diagnostic[diagnostic.index("python3") - 1], NEW_OCR_IMAGE_ID)

    def test_should_show_nothing_the_sandbox_printed_since_it_is_untrusted(self) -> None:
        self.assertEqual([text[:40] for text in SANDBOX_TEXTS if text in self.deploy_run.output], [])

    def test_should_log_nothing_the_sandbox_printed(self) -> None:
        self.assertEqual(len(self.logs), 1)
        self.assertEqual([text[:40] for text in SANDBOX_TEXTS if text in self.logs[0]], [])

    def test_should_suggest_a_new_sandbox_in_case_the_new_image_needs_one(self) -> None:
        self.assertIn("deploy with --new-sandbox", self.deploy_run.stdout)


class WhenTheCheckOfTheSandboxDoesNotFinishInTime(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    sandbox_check: ClassVar[list[str]]
    backups: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.deploy_run = deploy(installation, rules=[{"match": SANDBOX_CHECK, "exit": TIMED_OUT_STATUS}])
        cls.commands = installation.read_docker_commands()
        cls.sandbox_check = find_sandbox_check(installation.read_docker_calls())
        cls.backups = list_backups(installation)

    def test_should_fail_at_the_check_of_the_sandbox(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "check"', self.deploy_run.stdout)

    def test_should_remove_the_container_that_the_timeout_left_by_its_name(self) -> None:
        removal_index = self.commands.index(f"rm -f {self.sandbox_check[4]}")
        self.assertGreater(removal_index, self.commands.index(" ".join(self.sandbox_check)))

    def test_should_say_that_production_is_unchanged(self) -> None:
        self.assertIn("Production is unchanged", self.deploy_run.stdout)

    def test_should_tag_latest_the_images_that_production_runs_again(self) -> None:
        self.assertIn("tag scanmylib-ocr:deployed scanmylib-ocr:latest", self.commands)

    def test_should_back_up_nothing(self) -> None:
        self.assertEqual(self.backups, [])

    def test_should_start_nothing(self) -> None:
        self.assertEqual([command for command in self.commands if " up " in command], [])


class WhenTheReleaseIsDeployedWithANewSandbox(InstallationTestCase):
    production_checkout: ClassVar[Path]
    production_data: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    installation_call: ClassVar[LoggedCall]
    sandbox_check: ClassVar[list[str]]
    production_env: ClassVar[dict[str, str]]
    sandbox_manifest: ClassVar[str | None]
    replaced_sandboxes: ClassVar[dict[str, str | None]]
    is_new_sandbox_left: ClassVar[bool]
    is_env_copy_left: ClassVar[bool]
    going_back_lines: ClassVar[list[str]]
    sandbox_manifest_after_going_back: ClassVar[str | None]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation_with_a_sandbox_to_replace(cls)
        start_fake_api(cls, installation.production_api_port)
        sandbox = installation.production_data / "sandbox"
        cls.production_checkout = installation.production_checkout
        cls.production_data = installation.production_data
        cls.deploy_run = deploy(installation, "--new-sandbox", rules=[build_sandbox_installation(sandbox)])
        calls = installation.read_docker_calls()
        cls.commands = installation.read_docker_commands()
        cls.installation_call = next(call for call in calls if re.search(INSTALL_SANDBOX, " ".join(call["argv"])))
        cls.sandbox_check = find_sandbox_check(calls)
        cls.production_env = parse_env((installation.production_checkout / ".env").read_text())
        cls.sandbox_manifest = read_text_if_present(sandbox / "MANIFEST.json")
        cls.replaced_sandboxes = {
            path.name: read_text_if_present(path / "MANIFEST.json")
            for path in installation.production_data.glob("sandbox.replaced-*")
        }
        cls.is_new_sandbox_left = Path(f"{sandbox}.new").exists()
        env_file = read_option_value(" ".join(cls.installation_call["argv"]), "--env-file")
        cls.is_env_copy_left = Path(env_file).exists()
        going_back = cls.deploy_run.stdout.split("Deployed scanmylib", 1)[-1]
        cls.going_back_lines = [line.strip() for line in going_back.splitlines() if line.startswith("  ")]
        for move in [line for line in cls.going_back_lines if line.startswith("mv -T ")]:
            subprocess.run(shlex.split(move), check=True)
        cls.sandbox_manifest_after_going_back = read_text_if_present(sandbox / "MANIFEST.json")

    def find_command_index(self, pattern: str) -> int:
        return next(index for index, command in enumerate(self.commands) if re.search(pattern, command))

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_install_the_new_sandbox_with_ocr_setup_from_production_s_checkout_without_a_terminal(self) -> None:
        argv = self.installation_call["argv"]
        self.assertEqual(
            [*argv[:3], *argv[argv.index("--env-file") + 2 :]],
            ["compose", "--project-directory", str(self.production_checkout), "--profile", "fake-ocr", "--profile",
             "setup", "run", "--rm", "-T", "--pull", "never", "ocr-setup"],
        )  # fmt: skip

    def test_should_give_ocr_setup_a_copy_of_env_that_only_sets_where_it_installs(self) -> None:
        expected = {**self.production_env, "SANDBOX_SETUP_DIR": f"{self.production_data}/sandbox.new"}
        self.assertEqual(parse_env(self.installation_call.get("env_file")), expected)

    def test_should_remove_the_copy_of_env(self) -> None:
        self.assertFalse(self.is_env_copy_left)

    def test_should_check_the_new_image_against_the_new_sandbox(self) -> None:
        self.assertIn(f"type=bind,src={self.production_data}/sandbox.new,dst=/opt/sandbox,readonly", self.sandbox_check)

    def test_should_check_the_new_sandbox_once_installed(self) -> None:
        self.assertGreater(self.find_command_index(SANDBOX_CHECK), self.find_command_index(INSTALL_SANDBOX))

    def test_should_stop_the_ocr_service_before_the_restart(self) -> None:
        self.assertLess(self.find_command_index(r" stop ocr$"), self.find_command_index(r" up -d --no-build --wait"))

    def test_should_install_the_new_sandbox_while_production_runs(self) -> None:
        self.assertLess(self.find_command_index(INSTALL_SANDBOX), self.find_command_index(r" stop ocr$"))

    def test_should_run_the_new_sandbox_in_sandbox_dir(self) -> None:
        self.assertEqual(self.sandbox_manifest, NEW_MANIFEST)

    def test_should_keep_the_replaced_sandbox(self) -> None:
        self.assertEqual(list(self.replaced_sandboxes.values()), [REPLACED_MANIFEST])

    def test_should_name_the_replaced_sandbox_after_the_deployment(self) -> None:
        self.assertRegex(next(iter(self.replaced_sandboxes)), r"^sandbox\.replaced-\d{8}-\d{6}$")

    def test_should_leave_no_new_sandbox_aside(self) -> None:
        self.assertFalse(self.is_new_sandbox_left)

    def test_should_say_how_to_remove_the_replaced_sandbox_since_the_scripts_never_delete_one(self) -> None:
        replaced = self.production_data / next(iter(self.replaced_sandboxes))
        self.assertIn(f"  rm -rf {replaced}\n", self.deploy_run.stdout)

    def test_should_pass_what_the_installation_prints_through_cat_v_since_it_is_untrusted(self) -> None:
        self.assertNotIn(CLIPBOARD_SEQUENCE, self.deploy_run.output)

    def test_should_say_to_stop_the_ocr_service_before_going_back_to_the_replaced_sandbox(self) -> None:
        first_move = next(index for index, line in enumerate(self.going_back_lines) if line.startswith("mv -T "))
        self.assertIn("scripts/prod.sh compose stop ocr", self.going_back_lines[:first_move])

    def test_should_print_the_moves_that_go_back_to_the_replaced_sandbox(self) -> None:
        self.assertEqual(self.sandbox_manifest_after_going_back, REPLACED_MANIFEST)

    def test_should_say_to_deploy_the_previous_release_again_on_it(self) -> None:
        self.assertIn("\n  scripts/deploy.sh --allow-downgrade\n", self.deploy_run.stdout)

    def test_should_put_no_version_that_the_api_reports_in_the_commands_it_prints(self) -> None:
        self.assertEqual([line for line in self.going_back_lines if VERSION in line], [])


class WhenTheInstallationOfTheNewSandboxFails(InstallationTestCase):
    production_data: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    backups: ClassVar[list[str]]
    sandbox_manifest: ClassVar[str | None]
    is_new_sandbox_left: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation_with_a_sandbox_to_replace(cls)
        start_fake_api(cls, installation.production_api_port)
        sandbox = installation.production_data / "sandbox"
        cls.production_data = installation.production_data
        failing = build_sandbox_installation(sandbox, exit_status=1)
        cls.deploy_run = deploy(installation, "--new-sandbox", rules=[failing])
        cls.commands = installation.read_docker_commands()
        cls.backups = list_backups(installation)
        cls.sandbox_manifest = read_text_if_present(sandbox / "MANIFEST.json")
        cls.is_new_sandbox_left = Path(f"{sandbox}.new").is_dir()

    def test_should_fail_at_the_new_sandbox(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "sandbox"', self.deploy_run.stdout)

    def test_should_say_that_production_is_unchanged(self) -> None:
        self.assertIn("Production is unchanged", self.deploy_run.stdout)

    def test_should_tag_latest_the_images_that_production_runs_again(self) -> None:
        self.assertIn("tag scanmylib-ocr:deployed scanmylib-ocr:latest", self.commands)

    def test_should_check_no_sandbox(self) -> None:
        self.assertEqual([command for command in self.commands if re.search(SANDBOX_CHECK, command)], [])

    def test_should_back_up_nothing(self) -> None:
        self.assertEqual(self.backups, [])

    def test_should_neither_stop_nor_start_anything(self) -> None:
        self.assertEqual([command for command in self.commands if re.search(r" (up|stop) ", command)], [])

    def test_should_leave_the_running_sandbox_in_place(self) -> None:
        self.assertEqual(self.sandbox_manifest, REPLACED_MANIFEST)

    def test_should_keep_the_new_sandbox_for_its_log(self) -> None:
        self.assertTrue(self.is_new_sandbox_left)

    def test_should_say_how_to_read_its_log_and_remove_it(self) -> None:
        new_sandbox = f"{self.production_data}/sandbox.new"
        self.assertIn(f"cat -v {new_sandbox}/setup.log", self.deploy_run.stdout)
        self.assertIn(f"rm -rf {new_sandbox}", self.deploy_run.stdout)


class WhenTheFailedInstallationLeavesALinkForItsLog(InstallationTestCase):
    new_sandbox: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation_with_a_sandbox_to_replace(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.new_sandbox = installation.production_data / "sandbox.new"
        host_file = installation.production_data / "state" / "token"
        failing: Rule = {
            "match": INSTALL_SANDBOX,
            "exit": 1,
            "host_links": {f"{cls.new_sandbox}/setup.log": str(host_file)},
        }
        cls.deploy_run = deploy(installation, "--new-sandbox", rules=[failing])

    def test_should_fail_at_the_new_sandbox(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "sandbox"', self.deploy_run.stdout)

    def test_should_never_suggest_reading_a_file_of_the_host_through_the_link(self) -> None:
        self.assertNotIn(f"cat -v {self.new_sandbox}/setup.log", self.deploy_run.stdout)

    def test_should_say_how_to_remove_the_new_sandbox(self) -> None:
        self.assertIn(f"rm -rf {self.new_sandbox}", self.deploy_run.stdout)


class WhenTheNewImageFailsTheCheckOfTheNewSandbox(InstallationTestCase):
    new_sandbox: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    backups: ClassVar[list[str]]
    sandbox_manifest: ClassVar[str | None]
    new_sandbox_manifest: ClassVar[str | None]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation_with_a_sandbox_to_replace(cls)
        start_fake_api(cls, installation.production_api_port)
        sandbox = installation.production_data / "sandbox"
        cls.new_sandbox = Path(f"{sandbox}.new")
        rules: list[Rule] = [build_sandbox_installation(sandbox), {"match": SANDBOX_CHECK, "exit": 1}]
        cls.deploy_run = deploy(installation, "--new-sandbox", rules=rules)
        cls.commands = installation.read_docker_commands()
        cls.backups = list_backups(installation)
        cls.sandbox_manifest = read_text_if_present(sandbox / "MANIFEST.json")
        cls.new_sandbox_manifest = read_text_if_present(Path(f"{sandbox}.new") / "MANIFEST.json")

    def test_should_fail_at_the_check_of_the_sandbox(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "check"', self.deploy_run.stdout)

    def test_should_say_that_production_is_unchanged(self) -> None:
        self.assertIn("Production is unchanged", self.deploy_run.stdout)

    def test_should_back_up_nothing(self) -> None:
        self.assertEqual(self.backups, [])

    def test_should_neither_stop_nor_start_anything(self) -> None:
        self.assertEqual([command for command in self.commands if re.search(r" (up|stop) ", command)], [])

    def test_should_leave_the_running_sandbox_in_place(self) -> None:
        self.assertEqual(self.sandbox_manifest, REPLACED_MANIFEST)

    def test_should_keep_the_new_sandbox_aside(self) -> None:
        self.assertEqual(self.new_sandbox_manifest, NEW_MANIFEST)

    def test_should_not_suggest_the_option_it_was_given(self) -> None:
        self.assertNotIn("deploy with --new-sandbox", self.deploy_run.stdout)

    def test_should_say_that_the_new_image_could_not_import_the_engine_s_libraries_from_the_new_sandbox(self) -> None:
        self.assertIn(f"could not import the engine's libraries from {self.new_sandbox}.", self.deploy_run.stdout)

    def test_should_show_why_with_the_check_on_the_new_sandbox(self) -> None:
        self.assertRegex(
            self.deploy_run.stdout, rf"\n  docker run .*src={re.escape(str(self.new_sandbox))}\\,dst=/opt/sandbox"
        )

    def test_should_say_how_to_remove_the_new_sandbox_before_deploying_again(self) -> None:
        self.assertIn(f"rm -rf {self.new_sandbox}\n", self.deploy_run.stdout)


class WhenTheRestartFailsOnceTheSandboxesAreSwapped(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    rollback_moves: ClassVar[list[str]]
    sandbox_manifest_after_the_rollback: ClassVar[str | None]
    sandboxes_after_the_rollback: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation_with_a_sandbox_to_replace(cls)
        start_fake_api(cls, installation.production_api_port)
        sandbox = installation.production_data / "sandbox"
        rules: list[Rule] = [build_sandbox_installation(sandbox), {"match": r" up -d --no-build --wait", "exit": 1}]
        cls.deploy_run = deploy(installation, "--new-sandbox", rules=rules)
        rollback = cls.deploy_run.stdout.split("DEPLOY FAILED", 1)[-1]
        cls.rollback_moves = [line.strip() for line in rollback.splitlines() if line.startswith("  mv -T ")]
        for move in cls.rollback_moves:
            subprocess.run(shlex.split(move), check=True)
        cls.sandbox_manifest_after_the_rollback = read_text_if_present(sandbox / "MANIFEST.json")
        cls.sandboxes_after_the_rollback = sorted(
            re.sub(r"\d{8}-\d{6}", "<time>", path.name) for path in installation.production_data.glob("sandbox*")
        )

    def test_should_fail_at_the_restart(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "restart"', self.deploy_run.stdout)

    def test_should_print_the_two_moves_that_undo_the_swap(self) -> None:
        self.assertEqual(len(self.rollback_moves), 2, self.deploy_run.stdout)

    def test_should_put_the_replaced_sandbox_back_with_the_printed_moves(self) -> None:
        self.assertEqual(self.sandbox_manifest_after_the_rollback, REPLACED_MANIFEST)

    def test_should_keep_the_new_sandbox_aside_with_the_printed_moves(self) -> None:
        self.assertEqual(self.sandboxes_after_the_rollback, ["sandbox", "sandbox.failed-<time>"])


class WhenTheAppFailsToBuildOnceTheSandboxesAreSwapped(InstallationTestCase):
    production_data: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    replaced_sandboxes: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation_with_a_sandbox_to_replace(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.production_data = installation.production_data
        rules: list[Rule] = [
            build_sandbox_installation(installation.production_data / "sandbox"),
            {"match": "^run .*scanmylib-android-build", "exit": 1},
        ]
        cls.deploy_run = deploy(installation, "--apk", "--new-sandbox", rules=rules)
        cls.replaced_sandboxes = [path.name for path in installation.production_data.glob("sandbox.replaced-*")]

    def test_should_fail_at_the_app(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "apk"', self.deploy_run.stdout)

    def test_should_say_where_the_replaced_sandbox_is_kept_for_a_rollback(self) -> None:
        self.assertEqual(len(self.replaced_sandboxes), 1)
        self.assertIn(
            f"kept for a rollback in {self.production_data}/{self.replaced_sandboxes[0]}", self.deploy_run.stdout
        )


class WhenANewSandboxIsLeftFromAnEarlierDeployment(InstallationTestCase):
    deploy_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation_with_a_sandbox_to_replace(cls)
        start_fake_api(cls, installation.production_api_port)
        (installation.production_data / "sandbox.new").mkdir()
        (installation.production_data / "sandbox.new" / "setup.log").write_text(INSTALLATION_LOG)
        cls.deploy_run = deploy(installation, "--new-sandbox")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_and_say_how_to_read_it(self) -> None:
        self.assertNotEqual(self.deploy_run.returncode, 0)
        self.assertIn(
            "sandbox.new is left from an earlier installation: read its setup.log through cat -v",
            self.deploy_run.output,
        )

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


def point_the_sandbox_at_data_dir(installation: Installation) -> None:
    data_dir = str(installation.production_data)
    env = installation.build_production_env(SANDBOX_DIR=data_dir, SANDBOX_SETUP_DIR=data_dir)
    (installation.production_checkout / ".env").write_text(env)


def point_the_sandbox_at_library_dir(installation: Installation) -> None:
    library = str(installation.library)
    env = installation.build_production_env(SANDBOX_DIR=library, SANDBOX_SETUP_DIR=library)
    (installation.production_checkout / ".env").write_text(env)


def point_the_sandbox_at_the_checkout(installation: Installation) -> None:
    checkout = str(installation.production_checkout)
    env = installation.build_production_env(SANDBOX_DIR=checkout, SANDBOX_SETUP_DIR=checkout)
    (installation.production_checkout / ".env").write_text(env)


def put_the_signing_key_in_sandbox_dir(installation: Installation) -> None:
    keystore = installation.production_data / "sandbox" / "keystore"
    keystore.mkdir()
    env = installation.build_production_env(ANDROID_KEYSTORE_DIR=str(keystore))
    (installation.production_checkout / ".env").write_text(env)


def put_something_else_than_a_sandbox_in_sandbox_dir(installation: Installation) -> None:
    sandbox = installation.production_data / "sandbox"
    (sandbox / "MANIFEST.json").unlink()
    (sandbox / "notes.txt").write_text("not a sandbox")


class WhenANewSandboxWouldMoveWhatIsNotASandbox(InstallationTestCase):
    preconditions: ClassVar[Mapping[str, BrokenPrecondition]] = MappingProxyType(
        {
            "DATA_DIR as SANDBOX_DIR": BrokenPrecondition(point_the_sandbox_at_data_dir, "is or contains DATA_DIR"),
            "a SANDBOX_DIR that holds no sandbox": BrokenPrecondition(
                put_something_else_than_a_sandbox_in_sandbox_dir, "holds no MANIFEST.json and is not empty"
            ),
            "LIBRARY_DIR as SANDBOX_DIR": BrokenPrecondition(
                point_the_sandbox_at_library_dir, "is, contains or lies inside LIBRARY_DIR"
            ),
            "the checkout as SANDBOX_DIR": BrokenPrecondition(
                point_the_sandbox_at_the_checkout, "is, contains or lies inside the checkout"
            ),
            "a SANDBOX_DIR that holds the signing key": BrokenPrecondition(
                put_the_signing_key_in_sandbox_dir, "is, contains or lies inside ANDROID_KEYSTORE_DIR"
            ),
        }
    )
    deploy_runs: ClassVar[dict[str, ScriptRun]]
    writing_calls: ClassVar[dict[str, list[list[str]]]]
    is_database_in_place: ClassVar[dict[str, bool]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.deploy_runs, cls.writing_calls, cls.is_database_in_place = {}, {}, {}
        for row, broken_precondition in cls.preconditions.items():
            installation = make_installation_with_a_sandbox_to_replace(cls)
            start_fake_api(cls, installation.production_api_port)
            broken_precondition.break_it(installation)
            cls.deploy_runs[row] = deploy(installation, "--new-sandbox")
            cls.writing_calls[row] = list_writing_calls(installation.read_docker_calls())
            cls.is_database_in_place[row] = (installation.production_data / "state" / "scanmylib.db").is_file()

    def test_should_refuse_and_say_why(self) -> None:
        self.assertEqual(sorted(self.deploy_runs), sorted(self.preconditions))
        for row, deploy_run in self.deploy_runs.items():
            with self.subTest(row):
                self.assertNotEqual(deploy_run.returncode, 0)
                self.assertIn(self.preconditions[row].refusal, deploy_run.output)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(sorted(self.writing_calls), sorted(self.preconditions))
        for row, writing_calls in self.writing_calls.items():
            with self.subTest(row):
                self.assertEqual(writing_calls, [])

    def test_should_leave_production_s_database_in_place(self) -> None:
        self.assertEqual(self.is_database_in_place, dict.fromkeys(self.preconditions, True))


class WhenADeploymentWithANewSandboxIsADryRun(InstallationTestCase):
    production_data: ClassVar[Path]
    deploy_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]
    sandboxes: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation_with_a_sandbox_to_replace(cls)
        start_fake_api(cls, installation.production_api_port)
        cls.production_data = installation.production_data
        cls.deploy_run = deploy(installation, "--dry-run", "--new-sandbox")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())
        cls.sandboxes = sorted(path.name for path in installation.production_data.glob("sandbox*"))

    def test_should_succeed(self) -> None:
        self.assertEqual(self.deploy_run.returncode, 0, self.deploy_run.output)

    def test_should_say_that_it_would_install_the_new_sandbox_with_ocr_setup(self) -> None:
        self.assertIn(
            f"would run docker compose, with .env but SANDBOX_SETUP_DIR={self.production_data}/sandbox.new: "
            "--profile setup run --rm -T --pull never ocr-setup",
            self.deploy_run.stdout,
        )

    def test_should_say_that_it_would_check_the_new_image_against_the_new_sandbox(self) -> None:
        self.assertIn(f"src={self.production_data}/sandbox.new", self.deploy_run.stdout)

    def test_should_say_that_it_would_swap_the_sandboxes(self) -> None:
        self.assertRegex(
            self.deploy_run.stdout,
            rf"would run: mv -T {re.escape(str(self.production_data))}/sandbox "
            rf"{re.escape(str(self.production_data))}/sandbox\.replaced-\d{{8}}-\d{{6}}\n",
        )

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])

    def test_should_leave_the_sandboxes_as_they_were(self) -> None:
        self.assertEqual(self.sandboxes, ["sandbox"])


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
        self.assertNotIn(NEW_API_IMAGE_TAGGED_DEPLOYED, self.commands)

    def test_should_never_tag_the_release(self) -> None:
        self.assertEqual(self.tags, RELEASE_TAGS_ALONE)

    def test_should_not_check_the_engine_in_the_sandbox_that_is_not_isolated(self) -> None:
        execs = [command for command in self.commands if command.startswith("exec ")]
        self.assertEqual([command for command in execs if ENGINE_CHECK_MODULE in command], [])


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
        self.assertNotIn(NEW_API_IMAGE_TAGGED_DEPLOYED, self.commands)
        self.assertNotIn(NEW_OCR_IMAGE_TAGGED_DEPLOYED, self.commands)

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
        self.assertNotIn(NEW_API_IMAGE_TAGGED_DEPLOYED, self.commands)
        self.assertNotIn(NEW_OCR_IMAGE_TAGGED_DEPLOYED, self.commands)

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
            "a sandbox path with a comma": BrokenPrecondition(put_a_comma_in_the_sandbox_path, "without a comma"),
            "the sandbox run as root": BrokenPrecondition(run_the_sandbox_as_root, "SCANMYLIB_UID in .env must be"),
            "a group named by its name": BrokenPrecondition(
                run_the_sandbox_in_a_group_named_by_its_name, "SCANMYLIB_GID in .env must be"
            ),
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
        self.assertIn(f"tag {NEW_API_IMAGE_ID} {REHEARSAL_PROJECT}-api:deployed", self.commands)

    def test_should_tag_deployed_the_sandbox_image_it_built_since_the_fake_ocr_runs_none(self) -> None:
        self.assertIn(f"tag {REHEARSAL_PROJECT}-ocr:latest {REHEARSAL_PROJECT}-ocr:deployed", self.commands)

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


class WhenANewSandboxIsRehearsedOnProductionsSandbox(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]
    sandboxes: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls, ROOM_FOR_A_NEW_SANDBOX)
        write_rehearsal_env(installation, installation.directory / "rehearsal", find_free_port(), OCR_SERVICE="ocr")
        cls.rehearsal = rehearse(installation, "--new-sandbox")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())
        cls.sandboxes = sorted(path.name for path in installation.production_data.glob("sandbox*"))

    def test_should_refuse_since_the_sandbox_is_production_s(self) -> None:
        self.assertNotEqual(self.rehearsal.returncode, 0)
        self.assertIn("SANDBOX_DIR: ", self.rehearsal.stdout)
        self.assertIn("is production's SANDBOX_DIR", self.rehearsal.stdout)

    def test_should_refuse_before_anything_is_built_or_installed(self) -> None:
        self.assertEqual(self.writing_calls, [])

    def test_should_leave_production_s_sandbox_alone(self) -> None:
        self.assertEqual(self.sandboxes, ["sandbox"])


class WhenANewSandboxIsRehearsedOnTheStacksDataDir(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    is_new_sandbox_made: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        # The stack's DATA_DIR as its sandbox passes every check of .env, but the new sandbox would go next to it, and
        # the restart would move the stack's data.
        installation = make_installation(cls, ROOM_FOR_A_NEW_SANDBOX)
        rehearsal_data = installation.directory / "rehearsal"
        rehearsal_data.mkdir()
        write_rehearsal_env(
            installation, rehearsal_data, find_free_port(), OCR_SERVICE="ocr", SANDBOX_DIR=str(rehearsal_data)
        )
        installation.answer_docker([NEW_OCR_IMAGE])
        cls.rehearsal = rehearse(installation, "--new-sandbox")
        cls.commands = installation.read_docker_commands()
        cls.is_new_sandbox_made = Path(f"{rehearsal_data}.new").exists()

    def test_should_refuse_since_sandbox_dir_is_the_stack_s_data_dir(self) -> None:
        self.assertNotEqual(self.rehearsal.returncode, 0)
        self.assertIn("is or contains DATA_DIR", self.rehearsal.output)

    def test_should_refuse_before_ocr_setup_runs(self) -> None:
        self.assertEqual([command for command in self.commands if re.search(INSTALL_SANDBOX, command)], [])

    def test_should_make_no_new_sandbox(self) -> None:
        self.assertFalse(self.is_new_sandbox_made)


class WhenTheCopyOfEnvThatInstallsANewSandboxReachesOutsideTheStacksData(InstallationTestCase):
    outside: ClassVar[Path]
    rehearsal: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    is_new_sandbox_made: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        # The stack's own .env passes, but docker compose, given the copy that sets SANDBOX_SETUP_DIR, resolves an
        # ocr-setup that mounts a directory outside the stack's DATA_DIR.
        installation = make_installation(cls, ROOM_FOR_A_NEW_SANDBOX)
        api_port = find_free_port()
        start_fake_api(cls, api_port)
        rehearsal_data = installation.directory / "rehearsal"
        sandbox = rehearsal_data / "sandbox"
        sandbox.mkdir(parents=True)
        cls.outside = installation.directory / "outside"
        cls.outside.mkdir()
        write_rehearsal_env(installation, rehearsal_data, api_port, OCR_SERVICE="ocr", SANDBOX_DIR=str(sandbox))
        ocr_setup = {
            "image": f"{REHEARSAL_PROJECT}-ocr:latest",
            "network_mode": "none",
            "volumes": [{"type": "bind", "source": str(cls.outside), "target": "/opt/sandbox"}],
        }
        resolved = json.dumps({"name": REHEARSAL_PROJECT, "services": {"ocr-setup": ocr_setup}})
        installation.answer_docker(
            [
                {"match": r"--env-file \S*/scanmylib-env\.\w+ .*config (--no-interpolate )?--format json$",
                 "stdout": resolved},
                NEW_OCR_IMAGE,
                *build_running_sandbox_rules(str(sandbox), str(rehearsal_data)),
            ]
        )  # fmt: skip
        cls.rehearsal = rehearse(installation, "--new-sandbox")
        cls.commands = installation.read_docker_commands()
        cls.is_new_sandbox_made = Path(f"{sandbox}.new").exists()

    def test_should_refuse_since_the_copy_is_not_isolated_from_production(self) -> None:
        self.assertNotEqual(self.rehearsal.returncode, 0)
        self.assertIn("the copy of .env that installs the new sandbox is not isolated", self.rehearsal.output)

    def test_should_name_the_mount_outside_the_stack_s_data(self) -> None:
        self.assertIn(f"bind mount {self.outside} -> /opt/sandbox", self.rehearsal.output)

    def test_should_refuse_before_ocr_setup_runs(self) -> None:
        self.assertEqual([command for command in self.commands if re.search(INSTALL_SANDBOX, command)], [])

    def test_should_make_no_new_sandbox(self) -> None:
        self.assertFalse(self.is_new_sandbox_made)


class WhenANewSandboxIsRehearsedOnTheStacksOwnSandbox(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]
    sandbox_manifest: ClassVar[str | None]
    replaced_sandboxes: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls, ROOM_FOR_A_NEW_SANDBOX)
        api_port = find_free_port()
        start_fake_api(cls, api_port)
        rehearsal_data = installation.directory / "rehearsal"
        sandbox = rehearsal_data / "sandbox"
        sandbox.mkdir(parents=True)
        write_rehearsal_env(installation, rehearsal_data, api_port, OCR_SERVICE="ocr", SANDBOX_DIR=str(sandbox))
        installation.answer_docker(
            [
                build_sandbox_installation(sandbox),
                NEW_OCR_IMAGE,
                *build_running_sandbox_rules(str(sandbox), str(rehearsal_data)),
            ]
        )
        cls.rehearsal = rehearse(installation, "--new-sandbox")
        cls.commands = installation.read_docker_commands()
        cls.sandbox_manifest = read_text_if_present(sandbox / "MANIFEST.json")
        cls.replaced_sandboxes = [path.name for path in rehearsal_data.glob("sandbox.replaced-*")]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.rehearsal.returncode, 0, self.rehearsal.output)

    def test_should_check_that_its_sandboxes_are_not_production_s(self) -> None:
        self.assertIn("the rehearsal's sandboxes are not production's", self.rehearsal.stdout)

    def test_should_check_that_the_copy_of_env_shares_nothing_with_production_before_ocr_setup_runs(self) -> None:
        stdout = self.rehearsal.stdout
        copy_checked = stdout.index("the copy of .env that installs the new sandbox shares nothing with production")
        self.assertLess(copy_checked, stdout.index("--profile setup run --rm -T --pull never ocr-setup"))

    def test_should_run_the_new_sandbox_in_sandbox_dir(self) -> None:
        self.assertEqual(self.sandbox_manifest, NEW_MANIFEST)

    def test_should_keep_the_stack_s_empty_sandbox_aside(self) -> None:
        self.assertEqual(len(self.replaced_sandboxes), 1)

    def test_should_say_to_deploy_the_previous_release_again_as_a_rehearsal(self) -> None:
        command = f"\n  SCANMYLIB_DEPLOY_REHEARSAL={REHEARSAL_PROJECT} scripts/deploy.sh --allow-downgrade\n"
        self.assertIn(command, self.rehearsal.stdout)


class WhenANewSandboxIsRehearsedOnTheFakeOcr(InstallationTestCase):
    rehearsal: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls, ROOM_FOR_A_NEW_SANDBOX)
        write_rehearsal_env(installation, installation.directory / "rehearsal", find_free_port())
        cls.rehearsal = rehearse(installation, "--new-sandbox")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_the_fake_ocr_runs_no_sandbox(self) -> None:
        self.assertNotEqual(self.rehearsal.returncode, 0)
        self.assertIn(
            "--new-sandbox installs the OCR sandbox, which OCR_SERVICE=ocr-fake does not run", self.rehearsal.output
        )

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


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
