"""The gate (scripts/check.sh), in the worktrees of throwaway installations (installation_support.py), whose docker
stand-in only logs the builds and the containers that would check each area.

Needs git, bash and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_check.py'
"""

from __future__ import annotations

import os
import re
import shutil
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from docker_shim import LoggedCall, Rule, image_id
from installation_support import Installation, InstallationTestCase, ScriptRun, make_installation

_ISOLATED_FLAGS = {"--rm", "--read-only", "--init"}
_OPTIONS_WITH_ANY_VALUE = {"--env", "-v", "-w"}
_OPTIONS_WITH_ALLOWED_VALUES = {
    "--network": {"none"},
    "--cap-drop": {"ALL"},
    "--security-opt": {"no-new-privileges:true"},
    "--user": {f"{os.getuid()}:{os.getgid()}"},
    "--tmpfs": {"/tmp"},
}
_OPTIONS_GIVEN_ONCE = ("--network", "--read-only", "--cap-drop", "--security-opt", "--user")
FIXER_COMMANDS = ("ruff check --fix .", "ruff format .", "-w -- ", "biome check --write", "ktlintFormat")


@dataclass(frozen=True)
class FormatterChange:
    command_pattern: str
    container_path: str
    worktree_path: str
    text: str


def check(installation: Installation, *arguments: str, environment: dict[str, str] | None = None) -> ScriptRun:
    return installation.run_script(installation.worktree, "check.sh", *arguments, environment=environment)


def fix(installation: Installation) -> ScriptRun:
    """check.sh --fix, whose ktlint builds the app as CI would, without a .env."""
    ci_settings = {"CI": "true", "DATA_DIR": str(installation.directory / "ci")}
    return check(installation, "--fix", environment=ci_settings)


def list_checks(calls: list[LoggedCall]) -> list[list[str]]:
    return [call["argv"] for call in calls if call["argv"][:1] in (["build"], ["run"])]


def list_runs(calls: list[LoggedCall]) -> list[list[str]]:
    return [argv for argv in list_checks(calls) if argv[0] == "run"]


def list_tool_runs(calls: list[LoggedCall]) -> list[list[str]]:
    """The runs of the tools, but the app's build container, which runs ktlint: build-apk.sh's own tests cover it."""
    return [argv for argv in list_runs(calls) if "ktlintFormat" not in argv]


def list_areas_checked(gate_run: ScriptRun) -> list[str]:
    return re.findall(r"Checking (\w+)", gate_run.stdout)


def list_mounts(run: list[str]) -> list[str]:
    return [run[index + 1] for index, argument in enumerate(run) if argument == "-v"]


def list_isolation_breaches(run: list[str]) -> list[str]:
    breaches = []
    options = []
    index = 1
    while run[index].startswith("-"):
        option = run[index]
        options.append(option)
        if option in _ISOLATED_FLAGS:
            index += 1
            continue
        if option not in _OPTIONS_WITH_ANY_VALUE | _OPTIONS_WITH_ALLOWED_VALUES.keys():
            breaches.append(f"the option {option}")
        elif option in _OPTIONS_WITH_ALLOWED_VALUES and run[index + 1] not in _OPTIONS_WITH_ALLOWED_VALUES[option]:
            breaches.append(f"{option} {run[index + 1]}")
        index += 2
    breaches += [
        f"{option} given {options.count(option)} times" for option in _OPTIONS_GIVEN_ONCE if options.count(option) != 1
    ]
    return breaches


def find_formatted_copy(tool_runs: list[list[str]]) -> Path:
    mounts = [mount for run in tool_runs for mount in list_mounts(run)]
    server_mount = next(mount for mount in reversed(mounts) if mount.endswith(":/src/server"))
    return Path(server_mount.split(":")[0]).parent.parent


def write_scripts_test(installation: Installation, body: str, directory: str = "tests") -> None:
    """A test of the scripts whose body is `body`, next to the runner's own: the only other test of the installation's
    scripts/, which its areas then run."""
    tests = installation.worktree / "scripts" / directory
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_placeholder.py").write_text(
        "import os\nimport unittest\n\n\nclass Placeholder(unittest.TestCase):\n"
        f"    def test_placeholder(self) -> None:\n        {body}\n"
    )


def commit_in_worktree(installation: Installation, path: str, text: str) -> None:
    (installation.worktree / path).parent.mkdir(parents=True, exist_ok=True)
    (installation.worktree / path).write_text(text)
    installation.run_git(installation.worktree, "add", path)
    installation.run_git(installation.worktree, "commit", "--quiet", "--message", f"Change {path}")


def break_commit_areas(checkout: Path) -> None:
    (checkout / "scripts" / "lib" / "commit_areas.py").write_text("import sys\n\nsys.exit(1)\n")


class TheLastCommitOptionWhenTheCommitChangesTheApi(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        commit_in_worktree(installation, "server/scanmylib/notes.py", "NOTES = 1\n")
        cls.gate_run = check(installation, "--last-commit")

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_check_the_areas_that_its_files_reach(self) -> None:
        self.assertEqual(list_areas_checked(self.gate_run), ["lint", "server"])


class TheLastCommitOptionWhenTheCommitChangesDocumentsOnly(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        commit_in_worktree(installation, "docs/guide.md", "# Guide\n")
        cls.gate_run = check(installation, "--last-commit")
        cls.checks = list_checks(installation.read_docker_calls())

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_say_that_there_is_nothing_to_check(self) -> None:
        self.assertIn("Nothing to check: no area reads what the last commit changes", self.gate_run.stdout)

    def test_should_check_no_area(self) -> None:
        self.assertEqual(self.checks, [])


class TheLastCommitOptionWhenItsAreasCannotBeTold(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        commit_in_worktree(installation, "server/scanmylib/notes.py", "NOTES = 1\n")
        break_commit_areas(installation.worktree)
        cls.gate_run = check(installation, "--last-commit")
        cls.checks = list_checks(installation.read_docker_calls())

    def test_should_fail_and_say_that_it_cannot_tell_them(self) -> None:
        self.assertNotEqual(self.gate_run.returncode, 0)
        self.assertIn("cannot tell the areas the last commit touches", self.gate_run.stderr)

    def test_should_check_no_area(self) -> None:
        self.assertEqual(self.checks, [])


class TheLastCommitOptionWhenGivenAnArea(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.gate_run = check(installation, "--last-commit", "server")

    def test_should_refuse_since_it_takes_none(self) -> None:
        self.assertNotEqual(self.gate_run.returncode, 0)
        self.assertIn("--last-commit takes no area", self.gate_run.stderr)


class TheLastCommitOptionWhenRunInProductionsCheckout(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        # A commit_areas.py that would fail shows whether the refusal comes first.
        break_commit_areas(installation.production_checkout)
        cls.gate_run = installation.run_script(installation.production_checkout, "check.sh", "--last-commit")

    def test_should_refuse_before_anything_else(self) -> None:
        self.assertNotEqual(self.gate_run.returncode, 0)
        self.assertIn("is production's checkout", self.gate_run.stderr)


class WhenGivenAreas(InstallationTestCase):
    worktree: ClassVar[Path]
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.worktree = installation.worktree
        cls.gate_run = check(installation, "server", "web")
        cls.checks = [" ".join(argv) for argv in list_checks(installation.read_docker_calls())]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_check_only_those_in_the_order_given(self) -> None:
        self.assertEqual(list_areas_checked(self.gate_run), ["server", "web"])

    def test_should_build_and_run_the_tests_of_the_api_then_run_those_of_the_web_ui(self) -> None:
        self.assertEqual(len(self.checks), 3)

    def test_should_build_the_test_image_of_the_api_from_the_worktree(self) -> None:
        self.assertIn(f"--target test {self.worktree}/server", self.checks[0])

    def test_should_run_the_tests_of_the_web_ui_with_node(self) -> None:
        self.assertIn("node --test", self.checks[2])


class WhenGivenTheWebUiTheApiAndTheSandbox(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.gate_run = check(installation, "web", "server", "ocr")
        cls.runs = [" ".join(argv) for argv in list_runs(installation.read_docker_calls())]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_run_their_tests_without_network_on_a_read_only_filesystem(self) -> None:
        self.assertEqual(len(self.runs), 3)
        for run in self.runs:
            with self.subTest(run):
                self.assertIn("--network none --read-only", run)


class WhenGivenTheApi(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.gate_run = check(installation, "server")
        cls.checks = list_checks(installation.read_docker_calls())

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_build_then_run_the_tests(self) -> None:
        self.assertEqual([argv[0] for argv in self.checks], ["build", "run"])

    def test_should_run_the_image_that_its_build_wrote(self) -> None:
        self.assertEqual(self.checks[1][-1], image_id(self.checks[0]))


class WhenGivenTheWebUiAndTheSandbox(InstallationTestCase):
    worktree: ClassVar[Path]
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.worktree = installation.worktree
        cls.gate_run = check(installation, "web", "ocr")
        cls.checks = list_checks(installation.read_docker_calls())

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_run_the_tests_of_the_web_ui_then_build_and_run_those_of_the_sandbox(self) -> None:
        self.assertEqual([argv[0] for argv in self.checks], ["run", "build", "run"])

    def test_should_build_the_image_of_the_sandbox_from_the_worktree(self) -> None:
        self.assertTrue(self.checks[1][-1].endswith(f"{self.worktree}/ocr"), self.checks[1])

    def test_should_run_each_without_network_or_privileges(self) -> None:
        tests = {"web UI": self.checks[0], "sandbox": self.checks[2]}
        for area, run in tests.items():
            with self.subTest(area):
                self.assertEqual(list_isolation_breaches(run), [])

    def test_should_mount_its_own_sources_alone_read_only(self) -> None:
        mounts = {"web UI": list_mounts(self.checks[0]), "sandbox": list_mounts(self.checks[2])}
        self.assertEqual(
            mounts,
            {"web UI": [f"{self.worktree}/server/scanmylib/web:/web:ro"], "sandbox": [f"{self.worktree}/ocr:/app:ro"]},
        )


class WhenGivenTheAppOnGitHubActions(InstallationTestCase):
    ci_data: ClassVar[Path]
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        runner_temporary_directory = installation.home / "work" / "_temp"
        cls.ci_data = runner_temporary_directory / "data"
        settings = {
            "GITHUB_ACTIONS": "true",
            "RUNNER_TEMP": str(runner_temporary_directory),
            "DATA_DIR": str(cls.ci_data),
        }
        cls.gate_run = check(installation, "android", environment=settings)
        cls.checks = [" ".join(argv) for argv in list_checks(installation.read_docker_calls())]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_check_it_in_one_build(self) -> None:
        self.assertEqual(len(self.checks), 1)

    def test_should_hand_the_settings_of_github_actions_to_the_build(self) -> None:
        self.assertIn(f"{self.ci_data}/android/sdk:/opt/android-sdk", self.checks[0])


class WhenGivenTheApp(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        settings = {"CI": "true", "DATA_DIR": str(installation.directory / "ci")}
        cls.gate_run = check(installation, "android", environment=settings)
        cls.checks = list_checks(installation.read_docker_calls())

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_run_its_tests_lint_and_ktlint_in_one_build(self) -> None:
        self.assertEqual([argv[-3:] for argv in self.checks], [["test", "lint", "ktlintCheck"]])


class WhenGivenTheLint(InstallationTestCase):
    lint_tool_commands: ClassVar[tuple[str, ...]] = (
        "ruff format --check .",
        "ruff check .",
        "mypy --config-file ../mypy.ini scanmylib tests",
        "mypy --config-file ../mypy.ini scanmylib_ocr tests bench",
        "mypy --config-file ../mypy.ini lib release.py e2e_test.py tests integration_tests",
        "zizmor --offline",
        "koalaman/shellcheck:",
        "-d -- ",
        "biome ci",
    )
    gate_run: ClassVar[ScriptRun]
    tool_runs: ClassVar[list[list[str]]]
    build_contexts: ClassVar[list[list[str] | None]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.gate_run = check(installation, "lint")
        calls = installation.read_docker_calls()
        cls.tool_runs = list_tool_runs(calls)
        cls.build_contexts = [call.get("context") for call in calls if call["argv"][:1] == ["build"]]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_check_every_language(self) -> None:
        tool_commands = [" ".join(run) for run in self.tool_runs]
        for lint_tool_command in self.lint_tool_commands:
            with self.subTest(lint_tool_command):
                self.assertTrue(any(lint_tool_command in command for command in tool_commands), tool_commands)

    def test_should_run_each_tool_without_network_or_privileges(self) -> None:
        self.assertEqual(len(self.tool_runs), len(self.lint_tool_commands))
        for run in self.tool_runs:
            with self.subTest(run=run):
                self.assertEqual(list_isolation_breaches(run), [])

    def test_should_mount_the_sources_read_only(self) -> None:
        self.assertEqual(len(self.tool_runs), len(self.lint_tool_commands))
        for run in self.tool_runs:
            with self.subTest(run=run):
                mounts = list_mounts(run)
                self.assertNotEqual(mounts, [])
                self.assertEqual([mount for mount in mounts if not mount.endswith(":ro")], [])

    def test_should_build_the_tools_from_their_locks_alone(self) -> None:
        self.assertEqual(
            self.build_contexts,
            [
                ["scripts/lint/Dockerfile", "scripts/lint/requirements.lock", "server/requirements-test.lock"],
                [
                    "scripts/lint/Dockerfile.web",
                    "server/scanmylib/web/package-lock.json",
                    "server/scanmylib/web/package.json",
                ],
            ],
        )


class WhenGivenTheLintAfterAScriptOfASkillIsAddedAndAnotherDeleted(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    skills_type_checks: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        scripts = installation.worktree / ".claude" / "skills" / "example" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "gone.py").write_text("print('gone')\n")
        installation.run_git(installation.worktree, "add", str(scripts / "gone.py"))
        installation.run_git(installation.worktree, "commit", "--quiet", "--message", "A script of a skill")
        (scripts / "gone.py").unlink()
        (scripts / "tool.py").write_text("print('tool')\n")
        cls.gate_run = check(installation, "lint")
        tools = [" ".join(run) for run in list_tool_runs(installation.read_docker_calls())]
        cls.skills_type_checks = [tool for tool in tools if "mypy --config-file mypy.ini --" in tool]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_type_the_new_script_and_skip_the_deleted_one(self) -> None:
        type_check = "mypy --config-file mypy.ini -- .claude/skills/example/scripts/tool.py"
        self.assertEqual(len(self.skills_type_checks), 1)
        self.assertTrue(self.skills_type_checks[0].endswith(type_check), self.skills_type_checks)


class WhenGivenTheLintAfterAShellScriptIsAddedAndAnotherDeleted(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    shellcheck_runs: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.worktree / "scripts" / "new.sh").write_text("#!/usr/bin/env bash\n")
        (installation.worktree / "scripts" / "setup.sh").unlink()
        cls.gate_run = check(installation, "lint")
        tool_runs = list_tool_runs(installation.read_docker_calls())
        cls.shellcheck_runs = [run for run in tool_runs if any("koalaman/shellcheck" in part for part in run)]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_run_shellcheck_once(self) -> None:
        self.assertEqual(len(self.shellcheck_runs), 1)

    def test_should_check_the_new_script(self) -> None:
        shellcheck = self.shellcheck_runs[0]
        self.assertIn("scripts/new.sh", shellcheck[shellcheck.index("--") + 1 :])

    def test_should_skip_the_deleted_script(self) -> None:
        shellcheck = self.shellcheck_runs[0]
        self.assertNotIn("scripts/setup.sh", shellcheck[shellcheck.index("--") + 1 :])


class WhenALintToolReportsFindings(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    tool_runs: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        installation.answer_docker([{"match": r" ruff check \.$", "exit": 1}])
        cls.gate_run = check(installation, "lint")
        cls.tool_runs = list_tool_runs(installation.read_docker_calls())

    def test_should_fail(self) -> None:
        self.assertNotEqual(self.gate_run.returncode, 0)

    def test_should_stop_at_that_tool(self) -> None:
        self.assertTrue(" ".join(self.tool_runs[-1]).endswith("ruff check ."), self.tool_runs[-1])


class WhenGivenNoArea(InstallationTestCase):
    areas_in_order: ClassVar[tuple[str, ...]] = ("lint", "scripts", "web", "server", "ocr", "android", "integration")
    gate_run: ClassVar[ScriptRun]
    is_scripts_mark_left: ClassVar[bool]
    is_integration_mark_left: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        # Each placeholder leaves its mark, so that each area shows it ran its own directory.
        write_scripts_test(installation, 'open(os.environ["SCRIPTS_MARK"], "w").close()')
        write_scripts_test(
            installation, 'open(os.environ["INTEGRATION_MARK"], "w").close()', directory="integration_tests"
        )
        scripts_mark = installation.directory / "scripts-ran"
        integration_mark = installation.directory / "integration-ran"
        settings = {
            "CI": "true",
            "DATA_DIR": str(installation.directory / "ci"),
            "SCRIPTS_MARK": str(scripts_mark),
            "INTEGRATION_MARK": str(integration_mark),
        }
        cls.gate_run = check(installation, environment=settings)
        cls.is_scripts_mark_left = scripts_mark.exists()
        cls.is_integration_mark_left = integration_mark.exists()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)

    def test_should_check_every_area_in_order(self) -> None:
        self.assertEqual(tuple(list_areas_checked(self.gate_run)), self.areas_in_order)

    def test_should_run_the_unit_tests_of_the_scripts_in_their_area(self) -> None:
        self.assertTrue(self.is_scripts_mark_left)

    def test_should_run_the_integration_tests_of_the_scripts_in_their_area(self) -> None:
        self.assertTrue(self.is_integration_mark_left)


class WhenTheCallerSetsGitVariables(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        write_scripts_test(installation, 'self.assertNotIn("GIT_DIR", os.environ)')
        # What `git rebase --exec` exports in a worktree, at a path where no repository can be touched.
        cls.gate_run = check(installation, "scripts", environment={"GIT_DIR": "/nonexistent/caller/.git"})

    def test_should_drop_them_before_any_area_runs(self) -> None:
        self.assertEqual(self.gate_run.returncode, 0, self.gate_run.output)


class WhenABuildFails(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        installation.answer_docker([{"match": r"^build ", "exit": 1}])
        cls.gate_run = check(installation, "server", "web")
        cls.checks = [" ".join(argv) for argv in list_checks(installation.read_docker_calls())]

    def test_should_fail(self) -> None:
        self.assertNotEqual(self.gate_run.returncode, 0)

    def test_should_stop_at_the_build_of_the_first_area(self) -> None:
        self.assertEqual(len(self.checks), 1)
        self.assertIn("--target test", self.checks[0])


class WhenABuildWritesNoImageId(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        installation.answer_docker([{"match": r"^build ", "no_image_id": True}])
        cls.gate_run = check(installation, "server")
        cls.checks = list_checks(installation.read_docker_calls())

    def test_should_fail_and_say_so(self) -> None:
        self.assertNotEqual(self.gate_run.returncode, 0)
        self.assertIn("docker build wrote no image id", self.gate_run.stderr)

    def test_should_run_nothing_after_the_build(self) -> None:
        self.assertEqual([argv[0] for argv in self.checks], ["build"])


class WhenALaterBuildFails(InstallationTestCase):
    gate_run: ClassVar[ScriptRun]
    checks: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        installation.answer_docker([{"match": r"^build .*/ocr$", "exit": 1}])
        cls.gate_run = check(installation, "server", "ocr")
        cls.checks = list_checks(installation.read_docker_calls())

    def test_should_fail(self) -> None:
        self.assertNotEqual(self.gate_run.returncode, 0)

    def test_should_never_run_the_image_of_an_earlier_build(self) -> None:
        self.assertEqual([argv[0] for argv in self.checks], ["build", "run", "build"])


class WhenGivenAnAreaItDoesNotKnow(InstallationTestCase):
    # The second is one argument holding two areas, which a match on the joined list of areas would accept.
    arguments: ClassVar[Mapping[str, tuple[str, ...]]] = MappingProxyType(
        {
            "an unknown area after a known one": ("web", "docs"),
            "two areas in one argument": ("web server",),
        }
    )
    gate_runs: ClassVar[dict[str, ScriptRun]]
    docker_calls: ClassVar[dict[str, list[LoggedCall]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.gate_runs, cls.docker_calls = {}, {}
        for row, arguments in cls.arguments.items():
            cls.gate_runs[row] = check(installation, *arguments)
            cls.docker_calls[row] = installation.read_docker_calls()

    def test_should_refuse_and_name_it(self) -> None:
        self.assertEqual(sorted(self.gate_runs), sorted(self.arguments))
        for row, gate_run in self.gate_runs.items():
            with self.subTest(row):
                self.assertNotEqual(gate_run.returncode, 0)
                self.assertIn(f"unknown area '{self.arguments[row][-1]}'", gate_run.stderr)

    def test_should_call_docker_for_nothing(self) -> None:
        self.assertEqual(self.docker_calls, {row: [] for row in self.arguments})


class WhenRunInProductionsCheckout(InstallationTestCase):
    # --fix would write there.
    arguments: ClassVar[Mapping[str, tuple[str, ...]]] = MappingProxyType({"an area": ("web",), "the fix": ("--fix",)})
    gate_runs: ClassVar[dict[str, ScriptRun]]
    checks: ClassVar[dict[str, list[list[str]]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.gate_runs, cls.checks = {}, {}
        for row, arguments in cls.arguments.items():
            cls.gate_runs[row] = installation.run_script(installation.production_checkout, "check.sh", *arguments)
            cls.checks[row] = list_checks(installation.read_docker_calls())

    def test_should_refuse_since_it_is_production_s_checkout(self) -> None:
        self.assertEqual(sorted(self.gate_runs), sorted(self.arguments))
        for row, gate_run in self.gate_runs.items():
            with self.subTest(row):
                self.assertNotEqual(gate_run.returncode, 0)
                self.assertIn("is production's checkout", gate_run.stderr)

    def test_should_check_nothing(self) -> None:
        self.assertEqual(self.checks, {row: [] for row in self.arguments})


class TheFixOption(InstallationTestCase):
    home: ClassVar[Path]
    worktree: ClassVar[Path]
    fix_run: ClassVar[ScriptRun]
    runs: ClassVar[list[str]]
    tool_runs: ClassVar[list[list[str]]]
    temporary_directory: ClassVar[Path]
    temporary_entries: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.home = installation.home
        cls.worktree = installation.worktree
        cls.fix_run = fix(installation)
        calls = installation.read_docker_calls()
        cls.runs = [" ".join(argv) for argv in list_runs(calls)]
        cls.tool_runs = list_tool_runs(calls)
        cls.temporary_directory = installation.directory
        cls.temporary_entries = sorted(path.name for path in installation.directory.iterdir())

    def test_should_succeed(self) -> None:
        self.assertEqual(self.fix_run.returncode, 0, self.fix_run.output)

    def test_should_format_and_fix_every_language(self) -> None:
        for fixer_command in FIXER_COMMANDS:
            with self.subTest(fixer_command):
                self.assertTrue(any(fixer_command in run for run in self.runs), self.runs)

    def test_should_run_no_check(self) -> None:
        self.assertEqual([run for run in self.runs if "ruff format --check" in run or "biome ci" in run], [])

    def test_should_check_no_area(self) -> None:
        self.assertEqual(list_areas_checked(self.fix_run), [])

    def test_should_write_to_a_copy_outside_the_home_directory(self) -> None:
        formatted_copy = find_formatted_copy(self.tool_runs)
        self.assertFalse(formatted_copy.is_relative_to(self.home), formatted_copy)

    def test_should_run_biome_ruff_and_shfmt_besides_ktlint(self) -> None:
        self.assertEqual(len(self.tool_runs), 4)

    def test_should_let_biome_write_to_the_copy_of_the_web_ui_alone(self) -> None:
        biome = self.tool_runs[0]
        tree = find_formatted_copy(self.tool_runs) / "tree"
        self.assertEqual(list_mounts(biome), [f"{tree}/server/scanmylib/web:/web"])

    def test_should_let_ruff_and_shfmt_write_to_the_copy_alone_and_read_the_worktree_read_only(self) -> None:
        tree = find_formatted_copy(self.tool_runs) / "tree"
        mounts = [
            f"{self.worktree}:/src:ro",
            f"{tree}/server:/src/server",
            f"{tree}/ocr:/src/ocr",
            f"{tree}/scripts:/src/scripts",
            f"{tree}/.claude/skills:/src/.claude/skills",
        ]
        self.assertEqual([list_mounts(run) for run in self.tool_runs[1:]], [mounts, mounts, mounts])

    def test_should_run_the_formatters_without_network_or_privileges(self) -> None:
        self.assertEqual(len(self.tool_runs), 4)
        for run in self.tool_runs:
            with self.subTest(run=run):
                self.assertEqual(list_isolation_breaches(run), [])

    def test_should_remove_its_copy_once_it_succeeds(self) -> None:
        formatted_copy = find_formatted_copy(self.tool_runs)
        self.assertEqual(formatted_copy.parent, self.temporary_directory)
        self.assertNotIn(formatted_copy.name, self.temporary_entries)


class TheFixOptionWhenAFormatterChangesATrackedFile(InstallationTestCase):
    changes: ClassVar[Mapping[str, FormatterChange]] = MappingProxyType(
        {
            "ruff format": FormatterChange(
                r" ruff format \.$", "/src/scripts/e2e_test.py", "scripts/e2e_test.py", "# formatted\n"
            ),
            "shfmt": FormatterChange(r" -w -- ", "/src/scripts/dev.sh", "scripts/dev.sh", "# formatted\n"),
            "biome": FormatterChange(
                "biome check --write", "/web/package.json", "server/scanmylib/web/package.json", "{}\n"
            ),
        }
    )
    fix_runs: ClassVar[dict[str, ScriptRun]]
    texts_after: ClassVar[dict[str, str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.fix_runs, cls.texts_after = {}, {}
        for row, change in cls.changes.items():
            installation.answer_docker(
                [{"match": change.command_pattern, "files": {change.container_path: change.text}}]
            )
            cls.fix_runs[row] = fix(installation)
            cls.texts_after[row] = (installation.worktree / change.worktree_path).read_text()

    def test_should_succeed(self) -> None:
        self.assertEqual(sorted(self.fix_runs), sorted(self.changes))
        for row, fix_run in self.fix_runs.items():
            with self.subTest(row):
                self.assertEqual(fix_run.returncode, 0, fix_run.output)

    def test_should_bring_the_change_back_to_the_worktree(self) -> None:
        self.assertEqual(self.texts_after, {row: change.text for row, change in self.changes.items()})


class TheFixOptionWhenAFormatterCreatesAFile(InstallationTestCase):
    fix_run: ClassVar[ScriptRun]
    is_created_file_brought_back: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        planted: Rule = {"match": r" ruff format \.$", "files": {"/src/scripts/tests/test_planted.py": "planted\n"}}
        installation.answer_docker([planted])
        cls.fix_run = fix(installation)
        cls.is_created_file_brought_back = (installation.worktree / "scripts" / "tests" / "test_planted.py").exists()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.fix_run.returncode, 0, self.fix_run.output)

    def test_should_never_bring_it_back(self) -> None:
        self.assertFalse(self.is_created_file_brought_back)


class TheFixOptionWhenAFormatterChangesAFileThatTheFormattersDoNotFormat(InstallationTestCase):
    container_paths: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "a vendored library": "/web/static/vendor/library.min.js",
            "the lock of the web UI": "/web/package-lock.json",
        }
    )
    fix_runs: ClassVar[dict[str, ScriptRun]]
    texts_before: ClassVar[dict[str, str]]
    texts_after: ClassVar[dict[str, str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        web = installation.worktree / "server" / "scanmylib" / "web"
        vendored = web / "static" / "vendor" / "library.min.js"
        vendored.parent.mkdir(parents=True)
        vendored.write_text("library\n")
        installation.run_git(installation.worktree, "add", str(vendored))
        installation.run_git(installation.worktree, "commit", "--quiet", "--message", "Vendored library")
        paths = {"a vendored library": vendored, "the lock of the web UI": web / "package-lock.json"}
        cls.fix_runs, cls.texts_before, cls.texts_after = {}, {}, {}
        for row, container_path in cls.container_paths.items():
            cls.texts_before[row] = paths[row].read_text()
            installation.answer_docker([{"match": "biome check --write", "files": {container_path: "spliced\n"}}])
            cls.fix_runs[row] = fix(installation)
            cls.texts_after[row] = paths[row].read_text()

    def test_should_succeed(self) -> None:
        self.assertEqual(sorted(self.fix_runs), sorted(self.container_paths))
        for row, fix_run in self.fix_runs.items():
            with self.subTest(row):
                self.assertEqual(fix_run.returncode, 0, fix_run.output)

    def test_should_never_bring_it_back(self) -> None:
        self.assertEqual(sorted(self.texts_after), sorted(self.container_paths))
        self.assertEqual(self.texts_after, self.texts_before)


class TheFixOptionWhenAFormatterChangesAnUntrackedFile(InstallationTestCase):
    untracked_text: ClassVar[str] = "#!/usr/bin/env bash\n"
    fix_run: ClassVar[ScriptRun]
    text_after: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        untracked = installation.worktree / "scripts" / "local.sh"
        untracked.write_text(cls.untracked_text)
        installation.answer_docker([{"match": r" -w -- ", "files": {"/src/scripts/local.sh": "formatted\n"}}])
        cls.fix_run = fix(installation)
        cls.text_after = untracked.read_text()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.fix_run.returncode, 0, self.fix_run.output)

    def test_should_leave_it_alone(self) -> None:
        self.assertEqual(self.text_after, self.untracked_text)

    def test_should_name_it(self) -> None:
        self.assertIn("scripts/local.sh", self.fix_run.stderr)


class TheFixOptionWhenAFormatterChangesTheScriptThatBuildsTheApp(InstallationTestCase):
    # Brought back first, this script would run in place of the checkout's own, which builds the app.
    planted_script: ClassVar[str] = "#!/usr/bin/env bash\nexit 3\n"
    fix_run: ClassVar[ScriptRun]
    checks: ClassVar[list[list[str]]]
    text_after: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        planted: Rule = {"match": r" ruff format \.$", "files": {"/src/scripts/build-apk.sh": cls.planted_script}}
        installation.answer_docker([planted])
        cls.fix_run = fix(installation)
        cls.checks = list_checks(installation.read_docker_calls())
        cls.text_after = (installation.worktree / "scripts" / "build-apk.sh").read_text()

    def test_should_succeed_since_ktlint_ran_through_the_checkout_s_own_script(self) -> None:
        self.assertEqual(self.fix_run.returncode, 0, self.fix_run.output)

    def test_should_run_ktlint(self) -> None:
        self.assertTrue(any("ktlintFormat" in argv for argv in self.checks))

    def test_should_bring_the_change_back_afterwards(self) -> None:
        self.assertEqual(self.text_after, self.planted_script)


class TheFixOptionWhenAFormatterTurnsAFileIntoALink(InstallationTestCase):
    fix_run: ClassVar[ScriptRun]
    texts_before: ClassVar[dict[str, str]]
    texts_after: ClassVar[dict[str, str]]
    is_link_brought_back: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        worktree = installation.worktree
        secret = installation.directory / "secret"
        secret.write_text("secret\n")
        paths = ("scripts/dev.sh", "scripts/prod.sh")
        cls.texts_before = {path: (worktree / path).read_text() for path in paths}
        installation.answer_docker(
            [
                {"match": r" ruff format \.$", "files": {"/src/scripts/dev.sh": "formatted\n"}},
                {"match": r" -w -- ", "links": {"/src/scripts/prod.sh": str(secret)}},
            ]
        )
        cls.fix_run = fix(installation)
        cls.texts_after = {path: (worktree / path).read_text() for path in paths}
        cls.is_link_brought_back = (worktree / "scripts" / "prod.sh").is_symlink()

    def test_should_fail_and_say_so(self) -> None:
        self.assertNotEqual(self.fix_run.returncode, 0)
        self.assertIn("into something other than a file", self.fix_run.stderr)

    def test_should_bring_nothing_back(self) -> None:
        self.assertEqual(self.texts_after, self.texts_before)

    def test_should_never_bring_the_link_back(self) -> None:
        self.assertFalse(self.is_link_brought_back)


class TheFixOptionWhenAFormatterTurnsADirectoryIntoALink(InstallationTestCase):
    fix_run: ClassVar[ScriptRun]
    texts_before: ClassVar[dict[str, str]]
    texts_after: ClassVar[dict[str, str]]
    is_link_brought_back: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        worktree = installation.worktree
        elsewhere = installation.directory / "elsewhere"
        shutil.copytree(worktree / "scripts" / "lib", elsewhere)
        paths = ("scripts/dev.sh", "scripts/lib/common.sh")
        cls.texts_before = {path: (worktree / path).read_text() for path in paths}
        installation.answer_docker(
            [
                {"match": r" ruff format \.$", "files": {"/src/scripts/dev.sh": "formatted\n"}},
                {"match": r" -w -- ", "links": {"/src/scripts/lib": str(elsewhere)}},
            ]
        )
        cls.fix_run = fix(installation)
        cls.texts_after = {path: (worktree / path).read_text() for path in paths}
        cls.is_link_brought_back = (worktree / "scripts" / "lib").is_symlink()

    def test_should_fail_and_say_so(self) -> None:
        self.assertNotEqual(self.fix_run.returncode, 0)
        self.assertIn("into something other than a file", self.fix_run.stderr)

    def test_should_bring_nothing_back(self) -> None:
        self.assertEqual(self.texts_after, self.texts_before)

    def test_should_never_bring_the_link_back(self) -> None:
        self.assertFalse(self.is_link_brought_back)


class TheFixOptionWhenItBringsNothingBack(InstallationTestCase):
    fix_run: ClassVar[ScriptRun]
    tool_runs: ClassVar[list[list[str]]]
    temporary_directory: ClassVar[Path]
    temporary_entries: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        installation.answer_docker([{"match": r" -w -- ", "links": {"/src/scripts/prod.sh": "/nonexistent"}}])
        cls.fix_run = fix(installation)
        cls.tool_runs = list_tool_runs(installation.read_docker_calls())
        cls.temporary_directory = installation.directory
        cls.temporary_entries = sorted(path.name for path in installation.directory.iterdir())

    def test_should_fail_and_say_why(self) -> None:
        self.assertNotEqual(self.fix_run.returncode, 0)
        self.assertIn("into something other than a file", self.fix_run.stderr)

    def test_should_remove_its_copy(self) -> None:
        formatted_copy = find_formatted_copy(self.tool_runs)
        self.assertEqual(formatted_copy.parent, self.temporary_directory)
        self.assertNotIn(formatted_copy.name, self.temporary_entries)


class TheFixOptionWhenATrackedFileChangesWhileTheFormattersRun(InstallationTestCase):
    edited_text: ClassVar[str] = "edited meanwhile\n"
    fix_run: ClassVar[ScriptRun]
    text_after: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        dev = installation.worktree / "scripts" / "dev.sh"
        installation.answer_docker(
            [
                {
                    "match": r" ruff format \.$",
                    "files": {"/src/scripts/dev.sh": "formatted\n"},
                    "host_files": {str(dev): cls.edited_text},
                }
            ]
        )
        cls.fix_run = fix(installation)
        cls.text_after = dev.read_text()

    def test_should_fail_and_name_the_file_that_changed(self) -> None:
        self.assertNotEqual(self.fix_run.returncode, 0)
        self.assertIn("scripts/dev.sh changed in the checkout", self.fix_run.stderr)

    def test_should_keep_the_edit(self) -> None:
        self.assertEqual(self.text_after, self.edited_text)


class TheFixOptionWhenATrackedFileIsMarkedAssumeUnchanged(InstallationTestCase):
    # git diff would not show what a formatter changed there.
    fix_run: ClassVar[ScriptRun]
    runs: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        installation.run_git(installation.worktree, "update-index", "--assume-unchanged", "scripts/dev.sh")
        cls.fix_run = fix(installation)
        cls.runs = list_runs(installation.read_docker_calls())

    def test_should_refuse_and_name_the_file(self) -> None:
        self.assertNotEqual(self.fix_run.returncode, 0)
        self.assertIn("scripts/dev.sh", self.fix_run.stderr)

    def test_should_run_no_formatter(self) -> None:
        self.assertEqual(self.runs, [])


class TheFixOptionWhenAFileOfTheAppIsMarkedAssumeUnchanged(InstallationTestCase):
    # ktlint formats android/ in place, where git diff would not show what it changed.
    fix_run: ClassVar[ScriptRun]
    runs: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        commit_in_worktree(installation, "android/Example.kt", "class Example\n")
        installation.run_git(installation.worktree, "update-index", "--assume-unchanged", "android/Example.kt")
        cls.fix_run = fix(installation)
        cls.runs = list_runs(installation.read_docker_calls())

    def test_should_refuse_and_name_the_file(self) -> None:
        self.assertNotEqual(self.fix_run.returncode, 0)
        self.assertIn("android/Example.kt", self.fix_run.stderr)

    def test_should_run_no_formatter(self) -> None:
        self.assertEqual(self.runs, [])


class TheFixOptionWhenEveryToolLeavesFindings(InstallationTestCase):
    runs: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        fixer_command_pattern = r"ruff check --fix|ruff format \.$| -w -- |biome check --write|ktlintFormat"
        installation.answer_docker([{"match": fixer_command_pattern, "exit": 1}])
        fix(installation)
        cls.runs = [" ".join(argv) for argv in list_runs(installation.read_docker_calls())]

    def test_should_still_run_every_tool(self) -> None:
        for fixer_command in FIXER_COMMANDS:
            with self.subTest(fixer_command):
                self.assertTrue(any(fixer_command in run for run in self.runs), self.runs)


class TheFixOptionWhenOneToolLeavesFindings(InstallationTestCase):
    failing_command_patterns: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "ruff check": r" ruff check --fix \.$",
            "ruff format": r" ruff format \.$",
            "shfmt": r" -w -- ",
            "biome": "biome check --write",
            "ktlint": "ktlintFormat",
        }
    )
    fix_runs: ClassVar[dict[str, ScriptRun]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.fix_runs = {}
        for row, command_pattern in cls.failing_command_patterns.items():
            installation.answer_docker([{"match": command_pattern, "exit": 1}])
            cls.fix_runs[row] = fix(installation)

    def test_should_fail_and_say_what_is_left_to_fix_by_hand(self) -> None:
        self.assertEqual(sorted(self.fix_runs), sorted(self.failing_command_patterns))
        for row, fix_run in self.fix_runs.items():
            with self.subTest(row):
                self.assertNotEqual(fix_run.returncode, 0)
                self.assertIn("left to fix by hand", fix_run.stderr)


class TheFixOptionWhenGivenAnArea(InstallationTestCase):
    fix_run: ClassVar[ScriptRun]
    docker_calls: ClassVar[list[LoggedCall]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.fix_run = check(installation, "--fix", "server")
        cls.docker_calls = installation.read_docker_calls()

    def test_should_refuse_since_it_takes_none(self) -> None:
        self.assertNotEqual(self.fix_run.returncode, 0)
        self.assertIn("--fix takes no area", self.fix_run.stderr)

    def test_should_call_docker_for_nothing(self) -> None:
        self.assertEqual(self.docker_calls, [])


if __name__ == "__main__":
    unittest.main()
