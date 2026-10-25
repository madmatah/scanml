"""The first installation of production (scripts/setup.sh), in throwaway installations (installation_support.py).

Needs git, bash and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_setup.py'
"""

from __future__ import annotations

import re
import unittest
from typing import ClassVar

from docker_shim import Rule
from installation_support import (
    BOUNDED_ENGINE_CHECK,
    ENGINE_CHECK,
    ENGINE_CHECK_MODULE,
    PRODUCTION_ENGINE_CHECK_STEPS,
    PRODUCTION_PS,
    SANDBOX_OUTPUT,
    SANDBOX_TEXTS,
    TIMED_OUT_STATUS,
    Installation,
    InstallationTestCase,
    ScriptRun,
    build_running_sandbox_rules,
    list_writing_calls,
    make_installation,
)

ENGINE_CHECK_FAILURE = "the check of the engine's environment failed"


def install_for_the_first_time(installation: Installation, rules: list[Rule]) -> ScriptRun:
    """Production's containers are answered once, then never: the first call tells production's checkout, which falls
    back to the real ~/Dev/scanmylib without them, and the next one finds that production does not exist yet."""
    (installation.production_data / "state" / "scanmylib.db").unlink()
    production_data = installation.production_data
    installation.answer_docker(
        [
            {"match": PRODUCTION_PS, "stdout": "prodapi\n", "max_calls": 1},
            {"match": PRODUCTION_PS, "stdout": ""},
            *rules,
            *build_running_sandbox_rules(f"{production_data}/sandbox", str(production_data)),
        ]
    )
    # --no-apk: scripts/build-apk.sh would ask for production's checkout a third time, and refuse.
    return installation.run_script(installation.production_checkout, "setup.sh", "--no-apk", timeout_seconds=120)


def find_isolation_check_indexes(commands: list[str]) -> list[int]:
    return [index for index, command in enumerate(commands) if command.startswith("exec ") and command != ENGINE_CHECK]


def list_ocr_stops(commands: list[str]) -> list[str]:
    return [command for command in commands if command.startswith("compose") and command.endswith(" stop ocr")]


class WhenRunOutsideProductionsCheckout(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.setup_run = installation.run_script(installation.worktree, "setup.sh")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_it_is_not_production_s_checkout(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("is not production's checkout", self.setup_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenProductionHoldsADatabase(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.setup_run = installation.run_script(installation.production_checkout, "setup.sh")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_production_already_exists(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("production already exists", self.setup_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenProductionsContainersRunWithoutADatabase(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.production_data / "state" / "scanmylib.db").unlink()
        cls.setup_run = installation.run_script(installation.production_checkout, "setup.sh")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_and_say_that_new_versions_are_deployed_with_deploy_sh(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("deploy new versions with scripts/deploy.sh", self.setup_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenTheCheckoutIsNotAPublishedRelease(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.production_data / "state" / "scanmylib.db").unlink()
        installation.commit_after_the_release()
        cls.setup_run = installation.run_script(installation.production_checkout, "setup.sh")

    def test_should_refuse_since_a_first_installation_is_a_published_release_too(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("install a published release: HEAD", self.setup_run.stderr)


class WhenAChangeIsHiddenFromGitStatus(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        installation.hide_a_change_with_skip_worktree()
        cls.setup_run = installation.run_script(installation.production_checkout, "setup.sh")

    def test_should_refuse_and_name_the_file_it_could_hide(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("assume-unchanged or skip-worktree could hide changes: compose.yaml", self.setup_run.stderr)


class WhenTheFirstInstallationCompletes(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.setup_run = install_for_the_first_time(installation, [])
        cls.commands = installation.read_docker_commands()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.setup_run.returncode, 0, self.setup_run.output)
        self.assertIn("==> Ready", self.setup_run.stdout)

    def test_should_check_the_engine_s_environment_in_the_new_sandbox(self) -> None:
        self.assertIn(ENGINE_CHECK, self.commands)

    def test_should_show_that_it_bounds_the_check_of_the_engine_s_environment_in_time(self) -> None:
        self.assertRegex(self.setup_run.stdout, BOUNDED_ENGINE_CHECK)

    def test_should_check_the_engine_only_once_the_sandbox_passed_the_isolation_check(self) -> None:
        self.assertGreater(self.commands.index(ENGINE_CHECK), max(find_isolation_check_indexes(self.commands)))

    def test_should_leave_the_ocr_service_running(self) -> None:
        self.assertEqual(list_ocr_stops(self.commands), [])


class WhenTheEngineEnvironmentIsBroken(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        broken_engine: list[Rule] = [
            {"match": rf"^{re.escape(ENGINE_CHECK)}$", "exit": 1, "stdout": SANDBOX_OUTPUT, "stderr": SANDBOX_OUTPUT}
        ]
        cls.setup_run = install_for_the_first_time(installation, broken_engine)
        cls.commands = installation.read_docker_commands()

    def test_should_fail_at_the_engine_s_environment(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn(ENGINE_CHECK_FAILURE, self.setup_run.stderr)

    def test_should_show_the_command_it_ran(self) -> None:
        self.assertRegex(self.setup_run.stdout, BOUNDED_ENGINE_CHECK)

    def test_should_show_nothing_the_sandbox_printed_since_it_is_untrusted(self) -> None:
        self.assertEqual([text[:40] for text in SANDBOX_TEXTS if text in self.setup_run.output], [])

    def test_should_say_how_to_see_why_the_check_failed(self) -> None:
        self.assertEqual([step for step in PRODUCTION_ENGINE_CHECK_STEPS if step not in self.setup_run.stdout], [])

    def test_should_stop_the_ocr_service(self) -> None:
        self.assertNotEqual(list_ocr_stops(self.commands), [])

    def test_should_not_say_that_production_is_ready(self) -> None:
        self.assertNotIn("==> Ready", self.setup_run.stdout)


class WhenTheCheckOfTheEngineEnvironmentDoesNotFinishInTime(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        timed_out: list[Rule] = [{"match": rf"^{re.escape(ENGINE_CHECK)}$", "exit": TIMED_OUT_STATUS}]
        cls.setup_run = install_for_the_first_time(installation, timed_out)
        cls.commands = installation.read_docker_commands()

    def test_should_fail_at_the_engine_s_environment(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn(ENGINE_CHECK_FAILURE, self.setup_run.stderr)

    def test_should_stop_the_ocr_service(self) -> None:
        self.assertNotEqual(list_ocr_stops(self.commands), [])

    def test_should_say_how_to_see_why_the_check_failed(self) -> None:
        self.assertEqual([step for step in PRODUCTION_ENGINE_CHECK_STEPS if step not in self.setup_run.stdout], [])


class WhenTheOcrContainerCannotBeFound(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        not_found: list[Rule] = [{"match": r" ps -q ocr$", "stdout": ""}]
        cls.setup_run = install_for_the_first_time(installation, not_found)
        cls.commands = installation.read_docker_commands()

    def test_should_fail_since_it_cannot_find_the_ocr_container(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("cannot find the ocr container: see scripts/prod.sh compose ps ocr", self.setup_run.stderr)

    def test_should_not_run_the_check_of_the_engine_s_environment(self) -> None:
        self.assertEqual([command for command in self.commands if ENGINE_CHECK_MODULE in command], [])

    def test_should_stop_the_ocr_service_since_its_engine_was_never_checked(self) -> None:
        self.assertNotEqual(list_ocr_stops(self.commands), [])
        self.assertIn("stopping ocr, whose container cannot be found", self.setup_run.stdout)


class WhenTheSandboxIsNotIsolated(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        production_data = installation.production_data
        on_a_network = build_running_sandbox_rules(f"{production_data}/sandbox", str(production_data), network="bridge")
        cls.setup_run = install_for_the_first_time(installation, on_a_network)
        cls.commands = installation.read_docker_commands()

    def test_should_fail_at_the_isolation_check(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("scripts/verify-sandbox.sh failed", self.setup_run.stderr)

    def test_should_not_say_that_production_is_ready(self) -> None:
        self.assertNotIn("==> Ready", self.setup_run.stdout)

    def test_should_stop_the_ocr_service(self) -> None:
        self.assertNotEqual(list_ocr_stops(self.commands), [])

    def test_should_say_that_it_stopped_the_ocr_service_since_it_failed_the_isolation_check(self) -> None:
        self.assertIn("stopping ocr, which failed the isolation check", self.setup_run.stdout)

    def test_should_not_check_the_engine_of_a_sandbox_that_is_not_isolated(self) -> None:
        self.assertEqual([command for command in self.commands if ENGINE_CHECK_MODULE in command], [])


if __name__ == "__main__":
    unittest.main()
