"""The areas of the gate that a commit touches (scripts/lib/commit_areas.py).

Standard library and git only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from git_environment import isolated_git_environment, run_git

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import commit_areas

EVERY_AREA = ["lint", "scripts", "web", "server", "ocr", "android", "integration"]


# One path for each rule of commit_areas.PATH_RULES, and the areas a commit that changes it alone is checked on.
AREAS_OF_EACH_PATH = {
    ".claude/skills/pull-request/scripts/publish_screenshots.py": ["lint", "integration"],
    ".claude/rules/tests.md": [],
    "docs/foundations.md": [],
    "CLAUDE.md": [],
    "README.md": [],
    "CREDITS.md": [],
    "CHANGELOG.md": [],
    "LICENSE": [],
    ".github/pull_request_template.md": [],
    ".github/workflows/ci.yml": ["lint", "scripts"],
    "android/app/build.gradle.kts": ["android"],
    "ocr/scanmylib_ocr/manager.py": ["lint", "ocr"],
    "server/scanmylib/web/static/js/main.js": ["lint", "web", "server"],
    "server/README.md": ["lint", "server"],
    "scripts/check.sh": EVERY_AREA,
    "scripts/lib/common.sh": EVERY_AREA,
    "scripts/build-apk.sh": ["lint", "scripts", "android", "integration"],
    "scripts/lib/stack.py": ["lint", "scripts", "android", "integration"],
    "scripts/lib/version.py": ["lint", "scripts", "android", "integration"],
    "scripts/lint/requirements.lock": ["lint"],
    "scripts/tests/test_release.py": ["lint", "scripts"],
    "scripts/integration_tests/test_deploy.py": ["lint", "integration"],
    "scripts/release.py": ["lint", "scripts"],
    "scripts/vendor-katex.sh": ["lint"],
    "scripts/dev.sh": ["lint", "scripts", "integration"],
    "ruff.toml": ["lint"],
    "mypy.ini": ["lint"],
    ".shellcheckrc": ["lint"],
}


def commit(repository: Path, message: str) -> None:
    run_git(repository, "add", "--all")
    run_git(repository, "commit", "--quiet", "--message", message)


def read_printed_areas(repository: Path) -> list[str]:
    output = io.StringIO()
    with redirect_stdout(output):
        commit_areas.main([str(repository)])
    return output.getvalue().split()


def build_repository(test: unittest.TestCase) -> Path:
    # commit_areas.py runs git in the test's process, with its environment.
    test.enterContext(isolated_git_environment())
    directory = tempfile.TemporaryDirectory(prefix="scanmylib-areas-")
    test.addCleanup(directory.cleanup)
    repository = Path(directory.name)
    run_git(repository, "init", "--quiet", "--initial-branch=main")
    (repository / "docs").mkdir()
    (repository / "docs" / "guide.md").write_text("# Guide\n")
    (repository / "scripts").mkdir()
    (repository / "scripts" / "tool.py").write_text("print('tool')\n")
    return repository


class TheListAreasTouchedFunctionWhenAPathIsChangedAlone(unittest.TestCase):
    def setUp(self) -> None:
        self.reached_areas = {path: commit_areas.list_areas_touched([path]) for path in AREAS_OF_EACH_PATH}

    def test_should_check_the_areas_that_read_the_path_and_no_other(self) -> None:
        self.assertEqual(len(self.reached_areas), len(commit_areas.PATH_RULES))
        for path, expected in AREAS_OF_EACH_PATH.items():
            with self.subTest(path=path):
                self.assertEqual(self.reached_areas[path], expected)


class ThePathRulesConstant(unittest.TestCase):
    def setUp(self) -> None:
        self.rules_with_a_path = {commit_areas.find_rule(path) for path in AREAS_OF_EACH_PATH}

    def test_should_have_a_path_of_the_tests_above_for_every_rule_so_that_a_new_rule_states_what_it_reaches(
        self,
    ) -> None:
        self.assertEqual(self.rules_with_a_path, set(commit_areas.PATH_RULES))


class TheListAreasTouchedFunctionWhenNoRuleKnowsThePath(unittest.TestCase):
    def setUp(self) -> None:
        path_no_rule_knows = "compose.yaml"
        self.areas = commit_areas.list_areas_touched([path_no_rule_knows])

    def test_should_check_every_area_so_that_a_file_nobody_thought_of_is_checked_rather_than_skipped(self) -> None:
        self.assertEqual(self.areas, EVERY_AREA)


class TheListAreasTouchedFunctionWhenAShellScriptLiesWhereNoAreaReads(unittest.TestCase):
    def setUp(self) -> None:
        hook_script = ".claude/hooks/install.sh"
        self.areas = commit_areas.list_areas_touched([hook_script])

    def test_should_lint_it_since_the_lint_area_checks_every_shell_script(self) -> None:
        self.assertEqual(self.areas, ["lint"])


class TheListAreasTouchedFunctionWhenPathsReachSeveralAreas(unittest.TestCase):
    def setUp(self) -> None:
        changed_paths = ["server/scanmylib/app.py", "scripts/release.py", "server/tests/test_db.py"]
        self.areas = commit_areas.list_areas_touched(changed_paths)

    def test_should_list_each_area_once_in_the_gate_s_order(self) -> None:
        self.assertEqual(self.areas, ["lint", "scripts", "server"])


class TheMainFunctionWhenTheLastCommitHasNoParent(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = build_repository(self)
        commit(self.repository, "docs: start the guide")
        self.areas = read_printed_areas(self.repository)

    def test_should_check_every_area_so_that_a_first_commit_is_checked_whole(self) -> None:
        self.assertEqual(self.areas, EVERY_AREA)


class TheMainFunctionWhenTheLastCommitChangesDocumentsOnly(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = build_repository(self)
        commit(self.repository, "feat(scripts): add the tool")
        (self.repository / "docs" / "guide.md").write_text("# Guide\n\nHow to use the tool.\n")
        commit(self.repository, "docs: say how to use the tool")
        self.areas = read_printed_areas(self.repository)

    def test_should_check_no_area(self) -> None:
        self.assertEqual(self.areas, [])


class TheMainFunctionWhenTheLastCommitMovesAFileOutOfAnArea(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = build_repository(self)
        commit(self.repository, "feat(scripts): add the tool")
        (self.repository / "scripts" / "tool.py").rename(self.repository / "docs" / "tool.py")
        commit(self.repository, "docs: keep the tool as an example")
        self.areas = read_printed_areas(self.repository)

    def test_should_check_the_area_it_left_so_that_what_used_the_file_is_checked_without_it(self) -> None:
        self.assertEqual(self.areas, ["lint", "scripts", "integration"])


if __name__ == "__main__":
    unittest.main()
