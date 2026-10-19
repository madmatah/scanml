"""The build of the Android app (scripts/build-apk.sh), in throwaway installations (installation_support.py), whose
docker stand-in only logs the containers that would build and sign it.

Needs git, bash, flock and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_build_apk.py'
"""

from __future__ import annotations

import fcntl
import json
import os
import queue
import re
import signal
import subprocess
import tempfile
import threading
import time
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from installation_support import (
    DEV_VERSION,
    REPO,
    VERSION,
    VERSION_CODE,
    Installation,
    InstallationTestCase,
    ScriptRun,
    UncleanCheckout,
    make_installation,
    read_text_if_present,
)

SHA256 = "0123456789abcdef" * 4
LONGEST_VERSION_NAME = "0.2.4-dev+g" + "a" * 53
DEVELOPMENT_VERSION_CODE = "416057"
RELEASE_VERSION_CODE = "10203"
APK_SIZE_BYTES = "4567"


@dataclass(frozen=True)
class RunningScript:
    process: subprocess.Popen[str]
    lines: queue.Queue[str | None]


def list_docker_runs(installation: Installation) -> list[str]:
    return [command for command in installation.read_docker_commands() if command.startswith("run ")]


def read_environment_value(command: str, name: str) -> str:
    found = re.search(rf"--env {name}=(\S+) ", command)
    return found[1] if found else ""


def read_first_version_code(docker_runs: list[str]) -> int:
    """The version code of the first build, or 0 when it ran no container: the tests of the next build then fail and
    show its output, where an error here would hide it."""
    version_code = read_environment_value(" ".join(docker_runs[:1]), "SCANMYLIB_DEV_VERSION_CODE")
    return int(version_code) if version_code.isdecimal() else 0


def start_script(test_case: type[unittest.TestCase], installation: Installation, script: str) -> RunningScript:
    process = subprocess.Popen(
        [str(installation.worktree / "scripts" / script)],
        cwd=installation.worktree,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=installation.build_environment(),
        start_new_session=True,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def read_lines() -> None:
        # A thread rather than select(): a line already read into the pipe's buffer would never wake select().
        for line in process.stdout or ():
            lines.put(line)
        lines.put(None)

    threading.Thread(target=read_lines, daemon=True).start()
    running = RunningScript(process, lines)
    test_case.addClassCleanup(stop_script, running)
    return running


def read_output_until(running: RunningScript, expected: str, idle_seconds: float = 60) -> str:
    output = ""
    while expected not in output:
        try:
            line = running.lines.get(timeout=idle_seconds)
        except queue.Empty:
            return output
        if line is None:
            # The end of the output stays there for the next read.
            running.lines.put(None)
            return output
        output += line
    return output


def is_waiting_on(running: RunningScript, command: str, search_seconds: float = 60) -> bool:
    deadline_seconds = time.monotonic() + search_seconds
    while time.monotonic() < deadline_seconds:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / "stat").read_text()
            except OSError:
                # The process ended since the directory was listed, or belongs to someone the system hides.
                continue
            # pid (comm) state ppid pgrp session: comm may hold spaces and parentheses.
            name = stat[stat.index("(") + 1 : stat.rindex(")")]
            session = int(stat[stat.rindex(")") + 2 :].split()[3])
            if name == command and session == running.process.pid:
                return True
        time.sleep(0.05)
    return False


def stop_script(running: RunningScript) -> None:
    # The whole session: the script and what it waits on, such as flock.
    if running.process.poll() is None:
        os.killpg(running.process.pid, signal.SIGTERM)
    running.process.wait(timeout=60)
    if running.process.stdout is not None:
        running.process.stdout.close()


def write_apk_metadata(file: Path, *fields: str) -> ScriptRun:
    """Runs write_apk_metadata of build-apk.sh, as the signing container does, in its locale."""
    script = (REPO / "scripts" / "build-apk.sh").read_text()
    function = script[script.index("write_apk_metadata() {") :]
    function = function[: function.index("\n}\n") + 3]
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'die() { echo "error: $*" >&2; exit 1; }\n' + function + '\nwrite_apk_metadata "$@"',
            "bash",
            str(file),
            *fields,
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "en_US.UTF-8"},
    )
    return ScriptRun(completed.returncode, completed.stdout, completed.stderr)


def parse_metadata(metadata_text: str | None) -> dict[str, object]:
    if metadata_text is None:
        raise FileNotFoundError("write_apk_metadata wrote no metadata")
    metadata: dict[str, object] = json.loads(metadata_text)
    return metadata


def make_metadata_directory(test_case: type[unittest.TestCase]) -> Path:
    directory = tempfile.TemporaryDirectory(prefix="scanmylib-metadata-")
    test_case.addClassCleanup(directory.cleanup)
    return Path(directory.name)


def add_a_stray_file(installation: Installation) -> None:
    sources = installation.production_checkout / "android" / "app" / "src"
    sources.mkdir(parents=True)
    (sources / "stray.jks").write_bytes(b"key")


def hide_a_change_with_assume_unchanged(installation: Installation) -> None:
    installation.run_git(installation.production_checkout, "update-index", "--assume-unchanged", "VERSION")
    (installation.production_checkout / "VERSION").write_text("9.9.9\n")


def remove_the_signing_key(installation: Installation) -> None:
    for name in ("scanmylib-release.p12", "password"):
        (installation.production_data / "android" / "keystore" / name).unlink()


class WhenAWorktreeBuilds(InstallationTestCase):
    #: A development build's versionCode, from the time of the build, is above every release's (scripts/lib/version.py).
    development_version_code_floor: ClassVar[int] = 400_000
    production_data: ClassVar[Path]
    development_data: ClassVar[Path]
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.production_data = installation.production_data
        cls.development_data = installation.development_data
        (installation.worktree / ".env").write_text(installation.build_development_env())
        # What would turn this into a release build in production's directories, without a .env.
        release_settings = {
            "APP_VARIANT": "release",
            "DATA_DIR": str(cls.production_data),
            "ANDROID_DIR": f"{cls.production_data}/android",
        }
        cls.build_apk_run = installation.run_script(installation.worktree, "build-apk.sh", environment=release_settings)
        cls.docker_runs = list_docker_runs(installation)

    def read_version_name(self) -> str:
        return read_environment_value(self.docker_runs[0], "SCANMYLIB_DEV_VERSION_NAME")

    def read_version_code(self) -> str:
        return read_environment_value(self.docker_runs[0], "SCANMYLIB_DEV_VERSION_CODE")

    def test_should_succeed(self) -> None:
        self.assertEqual(self.build_apk_run.returncode, 0, self.build_apk_run.output)

    def test_should_run_a_build_then_a_signing_container(self) -> None:
        self.assertEqual(len(self.docker_runs), 2)

    def test_should_build_the_dev_app_whatever_the_caller_s_environment_says(self) -> None:
        self.assertIn("assembleDev", self.docker_runs[0])

    def test_should_build_with_the_android_sdk_of_the_stack(self) -> None:
        self.assertIn(f"{self.development_data}/android/sdk:/opt/android-sdk", self.docker_runs[0])

    def test_should_build_with_the_gradle_caches_of_the_stack(self) -> None:
        self.assertIn(f"{self.development_data}/android/gradle:/gradle", self.docker_runs[0])

    def test_should_mount_nothing_of_production_into_the_build(self) -> None:
        self.assertNotIn(f"{self.production_data}/", self.docker_runs[0].replace(f"{self.development_data}/", ""))

    def test_should_sign_without_network(self) -> None:
        self.assertIn("--network none", self.docker_runs[1])

    def test_should_sign_with_production_s_key_read_only(self) -> None:
        self.assertIn(f"{self.production_data}/android/keystore:/keystore:ro", self.docker_runs[1])

    def test_should_sign_with_the_build_tools_of_the_stack_read_only(self) -> None:
        self.assertIn(f"{self.development_data}/android/sdk/build-tools/36.0.0:/build-tools:ro", self.docker_runs[1])

    def test_should_publish_the_app_in_the_data_of_the_stack(self) -> None:
        self.assertIn(f"{self.development_data}/app:/out", self.docker_runs[1])

    def test_should_sign_the_dev_variant(self) -> None:
        self.assertIn("APP_VARIANT=dev", self.docker_runs[1])

    def test_should_take_the_version_of_a_development_build_from_git(self) -> None:
        self.assertRegex(self.read_version_name(), rf"^{DEV_VERSION}$")

    def test_should_take_the_version_code_from_the_time_of_the_build(self) -> None:
        version_code = self.read_version_code()
        self.assertRegex(version_code, "^[0-9]+$")
        self.assertGreater(int(version_code), self.development_version_code_floor)

    def test_should_print_the_version_and_version_code_it_builds(self) -> None:
        printed = f"Version {self.read_version_name()} (versionCode {self.read_version_code()})"
        self.assertIn(printed, self.build_apk_run.stdout)

    def test_should_have_the_signer_refuse_any_other_app_than_the_dev_app(self) -> None:
        self.assertIn("EXPECTED_PACKAGE=fr.scanmylib.dev ", self.docker_runs[1])

    def test_should_have_the_signer_refuse_any_other_version_code_than_the_one_it_built(self) -> None:
        self.assertIn(f"EXPECTED_VERSION_CODE={self.read_version_code()} ", self.docker_runs[1])

    def test_should_hand_the_signer_the_definition_of_the_identity_check_not_only_its_call(self) -> None:
        # "declare -f" prints the definitions, as "name () ", where sign_main only calls them.
        self.assertIn("apk_identity () ", self.docker_runs[1])

    def test_should_publish_the_version_next_to_the_app_for_the_health_of_the_api(self) -> None:
        self.assertIn(f"EXPECTED_VERSION_NAME={self.read_version_name()} ", self.docker_runs[1])

    def test_should_hand_the_signer_the_definition_of_the_metadata_writer_not_only_its_call(self) -> None:
        self.assertIn("write_apk_metadata () ", self.docker_runs[1])


class WhenAWorktreeBuildsAgainWithUncommittedChanges(InstallationTestCase):
    published_version_code: ClassVar[int]
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        worktree = installation.worktree
        (worktree / ".env").write_text(installation.build_development_env())
        installation.run_script(worktree, "build-apk.sh")
        # Published within the same minute, ahead of the version code that the time of the next build gives.
        cls.published_version_code = read_first_version_code(list_docker_runs(installation)) + 5
        (worktree / "VERSION").write_text(VERSION + "\n\n")
        metadata_file = installation.development_data / "app" / "scanmylib.json"
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        metadata_file.write_text(json.dumps({"version_code": cls.published_version_code}))
        installation.forget_docker_calls()
        cls.build_apk_run = installation.run_script(worktree, "build-apk.sh")
        cls.docker_runs = list_docker_runs(installation)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.build_apk_run.returncode, 0, self.build_apk_run.output)

    def test_should_run_a_build_then_a_signing_container(self) -> None:
        self.assertEqual(len(self.docker_runs), 2)

    def test_should_say_in_the_version_that_the_build_holds_uncommitted_changes(self) -> None:
        version_name = read_environment_value(self.docker_runs[0], "SCANMYLIB_DEV_VERSION_NAME")
        self.assertRegex(version_name, rf"^{DEV_VERSION}\.dirty$")

    def test_should_install_over_the_published_app_even_within_the_same_minute(self) -> None:
        self.assertIn(f"EXPECTED_VERSION_CODE={self.published_version_code + 1} ", self.docker_runs[1])


class WhenACheckoutOtherThanProductionsAsksForTheReleaseApp(InstallationTestCase):
    expected_refusals: ClassVar[dict[str, str]]
    build_apk_runs: ClassVar[dict[str, ScriptRun]]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        worktree = installation.worktree
        only_in_production = f"only built in production's checkout ({installation.production_checkout})"
        cls.expected_refusals = {
            "a worktree whose .env asks for it": "production's checkout",
            "a worktree with a copy of production's .env": only_in_production,
            "another clone with a copy of production's .env": only_in_production,
        }
        cls.build_apk_runs = {}
        (worktree / ".env").write_text(installation.build_development_env(APP_VARIANT="release"))
        cls.build_apk_runs["a worktree whose .env asks for it"] = installation.run_script(worktree, "build-apk.sh")
        (worktree / ".env").write_text(installation.build_production_env())
        cls.build_apk_runs["a worktree with a copy of production's .env"] = installation.run_script(
            worktree, "build-apk.sh"
        )
        cls.build_apk_runs["another clone with a copy of production's .env"] = installation.run_script(
            installation.make_clone(), "build-apk.sh"
        )
        cls.docker_runs = list_docker_runs(installation)

    def test_should_refuse_and_say_why(self) -> None:
        self.assertEqual(sorted(self.build_apk_runs), sorted(self.expected_refusals))
        for row, build_apk_run in self.build_apk_runs.items():
            with self.subTest(row):
                self.assertNotEqual(build_apk_run.returncode, 0)
                self.assertIn(self.expected_refusals[row], build_apk_run.stderr)

    def test_should_run_no_container(self) -> None:
        self.assertEqual(self.docker_runs, [])


class WhenProductionsCheckoutBuildsThePublishedRelease(InstallationTestCase):
    production_data: ClassVar[Path]
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.production_data = installation.production_data
        cls.build_apk_run = installation.run_script(installation.production_checkout, "build-apk.sh")
        cls.docker_runs = list_docker_runs(installation)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.build_apk_run.returncode, 0, self.build_apk_run.output)

    def test_should_run_a_build_then_a_signing_container(self) -> None:
        self.assertEqual(len(self.docker_runs), 2)

    def test_should_build_the_release_app(self) -> None:
        self.assertIn("assembleRelease", self.docker_runs[0])

    def test_should_take_the_version_of_the_release_which_the_build_reads_itself(self) -> None:
        self.assertNotIn("SCANMYLIB_DEV_VERSION", self.docker_runs[0])

    def test_should_sign_with_production_s_key_read_only(self) -> None:
        self.assertIn(f"{self.production_data}/android/keystore:/keystore:ro", self.docker_runs[1])

    def test_should_have_the_signer_refuse_any_other_app_than_the_production_app(self) -> None:
        self.assertIn("EXPECTED_PACKAGE=fr.scanmylib ", self.docker_runs[1])

    def test_should_have_the_signer_refuse_any_other_version_code_than_the_release_s(self) -> None:
        self.assertIn(f"EXPECTED_VERSION_CODE={VERSION_CODE} ", self.docker_runs[1])

    def test_should_publish_the_version_of_the_release(self) -> None:
        self.assertIn(f"EXPECTED_VERSION_NAME={VERSION} ", self.docker_runs[1])


class WhenProductionsCheckoutIsNotTheCleanPublishedRelease(InstallationTestCase):
    unclean_checkouts: ClassVar[Mapping[str, UncleanCheckout]] = MappingProxyType(
        {
            "a stray file": UncleanCheckout(add_a_stray_file, "could end up in the release app"),
            "an untracked file": UncleanCheckout(Installation.add_an_untracked_file, "clean checkout"),
            "a hidden change": UncleanCheckout(
                hide_a_change_with_assume_unchanged, "assume-unchanged or skip-worktree"
            ),
            "a commit after the release": UncleanCheckout(
                Installation.commit_after_the_release, "built from a published release only: HEAD"
            ),
            "a release not published": UncleanCheckout(
                Installation.unpublish_the_release, f"v{VERSION} is not published on origin"
            ),
        }
    )
    build_apk_runs: ClassVar[dict[str, ScriptRun]]
    docker_runs: ClassVar[dict[str, list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.build_apk_runs, cls.docker_runs = {}, {}
        for row, unclean_checkout in cls.unclean_checkouts.items():
            installation = make_installation(cls)
            unclean_checkout.make_unclean(installation)
            cls.build_apk_runs[row] = installation.run_script(installation.production_checkout, "build-apk.sh")
            cls.docker_runs[row] = list_docker_runs(installation)

    def test_should_refuse_and_say_why(self) -> None:
        self.assertEqual(sorted(self.build_apk_runs), sorted(self.unclean_checkouts))
        for row, build_apk_run in self.build_apk_runs.items():
            with self.subTest(row):
                self.assertNotEqual(build_apk_run.returncode, 0)
                self.assertIn(self.unclean_checkouts[row].refusal, build_apk_run.stderr)

    def test_should_run_no_container(self) -> None:
        self.assertEqual(self.docker_runs, {row: [] for row in self.unclean_checkouts})


class WhenProductionHasNoSigningKey(InstallationTestCase):
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        remove_the_signing_key(installation)
        cls.build_apk_run = installation.run_script(installation.production_checkout, "build-apk.sh")
        cls.docker_runs = list_docker_runs(installation)

    def test_should_refuse_since_only_a_request_creates_the_key(self) -> None:
        self.assertNotEqual(self.build_apk_run.returncode, 0)
        self.assertIn("no signing key", self.build_apk_run.stderr)

    def test_should_run_no_container(self) -> None:
        self.assertEqual(self.docker_runs, [])


class WhenProductionAsksToCreateItsSigningKey(InstallationTestCase):
    keystore: ClassVar[Path]
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.keystore = installation.production_data / "android" / "keystore"
        remove_the_signing_key(installation)
        cls.build_apk_run = installation.run_script(
            installation.production_checkout, "build-apk.sh", "--create-signing-key"
        )
        cls.docker_runs = list_docker_runs(installation)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.build_apk_run.returncode, 0, self.build_apk_run.output)

    def test_should_run_a_build_then_a_container_that_creates_the_key_then_a_signing_one(self) -> None:
        self.assertEqual(len(self.docker_runs), 3)

    def test_should_mount_production_s_keystore_writable_to_create_the_key(self) -> None:
        self.assertIn(f"{self.keystore}:/keystore ", self.docker_runs[1] + " ")

    def test_should_create_the_key_without_network(self) -> None:
        self.assertIn("--network none", self.docker_runs[1])

    def test_should_sign_with_the_key_read_only(self) -> None:
        self.assertIn(f"{self.keystore}:/keystore:ro", self.docker_runs[2])


class WhenAWorktreeAsksToCreateTheSigningKey(InstallationTestCase):
    build_apk_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        remove_the_signing_key(installation)
        (installation.worktree / ".env").write_text(installation.build_development_env())
        cls.build_apk_run = installation.run_script(installation.worktree, "build-apk.sh", "--create-signing-key")

    def test_should_refuse_since_only_production_creates_the_key(self) -> None:
        self.assertNotEqual(self.build_apk_run.returncode, 0)
        self.assertIn("only production creates the signing key", self.build_apk_run.stderr)


class WhenThereIsNoEnvOutsideCi(InstallationTestCase):
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        settings = {"DATA_DIR": str(installation.directory / "ci")}
        cls.build_apk_run = installation.run_script(
            installation.worktree, "build-apk.sh", "test", "lint", environment=settings
        )
        cls.docker_runs = list_docker_runs(installation)

    def test_should_refuse_since_only_ci_builds_without_one(self) -> None:
        self.assertNotEqual(self.build_apk_run.returncode, 0)
        self.assertIn("only CI builds", self.build_apk_run.stderr)

    def test_should_run_no_container(self) -> None:
        self.assertEqual(self.docker_runs, [])


class WhenCiBuildsWithoutEnv(InstallationTestCase):
    ci_data: ClassVar[Path]
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.ci_data = installation.directory / "ci"
        settings = {"DATA_DIR": str(cls.ci_data), "CI": "true"}
        cls.build_apk_run = installation.run_script(installation.worktree, "build-apk.sh", environment=settings)
        cls.docker_runs = list_docker_runs(installation)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.build_apk_run.returncode, 0, self.build_apk_run.output)

    def test_should_say_the_app_is_never_published(self) -> None:
        self.assertIn("never published", self.build_apk_run.stdout)

    def test_should_build_and_never_sign(self) -> None:
        self.assertEqual(len(self.docker_runs), 1)

    def test_should_build_with_the_android_sdk_of_its_data_dir(self) -> None:
        self.assertIn(f"{self.ci_data}/android/sdk:/opt/android-sdk", self.docker_runs[0])


class WhenCiBuildsWithoutEnvOnProductionsDirectories(InstallationTestCase):
    expected_refusals: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "production's DATA_DIR": "is production's DATA_DIR",
            "production's ANDROID_DIR": "is production's ANDROID_DIR",
            "a DATA_DIR that contains production's": "contains production's DATA_DIR",
        }
    )
    build_apk_runs: ClassVar[dict[str, ScriptRun]]
    docker_runs: ClassVar[dict[str, list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        production_data = str(installation.production_data)
        ci_data = str(installation.directory / "ci")
        settings = {
            "production's DATA_DIR": {"DATA_DIR": production_data},
            "production's ANDROID_DIR": {"DATA_DIR": ci_data, "ANDROID_DIR": f"{production_data}/android"},
            "a DATA_DIR that contains production's": {"DATA_DIR": str(installation.directory)},
        }
        cls.build_apk_runs, cls.docker_runs = {}, {}
        for row, row_settings in settings.items():
            installation.forget_docker_calls()
            cls.build_apk_runs[row] = installation.run_script(
                installation.worktree,
                "build-apk.sh",
                "test",
                "lint",
                environment={"GITHUB_ACTIONS": "true", **row_settings},
            )
            cls.docker_runs[row] = list_docker_runs(installation)

    def test_should_refuse_and_say_why_so_that_a_networked_build_never_writes_to_production_s_toolchain_or_data(
        self,
    ) -> None:
        self.assertEqual(sorted(self.build_apk_runs), sorted(self.expected_refusals))
        for row, build_apk_run in self.build_apk_runs.items():
            with self.subTest(row):
                self.assertNotEqual(build_apk_run.returncode, 0)
                self.assertIn(self.expected_refusals[row], build_apk_run.stderr)

    def test_should_run_no_container_that_would_mount_them(self) -> None:
        self.assertEqual(self.docker_runs, {row: [] for row in self.expected_refusals})


class WhenCiOnAWorkstationBuildsInTheHomeDirectory(InstallationTestCase):
    android: ClassVar[Path]
    build_apk_run: ClassVar[ScriptRun]
    is_android_created: ClassVar[bool]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.android = installation.home / "android-ci"
        settings = {"CI": "true", "DATA_DIR": str(installation.directory / "ci"), "ANDROID_DIR": str(cls.android)}
        cls.build_apk_run = installation.run_script(
            installation.worktree, "build-apk.sh", "test", "lint", environment=settings
        )
        cls.is_android_created = cls.android.exists()
        cls.docker_runs = list_docker_runs(installation)

    def test_should_refuse_and_name_the_directory(self) -> None:
        self.assertNotEqual(self.build_apk_run.returncode, 0)
        self.assertIn(f"ANDROID_DIR: {self.android} is inside your home directory", self.build_apk_run.stderr)

    def test_should_create_nothing_there(self) -> None:
        self.assertFalse(self.is_android_created)

    def test_should_run_no_container(self) -> None:
        self.assertEqual(self.docker_runs, [])


class WhenGitHubActionsBuildsInItsRunnerTemporaryDirectory(InstallationTestCase):
    runner_temporary_directory: ClassVar[Path]
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        # GitHub Actions keeps RUNNER_TEMP in the runner's home directory.
        installation = make_installation(cls)
        cls.runner_temporary_directory = installation.home / "work" / "_temp"
        settings = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_TEMP": str(cls.runner_temporary_directory),
            "DATA_DIR": str(cls.runner_temporary_directory / "data"),
        }
        cls.build_apk_run = installation.run_script(
            installation.worktree, "build-apk.sh", "test", "lint", environment=settings
        )
        cls.docker_runs = list_docker_runs(installation)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.build_apk_run.returncode, 0, self.build_apk_run.output)

    def test_should_build_with_the_android_sdk_there(self) -> None:
        self.assertIn(f"{self.runner_temporary_directory}/data/android/sdk:/opt/android-sdk", self.docker_runs[0])


class WhenGitHubActionsBuildsInTheHomeDirectoryOutsideItsRunnerTemporaryDirectory(InstallationTestCase):
    build_apk_run: ClassVar[ScriptRun]
    docker_runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        runner_temporary_directory = installation.home / "work" / "_temp"
        settings = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_TEMP": str(runner_temporary_directory),
            "DATA_DIR": str(runner_temporary_directory / "data"),
            "ANDROID_DIR": str(installation.home / "android-ci"),
        }
        cls.build_apk_run = installation.run_script(
            installation.worktree, "build-apk.sh", "test", "lint", environment=settings
        )
        cls.docker_runs = list_docker_runs(installation)

    def test_should_refuse_since_it_is_inside_the_home_directory(self) -> None:
        self.assertNotEqual(self.build_apk_run.returncode, 0)
        self.assertIn("is inside your home directory", self.build_apk_run.stderr)

    def test_should_run_no_container(self) -> None:
        self.assertEqual(self.docker_runs, [])


class WhenAnotherBuildHoldsTheToolchain(InstallationTestCase):
    output_while_locked: ClassVar[str]
    is_waiting_on_the_lock: ClassVar[bool]
    docker_runs_while_locked: ClassVar[list[str]]
    output_once_released: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.worktree / ".env").write_text(installation.build_development_env())
        android = installation.development_data / "android"
        android.mkdir(parents=True)
        lock = os.open(android, os.O_RDONLY)
        cls.addClassCleanup(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build = start_script(cls, installation, "build-apk.sh")
        cls.output_while_locked = read_output_until(build, "Waiting for another build")
        cls.is_waiting_on_the_lock = is_waiting_on(build, "flock")
        cls.docker_runs_while_locked = list_docker_runs(installation)
        fcntl.flock(lock, fcntl.LOCK_UN)
        cls.output_once_released = read_output_until(build, "Version ")

    def test_should_say_it_waits_for_another_build(self) -> None:
        self.assertIn("Waiting for another build", self.output_while_locked)

    def test_should_wait_on_the_lock_of_the_toolchain(self) -> None:
        self.assertTrue(self.is_waiting_on_the_lock)

    def test_should_run_no_container_while_it_waits(self) -> None:
        self.assertEqual(self.docker_runs_while_locked, [])

    def test_should_build_once_the_lock_is_released(self) -> None:
        self.assertIn("Version ", self.output_once_released)


class TheWriteApkMetadataFunctionWhenTheVersionIsADevelopmentOne(unittest.TestCase):
    version_names: ClassVar[tuple[str, ...]] = (
        "0.2.4-dev.27+g1a2b3c4d5e6f",
        "0.2.4-dev+g1a2b3c4d5e6f.dirty",
        "0.2.4-dev",
        LONGEST_VERSION_NAME,
    )
    metadata_writes: ClassVar[dict[str, ScriptRun]]
    metadata_texts: ClassVar[dict[str, str | None]]
    directory_entries: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        directory = make_metadata_directory(cls)
        metadata_file = directory / ".scanmylib.json.partial"
        cls.metadata_writes, cls.metadata_texts = {}, {}
        for version_name in cls.version_names:
            cls.metadata_writes[version_name] = write_apk_metadata(
                metadata_file, "fr.scanmylib.dev", version_name, DEVELOPMENT_VERSION_CODE, SHA256, APK_SIZE_BYTES
            )
            cls.metadata_texts[version_name] = read_text_if_present(metadata_file)
        cls.directory_entries = sorted(path.name for path in directory.iterdir())

    def test_should_accept_it(self) -> None:
        self.assertEqual(sorted(self.metadata_writes), sorted(self.version_names))
        for version_name, metadata_write in self.metadata_writes.items():
            with self.subTest(version_name):
                self.assertEqual(metadata_write.returncode, 0, metadata_write.stderr)

    def test_should_write_it_as_it_is(self) -> None:
        written_version_names = {
            name: parse_metadata(text)["version_name"] for name, text in self.metadata_texts.items()
        }
        self.assertEqual(written_version_names, {name: name for name in self.version_names})

    def test_should_write_no_other_file(self) -> None:
        self.assertEqual(self.directory_entries, [".scanmylib.json.partial"])


class TheWriteApkMetadataFunctionWhenTheVersionIsARelease(unittest.TestCase):
    metadata_write: ClassVar[ScriptRun]
    metadata_text: ClassVar[str | None]
    directory_entries: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        directory = make_metadata_directory(cls)
        metadata_file = directory / ".scanmylib.json.partial"
        cls.metadata_write = write_apk_metadata(
            metadata_file, "fr.scanmylib.dev", "1.2.3", RELEASE_VERSION_CODE, SHA256, APK_SIZE_BYTES
        )
        cls.metadata_text = read_text_if_present(metadata_file)
        cls.directory_entries = sorted(path.name for path in directory.iterdir())

    def test_should_succeed(self) -> None:
        self.assertEqual(self.metadata_write.returncode, 0, self.metadata_write.stderr)

    def test_should_write_every_field_as_json(self) -> None:
        self.assertEqual(
            parse_metadata(self.metadata_text),
            {
                "application_id": "fr.scanmylib.dev",
                "version_name": "1.2.3",
                "version_code": int(RELEASE_VERSION_CODE),
                "sha256": SHA256,
                "size": int(APK_SIZE_BYTES),
            },
        )

    def test_should_write_no_other_file(self) -> None:
        self.assertEqual(self.directory_entries, [".scanmylib.json.partial"])


class TheWriteApkMetadataFunctionWhenAValueCouldBreakTheJsonOrMisleadTheApp(unittest.TestCase):
    refused_fields: ClassVar[Mapping[str, tuple[str, ...]]] = MappingProxyType(
        {
            "a quote in the application id": (
                'fr.scanmylib", "x": "',
                "1.2.3",
                RELEASE_VERSION_CODE,
                SHA256,
                APK_SIZE_BYTES,
            ),
            "a quote after the version": ("fr.scanmylib", '1.2.3"', RELEASE_VERSION_CODE, SHA256, APK_SIZE_BYTES),
            "a quote in a development version": (
                "fr.scanmylib",
                '1.2.3-dev", "x": "',
                RELEASE_VERSION_CODE,
                SHA256,
                APK_SIZE_BYTES,
            ),
            "a version over 64 characters": (
                "fr.scanmylib",
                LONGEST_VERSION_NAME + "a",
                RELEASE_VERSION_CODE,
                SHA256,
                APK_SIZE_BYTES,
            ),
            "a version with an accented letter": (
                "fr.scanmylib",
                "1.2.3-dév",
                RELEASE_VERSION_CODE,
                SHA256,
                APK_SIZE_BYTES,
            ),
            "a version with an Arabic-Indic digit": (
                "fr.scanmylib",
                "١.2.3",
                RELEASE_VERSION_CODE,
                SHA256,
                APK_SIZE_BYTES,
            ),
            "a version code followed by JSON": (
                "fr.scanmylib",
                "1.2.3",
                f'{RELEASE_VERSION_CODE}, "x": 1',
                SHA256,
                APK_SIZE_BYTES,
            ),
            "a digest that is no SHA-256": (
                "fr.scanmylib",
                "1.2.3",
                RELEASE_VERSION_CODE,
                "not-a-digest",
                APK_SIZE_BYTES,
            ),
            "no size": ("fr.scanmylib", "1.2.3", RELEASE_VERSION_CODE, SHA256, ""),
        }
    )
    metadata_text_before: ClassVar[str | None]
    metadata_writes: ClassVar[dict[str, ScriptRun]]
    metadata_texts_after: ClassVar[dict[str, str | None]]

    @classmethod
    def setUpClass(cls) -> None:
        metadata_file = make_metadata_directory(cls) / ".scanmylib.json.partial"
        write_apk_metadata(metadata_file, "fr.scanmylib.dev", "1.2.3", RELEASE_VERSION_CODE, SHA256, APK_SIZE_BYTES)
        cls.metadata_text_before = read_text_if_present(metadata_file)
        cls.metadata_writes, cls.metadata_texts_after = {}, {}
        for row, fields in cls.refused_fields.items():
            cls.metadata_writes[row] = write_apk_metadata(metadata_file, *fields)
            cls.metadata_texts_after[row] = read_text_if_present(metadata_file)

    def test_should_refuse_each_as_unexpected(self) -> None:
        self.assertEqual(sorted(self.metadata_writes), sorted(self.refused_fields))
        for row, metadata_write in self.metadata_writes.items():
            with self.subTest(row):
                self.assertNotEqual(metadata_write.returncode, 0)
                self.assertIn("unexpected APK metadata", metadata_write.stderr)

    def test_should_leave_the_metadata_written_before(self) -> None:
        self.assertIsNotNone(self.metadata_text_before)
        self.assertEqual(self.metadata_texts_after, dict.fromkeys(self.refused_fields, self.metadata_text_before))


if __name__ == "__main__":
    unittest.main()
