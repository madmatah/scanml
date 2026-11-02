"""The workflows of the repository (.github/workflows/): what they may write, and what they run.

Standard library only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import itertools
import re
import shlex
import textwrap
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
WORKFLOW_NAMES = ("ci.yml", "release.yml", "vulnerability-scan.yml")
WRITING_WORKFLOW_NAMES = ("release.yml", "vulnerability-scan.yml")
OCR = Path(__file__).resolve().parents[2] / "ocr"
WRITING_PERMISSION_PATTERN = r"[\"']?[a-z-]+[\"']?\s*:\s*[\"']?write\b[\"']?|\bwrite-all\b"

RESOLUTION_CONTAINER = (
    "run", "--rm", "--read-only",
    "--tmpfs", "/tmp",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--user", "$(id -u):$(id -g)",
    "-v", "$GITHUB_WORKSPACE/ocr/setup:/requirements:ro",
    "-v", "$work:/work",
    "-e", "HOME=/work",
    "$SANDBOX_PYTHON_IMAGE",
)  # fmt: skip
SCANNER_CONTAINER = (
    "run", "--rm", "--read-only",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--user", "$(id -u):$(id -g)",
    "-w", "$GITHUB_WORKSPACE",
    "-v", "$GITHUB_WORKSPACE:$GITHUB_WORKSPACE:ro",
    "-v", "$results/environments:$results/environments:ro",
    "-v", "$images:$images:ro",
    "-v", "$scratch:$scratch",
    "-e", "TMPDIR=$scratch",
    "-e", "HOME=$scratch",
    "$OSV_SCANNER_IMAGE",
)  # fmt: skip
IMAGE_COMMANDS = (
    ("build", "--iidfile", "$RUNNER_TEMP/api-image-id", "--target", "runtime", "server"),
    ("build", "--iidfile", "$RUNNER_TEMP/sandbox-image-id", "ocr"),
    ("save", "-o", "$images/api-image.tar", "$(< $RUNNER_TEMP/api-image-id)"),
    ("save", "-o", "$images/sandbox-image.tar", "$(< $RUNNER_TEMP/sandbox-image-id)"),
)  # fmt: skip
DOCKER_CALLS = (RESOLUTION_CONTAINER, *IMAGE_COMMANDS, SCANNER_CONTAINER)
MOUNTED_DIRECTORIES = {
    "work": "$RUNNER_TEMP/resolution",
    "scratch": "$RUNNER_TEMP/scanner",
    "results": "$RUNNER_TEMP/scan-results",
    "images": "$RUNNER_TEMP/images",
    "environments": "$RUNNER_TEMP/scan-results/environments",
}
UPLOADED_PATH = "$RUNNER_TEMP/scan-results/"
UNUPLOADED_DIRECTORIES = ("work", "scratch")
NAMES_A_SCRIPT_NEVER_ASSIGNS = ("RUNNER_TEMP", "GITHUB_WORKSPACE", "SANDBOX_PYTHON_IMAGE", "OSV_SCANNER_IMAGE")
IMAGE_NAMES = ("SANDBOX_PYTHON_IMAGE", "OSV_SCANNER_IMAGE")

RESOLUTION_START_ANCHOR = "docker run --rm --read-only --tmpfs"
WORK_MOUNT_ANCHOR = '-v "$work:/work"'
RESOLUTION_TMPFS_ANCHOR = "--tmpfs /tmp"
RESOLUTION_DIRECTORIES_ANCHOR = '          mkdir -p "$environments" "$work"\n'

RUN_KEY_PATTERN = re.compile(r"^(?P<prefix>[ \t]*(?:-[ \t]+)?)run[ \t]*:(?P<inline_text>.*)$")
BLOCK_SCALAR_HEADER_PATTERN = re.compile(r"\|[+-]?(?:[ \t]+#.*)?")
STEP_START_PATTERN = re.compile(r"^[ \t]*-[ \t]")
PATH_KEY_PATTERN = re.compile(r"^(?P<prefix>[ \t]*)path[ \t]*:[ \t]*(?P<path>.*)$")
RUNNER_TEMP_EXPRESSION_PATTERN = re.compile(r"\$\{\{\s*runner\.temp\s*\}\}")
SEPARATOR_PATTERN = re.compile(r"[();<>|&\n]+")
ASSIGNMENT_PATTERN = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\+?=(?P<assigned_text>.*)", re.DOTALL)
JOB_CONTAINER_PATTERN = re.compile(r"^[ \t]*(?:-[ \t]+)?[\"']?(?:container|services)[\"']?[ \t]*:", re.MULTILINE)
TOP_LEVEL_ENVIRONMENT_PATTERN = re.compile(r"^env:[ \t]*\n(?P<keys>(?:[ \t]+.*\n|[ \t]*\n)*)", re.MULTILINE)


@dataclass(frozen=True)
class DockerDeviations:
    docker_words: tuple[str, ...]
    docker_calls: tuple[str, ...]
    unreadable_scripts: tuple[str, ...]
    resolution_container: tuple[str, ...]
    scanner_container: tuple[str, ...]
    image_commands: tuple[str, ...]
    mounted_directories: tuple[str, ...]
    uploaded_path: tuple[str, ...]
    job_containers: tuple[str, ...]
    docker_variables: tuple[str, ...]
    pinned_names: tuple[str, ...]


@dataclass(frozen=True)
class RunScripts:
    scripts: tuple[str, ...]
    unreadable_lines: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowMutation:
    name: str
    anchor: str
    replacement: str
    rule: str


def _measure_indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _select_lines_nested_under(lines: list[str], index: int, key_column: int) -> list[str]:
    return list(
        itertools.takewhile(
            lambda line: not line.strip() or _measure_indentation(line) > key_column, lines[index + 1 :]
        )
    )


def _find_parent_key(lines: list[str], index: int, key_column: int) -> str:
    return next(
        (line.strip() for line in reversed(lines[:index]) if line.strip() and _measure_indentation(line) < key_column),
        "",
    )


def read_run_scripts(workflow_text: str) -> RunScripts:
    lines = workflow_text.splitlines()
    scripts: list[str] = []
    unreadable_lines: list[str] = []
    for index, line in enumerate(lines):
        run_key = RUN_KEY_PATTERN.match(line)
        if run_key is None:
            continue
        key_column = len(run_key["prefix"])
        inline_text = run_key["inline_text"].strip()
        nested_lines = _select_lines_nested_under(lines, index, key_column)
        is_continued = any(nested_line.strip() for nested_line in nested_lines)
        if BLOCK_SCALAR_HEADER_PATTERN.fullmatch(inline_text):
            scripts.append(textwrap.dedent("\n".join(nested_lines)))
        elif inline_text and inline_text[0] not in ">|\"'&*!{[%@`" and not is_continued:
            scripts.append(inline_text)
        elif inline_text or _find_parent_key(lines, index, key_column) != "defaults:":
            unreadable_lines.append(f"line {index + 1}: {line.strip()}")
    return RunScripts(tuple(scripts), tuple(unreadable_lines))


def tokenize_script(script: str) -> tuple[str, ...]:
    lexer = shlex.shlex(re.sub(r"\\\n[ \t]*", " ", script), posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace_split = True
    lexer.whitespace = " \t"
    return tuple(lexer)


def find_docker_call_arguments(tokens: tuple[str, ...]) -> list[tuple[str, ...]]:
    return [
        tuple(itertools.takewhile(lambda argument: not SEPARATOR_PATTERN.fullmatch(argument), tokens[index + 1 :]))
        for index, token in enumerate(tokens)
        if token == "docker"
    ]


def collect_assignments(tokens: tuple[str, ...]) -> dict[str, list[str]]:
    assignments: dict[str, list[str]] = {}
    for token in tokens:
        assignment = ASSIGNMENT_PATTERN.fullmatch(token)
        if assignment is not None:
            assignments.setdefault(assignment["name"], []).append(assignment["assigned_text"])
    return assignments


def _find_container_deviations(call: tuple[str, ...] | None, container: tuple[str, ...]) -> tuple[str, ...]:
    options = call[: len(container)] if call is not None else None
    return () if options == container else (f"docker {options} where the allowlist has docker {container}",)


def _lies_under(inner_path: str, outer_path: str) -> bool:
    return (inner_path.rstrip("/") + "/").startswith(outer_path.rstrip("/") + "/")


def _find_uploaded_path_deviations(lines: list[str], assignments: dict[str, list[str]]) -> tuple[str, ...]:
    upload_indexes = [index for index, line in enumerate(lines) if "actions/upload-artifact" in line]
    deviations = (
        [] if len(upload_indexes) == 1 else [f"{len(upload_indexes)} upload-artifact steps, where one is allowed"]
    )
    uploaded_paths: list[str] = []
    for upload_index in upload_indexes:
        step_index = next(
            (index for index in range(upload_index, -1, -1) if STEP_START_PATTERN.match(lines[index])), upload_index
        )
        step_lines = [
            lines[step_index],
            *_select_lines_nested_under(lines, step_index, _measure_indentation(lines[step_index])),
        ]
        path_keys = [
            (position, path_key)
            for position, line in enumerate(step_lines)
            if (path_key := PATH_KEY_PATTERN.match(line)) is not None
        ]
        if len(path_keys) != 1:
            deviations.append(
                f"the upload at line {upload_index + 1} has {len(path_keys)} path keys, where one is allowed"
            )
        for position, path_key in path_keys:
            uploaded_path = RUNNER_TEMP_EXPRESSION_PATTERN.sub("$RUNNER_TEMP", path_key["path"].strip())
            uploaded_paths.append(uploaded_path)
            if (
                _select_lines_nested_under(step_lines, position, len(path_key["prefix"])) != []
                or uploaded_path != UPLOADED_PATH
            ):
                deviations.append(f"the upload's path is {path_key['path']!r}, where the allowlist has {UPLOADED_PATH}")
    deviations += [
        f"{name}={directory} lies under or holds the uploaded path {uploaded_path}"
        for name in UNUPLOADED_DIRECTORIES
        for directory in assignments.get(name, [])
        for uploaded_path in uploaded_paths
        if _lies_under(directory, uploaded_path) or _lies_under(uploaded_path, directory)
    ]
    return tuple(deviations)


def _find_pinned_name_deviations(workflow_text: str, assignments: dict[str, list[str]]) -> tuple[str, ...]:
    top_level_environment = TOP_LEVEL_ENVIRONMENT_PATTERN.search(workflow_text)
    top_level_keys = top_level_environment["keys"] if top_level_environment is not None else ""
    return (
        *(f"a script assigns {name}" for name in NAMES_A_SCRIPT_NEVER_ASSIGNS if name in assignments),
        *(
            f"{name} is not a key exactly once in the whole workflow, in its top-level env"
            for name in IMAGE_NAMES
            if len(re.findall(rf"(?<![\w$]){name}[\"']?[ \t]*:(?:[ \t]|$)", workflow_text, re.MULTILINE)) != 1
            or len(re.findall(rf"^  {name}:", top_level_keys, re.MULTILINE)) != 1
        ),
    )


def find_docker_deviations(workflow_text: str) -> DockerDeviations:
    lines = workflow_text.splitlines()
    run_scripts = read_run_scripts(workflow_text)
    script_tokens = [tokenize_script(script) for script in run_scripts.scripts]
    calls = [call for tokens in script_tokens for call in find_docker_call_arguments(tokens)]
    assignments = collect_assignments(tuple(token for tokens in script_tokens for token in tokens))
    word_count = len(re.findall(r"\bdocker\b", workflow_text))
    subcommands = tuple(call[0] if call else "" for call in calls)
    allowed_subcommands = tuple(call[0] for call in DOCKER_CALLS)
    container_calls = [call for call in calls if call[:1] == ("run",)]
    image_commands = tuple(call for call in calls if call[:1] in (("build",), ("save",)))
    return DockerDeviations(
        docker_words=(
            (f"the word docker {word_count} times for {len(calls)} calls",) if word_count != len(calls) else ()
        ),
        docker_calls=(
            ()
            if subcommands == allowed_subcommands
            else (f"docker {subcommands} where the allowlist has {allowed_subcommands}",)
        ),
        unreadable_scripts=tuple(
            f"a run value that is no script the test reads, {unreadable_line}"
            for unreadable_line in run_scripts.unreadable_lines
        ),
        resolution_container=_find_container_deviations(
            container_calls[0] if container_calls else None, RESOLUTION_CONTAINER
        ),
        scanner_container=_find_container_deviations(
            container_calls[-1] if container_calls else None, SCANNER_CONTAINER
        ),
        image_commands=(
            () if image_commands == IMAGE_COMMANDS else (f"{image_commands} where the allowlist has {IMAGE_COMMANDS}",)
        ),
        mounted_directories=(
            *(f"{name} is never assigned" for name in MOUNTED_DIRECTORIES if name not in assignments),
            *(
                f"{name}={directory}, where the allowlist has {pinned_directory}"
                for name, pinned_directory in MOUNTED_DIRECTORIES.items()
                for directory in assignments.get(name, [])
                if directory != pinned_directory
            ),
        ),
        uploaded_path=_find_uploaded_path_deviations(lines, assignments),
        job_containers=tuple(JOB_CONTAINER_PATTERN.findall(workflow_text)),
        docker_variables=tuple(re.findall(r"DOCKER_[A-Z_]+", workflow_text)),
        pinned_names=_find_pinned_name_deviations(workflow_text, assignments),
    )


class TheWritingPermissionPatternWhenAPermissionWrites(unittest.TestCase):
    permissions: ClassVar[tuple[str, ...]] = (
        'contents: "write"',
        "pull-requests:\twrite",
        "permissions: write-all",
        "contents: write  # x",
        "contents: 'write'",
        '"contents": write',
        "'pull-requests': write",
        "contents : write",
        'permissions: {"contents": write}',
    )

    def setUp(self) -> None:
        self.matches = {
            permission: re.findall(WRITING_PERMISSION_PATTERN, permission) for permission in self.permissions
        }

    def test_should_match_it_however_it_is_written_so_that_the_workflow_tests_see_every_write(self) -> None:
        for permission in self.permissions:
            with self.subTest(permission):
                self.assertNotEqual(self.matches[permission], [])


class TheWritingPermissionPatternWhenNoPermissionWrites(unittest.TestCase):
    def setUp(self) -> None:
        self.matches = re.findall(WRITING_PERMISSION_PATTERN, "contents: read\n# it writes nothing\n")

    def test_should_match_nothing_even_where_a_comment_says_write(self) -> None:
        self.assertEqual(self.matches, [])


class TheWorkflowsOfTheRepository(unittest.TestCase):
    action_reference_pattern: ClassVar[re.Pattern[str]] = re.compile(r"^\s*(?:- )?uses: (\S+)", re.MULTILINE)

    def setUp(self) -> None:
        self.workflows = {workflow.name: workflow.read_text() for workflow in sorted(WORKFLOWS.glob("*.y*ml"))}
        self.actions = [
            (name, action)
            for name, text in self.workflows.items()
            for action in self.action_reference_pattern.findall(text)
        ]

    def test_should_be_the_ci_release_and_vulnerability_scan_workflows_alone_so_that_a_new_one_is_checked_here(
        self,
    ) -> None:
        self.assertEqual(list(self.workflows), list(WORKFLOW_NAMES))

    def test_should_use_no_secret(self) -> None:
        self.assertEqual(len(self.workflows), len(WORKFLOW_NAMES))
        for name, text in self.workflows.items():
            with self.subTest(name):
                self.assertNotIn("secrets.", text)

    def test_should_never_run_on_pull_request_target(self) -> None:
        self.assertEqual(len(self.workflows), len(WORKFLOW_NAMES))
        for name, text in self.workflows.items():
            with self.subTest(name):
                self.assertNotRegex(text, r"\bpull_request_target\b")

    def test_should_use_only_the_checkout_and_cache_actions_pinned_to_a_commit_but_the_scan_which_has_its_own_list(
        self,
    ) -> None:
        actions_outside_the_scan = [(name, action) for name, action in self.actions if name != "vulnerability-scan.yml"]
        self.assertGreater(len(actions_outside_the_scan), 0)
        for name, action in actions_outside_the_scan:
            with self.subTest(workflow=name, action=action):
                self.assertRegex(action, r"^actions/checkout@[0-9a-f]{40}$|^actions/cache@[0-9a-f]{40}$")


class TheWorkflowsThatWriteNothing(unittest.TestCase):
    def setUp(self) -> None:
        self.workflows = {
            workflow.name: workflow.read_text()
            for workflow in sorted(WORKFLOWS.glob("*.y*ml"))
            if workflow.name not in WRITING_WORKFLOW_NAMES
        }

    def test_should_write_nothing(self) -> None:
        self.assertEqual(len(self.workflows), len(WORKFLOW_NAMES) - len(WRITING_WORKFLOW_NAMES))
        for name, text in self.workflows.items():
            with self.subTest(name):
                self.assertEqual(re.findall(WRITING_PERMISSION_PATTERN, text), [])

    def test_should_only_read_the_contents_of_the_repository(self) -> None:
        self.assertEqual(len(self.workflows), len(WORKFLOW_NAMES) - len(WRITING_WORKFLOW_NAMES))
        for name, text in self.workflows.items():
            with self.subTest(name):
                self.assertRegex(text, r"\npermissions:\n  contents: read\n")


class TheReleaseWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (WORKFLOWS / "release.yml").read_text()
        self.triggers = self.text.split("\non:\n", 1)[1].split("\n\n", 1)[0]

    def test_should_write_the_contents_of_the_repository_alone(self) -> None:
        self.assertEqual(re.findall(WRITING_PERMISSION_PATTERN, self.text), ["contents: write"])

    def test_should_run_on_a_push_to_main_that_changes_version_or_the_changelog(self) -> None:
        self.assertEqual(self.triggers, "  push:\n    branches: [main]\n    paths: [VERSION, CHANGELOG.md]")

    def test_should_grant_no_permission_unless_a_job_asks_for_it(self) -> None:
        self.assertIn("\npermissions: {}\n", self.text)

    def test_should_not_keep_the_credentials_of_its_checkout(self) -> None:
        self.assertIn("persist-credentials: false", self.text)

    def test_should_fetch_the_whole_history_since_release_py_reads_the_history_and_the_tags(self) -> None:
        self.assertIn("fetch-depth: 0", self.text)

    def test_should_use_the_checkout_action_alone_pinned_to_its_commit(self) -> None:
        self.assertEqual(
            re.findall(r"uses: (\S+)", self.text), ["actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"]
        )

    def test_should_ask_release_py_what_the_commit_publishes(self) -> None:
        self.assertIn('python3 scripts/release.py --ref "$COMMIT" --to-publish', self.text)

    def test_should_tag_the_commit_release_py_names_never_the_head_of_the_push(self) -> None:
        self.assertIn('read -r version target <<< "$release"', self.text)
        self.assertIn('-f object="$target"', self.text)
        self.assertEqual(self.text.count("$COMMIT"), 1)


class TheVulnerabilityScanWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (WORKFLOWS / "vulnerability-scan.yml").read_text()
        self.top_level, jobs = self.text.split("\njobs:\n", 1)
        self.scan_job, self.upload_job = jobs.split("\n  upload:\n", 1)
        self.triggers = self.text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
        self.scan_job_permissions = re.findall(r"\n    permissions:\n((?:      .*\n)+)", self.scan_job)
        self.upload_job_commands = re.findall(r"^\s*(?:- )?run:", self.upload_job, re.MULTILINE)
        self.upload_job_actions = [
            action.split("@", 1)[0]
            for action in TheWorkflowsOfTheRepository.action_reference_pattern.findall(self.upload_job)
        ]
        self.scanned_categories = sorted(re.findall(r"^\s*scan ([a-z0-9-]+) ", self.scan_job, re.MULTILINE))
        self.categories_of_the_uploaded_files = sorted(
            re.findall(r"^\s*sarif_file: .*/sarif/([a-z0-9-]+)\.sarif$", self.text, re.MULTILINE)
        )
        self.uploaded_categories = sorted(re.findall(r"^\s*category: (\S+)$", self.text, re.MULTILINE))
        self.sarif_uploads = re.findall(r"uses: github/codeql-action/upload-sarif@", self.text)
        self.status_handlings = [
            [line.strip() for line in block.splitlines()]
            for block in re.findall(
                r'^[ \t]*> "\$results/sarif/\$category\.sarif" \|\| status=\$\?\n(?:.*\n){4}',
                self.scan_job,
                re.MULTILINE,
            )
        ]
        self.checkouts = re.findall(r"uses: actions/checkout@", self.text)
        self.actions = TheWorkflowsOfTheRepository.action_reference_pattern.findall(self.text)

    def test_should_write_security_events_alone(self) -> None:
        self.assertEqual(re.findall(WRITING_PERMISSION_PATTERN, self.text), ["security-events: write"])

    def test_should_grant_no_permission_unless_a_job_asks_for_it(self) -> None:
        self.assertIn("\npermissions: {}\n", self.top_level)

    def test_should_let_the_scan_job_only_read_the_contents_of_the_repository(self) -> None:
        self.assertEqual(self.scan_job_permissions, ["      contents: read\n"])

    def test_should_give_the_write_to_the_upload_job_alone_so_that_no_scanned_code_holds_it(self) -> None:
        self.assertEqual(re.findall(WRITING_PERMISSION_PATTERN, self.scan_job), [])
        self.assertEqual(re.findall(WRITING_PERMISSION_PATTERN, self.upload_job), ["security-events: write"])

    def test_should_run_no_command_in_the_upload_job(self) -> None:
        self.assertEqual(self.upload_job_commands, [])

    def test_should_use_only_github_s_checkout_artifact_and_sarif_upload_actions_pinned_to_a_commit(self) -> None:
        pinned_action_pattern = re.compile(
            r"^(?:actions/(?:checkout|upload-artifact|download-artifact)|github/codeql-action/upload-sarif)"
            r"@[0-9a-f]{40}$"
        )
        self.assertGreater(len(self.actions), 0)
        self.assertEqual([action for action in self.actions if not pinned_action_pattern.match(action)], [])

    def test_should_use_only_github_s_checkout_download_and_sarif_upload_actions_in_the_upload_job(self) -> None:
        allowed_actions = {"actions/checkout", "actions/download-artifact", "github/codeql-action/upload-sarif"}
        self.assertGreater(len(self.upload_job_actions), 0)
        self.assertEqual([action for action in self.upload_job_actions if action not in allowed_actions], [])

    def test_should_upload_each_scan_under_a_category_of_its_own_since_an_upload_replaces_one_of_its_category(
        self,
    ) -> None:
        self.assertEqual(len(self.scanned_categories), 4)
        self.assertEqual(len(set(self.scanned_categories)), len(self.scanned_categories))
        self.assertEqual(
            (self.categories_of_the_uploaded_files, self.uploaded_categories, len(self.sarif_uploads)),
            (self.scanned_categories, self.scanned_categories, len(self.scanned_categories)),
        )

    def test_should_pass_on_status_1_vulnerabilities_found_and_fail_above_it_so_that_it_reports_and_never_blocks(
        self,
    ) -> None:
        self.assertEqual(
            self.status_handlings,
            [
                [
                    '> "$results/sarif/$category.sarif" || status=$?',
                    "if ((status > 1)); then",
                    'echo "::error::The scan $category failed with the exit status $status"',
                    'return "$status"',
                    "fi",
                ]
            ],
        )

    def test_should_run_every_week_by_hand_and_on_a_push_to_main_that_changes_what_it_scans_never_on_a_pull_request(
        self,
    ) -> None:
        self.assertEqual(
            self.triggers,
            "  schedule:\n"
            '    - cron: "17 5 * * 1"\n'
            "  workflow_dispatch:\n"
            "  push:\n"
            "    branches: [main]\n"
            "    paths:\n"
            "      - .github/workflows/vulnerability-scan.yml\n"
            "      - android/gradle/verification-metadata.xml\n"
            "      - ocr/Dockerfile\n"
            "      - ocr/setup/requirements-*.in\n"
            "      - scripts/lint/requirements.lock\n"
            "      - server/Dockerfile\n"
            "      - server/requirements.lock",
        )

    def test_should_not_keep_the_credentials_of_its_checkouts(self) -> None:
        self.assertGreater(len(self.checkouts), 0)
        self.assertEqual(self.text.count("persist-credentials: false"), len(self.checkouts))

    def test_should_pin_the_scanner_s_image_by_digest(self) -> None:
        self.assertRegex(
            self.top_level, r"\n  OSV_SCANNER_IMAGE: ghcr\.io/google/osv-scanner:v[0-9.]+@sha256:[0-9a-f]{64}\n"
        )


class TheVulnerabilityScanWorkflowWhenItCallsDocker(unittest.TestCase):
    def setUp(self) -> None:
        self.deviations = find_docker_deviations((WORKFLOWS / "vulnerability-scan.yml").read_text())

    def test_should_name_docker_only_where_it_calls_it_so_that_no_call_escapes_the_allowlist(self) -> None:
        self.assertEqual(self.deviations.docker_words, ())

    def test_should_call_docker_only_to_run_the_resolution_build_and_save_both_images_and_run_the_scanner(
        self,
    ) -> None:
        self.assertEqual(self.deviations.docker_calls, ())

    def test_should_write_each_run_value_as_a_script_the_test_reads_so_that_no_docker_call_hides_in_another_form(
        self,
    ) -> None:
        self.assertEqual(self.deviations.unreadable_scripts, ())

    def test_should_run_the_resolution_with_exactly_its_options_so_that_it_mounts_writable_only_its_work_directory(
        self,
    ) -> None:
        self.assertEqual(self.deviations.resolution_container, ())

    def test_should_run_the_scanner_with_exactly_its_options_so_that_it_mounts_writable_only_its_scratch_directory(
        self,
    ) -> None:
        self.assertEqual(self.deviations.scanner_container, ())

    def test_should_build_and_save_the_images_with_exactly_their_arguments_so_that_no_build_gains_a_network_or_output(
        self,
    ) -> None:
        self.assertEqual(self.deviations.image_commands, ())

    def test_should_point_each_mounted_directory_where_the_allowlist_says_so_that_a_mount_cannot_move_into_the_upload(
        self,
    ) -> None:
        self.assertEqual(self.deviations.mounted_directories, ())

    def test_should_upload_the_results_alone_which_hold_neither_the_work_nor_the_scratch_directory(self) -> None:
        self.assertEqual(self.deviations.uploaded_path, ())

    def test_should_start_no_job_container_or_service_since_their_options_escape_the_allowlist_of_the_docker_calls(
        self,
    ) -> None:
        self.assertEqual(self.deviations.job_containers, ())

    def test_should_set_no_variable_of_docker_since_it_would_act_as_a_global_option(self) -> None:
        self.assertEqual(self.deviations.docker_variables, ())

    def test_should_assign_no_runner_directory_or_image_name_in_a_script_and_name_each_image_once_at_the_top(
        self,
    ) -> None:
        self.assertEqual(self.deviations.pinned_names, ())


class TheFindDockerDeviationsFunctionWhenTheWorkflowDeviatesFromTheAllowlist(unittest.TestCase):
    mutations: ClassVar[tuple[WorkflowMutation, ...]] = (
        WorkflowMutation(
            "a resolution that mounts the uploaded environments unquoted instead of its work directory",
            WORK_MOUNT_ANCHOR,
            "-v $environments:/work",
            "resolution_container",
        ),
        WorkflowMutation(
            "a resolution that mounts the results in single quotes",
            WORK_MOUNT_ANCHOR,
            WORK_MOUNT_ANCHOR + " -v '$RUNNER_TEMP/scan-results:/results'",
            "resolution_container",
        ),
        WorkflowMutation(
            "a resolution that mounts the environments without a separator",
            WORK_MOUNT_ANCHOR,
            WORK_MOUNT_ANCHOR + ' -v"$environments:/x"',
            "resolution_container",
        ),
        WorkflowMutation(
            "a resolution that mounts the results with --volume",
            WORK_MOUNT_ANCHOR,
            WORK_MOUNT_ANCHOR + " --volume $RUNNER_TEMP/scan-results:/x",
            "resolution_container",
        ),
        WorkflowMutation(
            "a resolution that mounts the environments with --volume=",
            WORK_MOUNT_ANCHOR,
            WORK_MOUNT_ANCHOR + " --volume=$environments:/x",
            "resolution_container",
        ),
        WorkflowMutation(
            "a resolution that mounts the environments with --mount",
            WORK_MOUNT_ANCHOR,
            WORK_MOUNT_ANCHOR + " --mount type=bind,source=$environments,target=/x",
            "resolution_container",
        ),
        WorkflowMutation(
            "a resolution that mounts the requirements writable",
            '-v "$GITHUB_WORKSPACE/ocr/setup:/requirements:ro"',
            '-v "$GITHUB_WORKSPACE/ocr/setup:/requirements"',
            "resolution_container",
        ),
        WorkflowMutation(
            "a scanner that mounts the images writable",
            '-v "$images:$images:ro"',
            '-v "$images:$images"',
            "scanner_container",
        ),
        WorkflowMutation(
            "a scanner that mounts the results writable",
            '-v "$scratch:$scratch"',
            '-v "$scratch:$scratch" -v "$results:$results"',
            "scanner_container",
        ),
        WorkflowMutation(
            "a work directory moved under the results, against its pin",
            "work=$RUNNER_TEMP/resolution",
            "work=$RUNNER_TEMP/scan-results/resolution",
            "mounted_directories",
        ),
        WorkflowMutation(
            "a work directory moved under the results, against the upload",
            "work=$RUNNER_TEMP/resolution",
            "work=$RUNNER_TEMP/scan-results/resolution",
            "uploaded_path",
        ),
        WorkflowMutation(
            "a work directory that holds the results, against the upload",
            "work=$RUNNER_TEMP/resolution",
            "work=$RUNNER_TEMP",
            "uploaded_path",
        ),
        WorkflowMutation(
            "a scratch directory moved under the results, against its pin",
            "scratch=$RUNNER_TEMP/scanner",
            "scratch=$RUNNER_TEMP/scan-results/scanner",
            "mounted_directories",
        ),
        WorkflowMutation(
            "a scratch directory moved under the results, against the upload",
            "scratch=$RUNNER_TEMP/scanner",
            "scratch=$RUNNER_TEMP/scan-results/scanner",
            "uploaded_path",
        ),
        WorkflowMutation(
            "a second assignment of the work directory after its creation",
            RESOLUTION_DIRECTORIES_ANCHOR,
            RESOLUTION_DIRECTORIES_ANCHOR + "          work=$environments\n",
            "mounted_directories",
        ),
        WorkflowMutation(
            "an upload widened to the whole temporary directory of the runner",
            "path: ${{ runner.temp }}/scan-results/",
            "path: ${{ runner.temp }}/",
            "uploaded_path",
        ),
        *(
            WorkflowMutation(
                f"a resolution that gains {option}",
                RESOLUTION_TMPFS_ANCHOR,
                f"{RESOLUTION_TMPFS_ANCHOR} {option}",
                "resolution_container",
            )
            for option in (
                "--cap-add SYS_ADMIN",
                "--privileged",
                "--security-opt seccomp=unconfined",
                "--security-opt apparmor=unconfined",
                "--pid host",
                "--ipc host",
                "--userns host",
                "--network host",
                "--device /dev/fuse",
                "-v /var/run/docker.sock:/var/run/docker.sock",
            )
        ),
        WorkflowMutation(
            "a resolution that runs as root",
            '--user "$(id -u):$(id -g)" \\',
            "--user 0:0 \\",
            "resolution_container",
        ),
        WorkflowMutation(
            "a resolution with a writable root filesystem",
            "--read-only --tmpfs",
            "--tmpfs",
            "resolution_container",
        ),
        WorkflowMutation(
            "a scanner that gains --cap-add SYS_ADMIN",
            '-w "$GITHUB_WORKSPACE"',
            '-w "$GITHUB_WORKSPACE" --cap-add SYS_ADMIN',
            "scanner_container",
        ),
        WorkflowMutation(
            "a resolution behind a global option of docker",
            RESOLUTION_START_ANCHOR,
            RESOLUTION_START_ANCHOR.replace("docker run", "docker --context default run"),
            "docker_calls",
        ),
        WorkflowMutation(
            "a resolution through docker container run",
            RESOLUTION_START_ANCHOR,
            RESOLUTION_START_ANCHOR.replace("docker run", "docker container run"),
            "docker_calls",
        ),
        WorkflowMutation(
            "a resolution through the path of docker",
            RESOLUTION_START_ANCHOR,
            "/usr/bin/" + RESOLUTION_START_ANCHOR,
            "docker_words",
        ),
        WorkflowMutation(
            "a new docker create",
            RESOLUTION_DIRECTORIES_ANCHOR,
            RESOLUTION_DIRECTORIES_ANCHOR + '          docker create "$SANDBOX_PYTHON_IMAGE"\n',
            "docker_calls",
        ),
        WorkflowMutation(
            "a new docker compose run",
            RESOLUTION_DIRECTORIES_ANCHOR,
            RESOLUTION_DIRECTORIES_ANCHOR + "          docker compose run resolver\n",
            "docker_calls",
        ),
        WorkflowMutation(
            "a new docker run inside a quoted string",
            RESOLUTION_DIRECTORIES_ANCHOR,
            RESOLUTION_DIRECTORIES_ANCHOR + "          sh -c 'docker run --privileged \"$SANDBOX_PYTHON_IMAGE\"'\n",
            "docker_words",
        ),
        WorkflowMutation(
            "a resolution that reaches another docker daemon",
            RESOLUTION_START_ANCHOR,
            "DOCKER_HOST=tcp://example.invalid:2375 " + RESOLUTION_START_ANCHOR,
            "docker_variables",
        ),
        WorkflowMutation(
            "a scan job that runs in a container",
            "    timeout-minutes: 65\n",
            "    timeout-minutes: 65\n    container: python:3.12-slim-trixie\n",
            "job_containers",
        ),
        WorkflowMutation(
            "a scan job that starts a service",
            "    timeout-minutes: 65\n",
            "    timeout-minutes: 65\n    services:\n      resolver:\n        image: python:3.12-slim-trixie\n",
            "job_containers",
        ),
        WorkflowMutation(
            "a build of the api's image that gains --network host",
            "--target runtime server",
            "--target runtime --network host server",
            "image_commands",
        ),
        WorkflowMutation(
            "a step whose script is a folded scalar",
            "      - name: Build the api's and the sandbox's images\n",
            "      - name: Show the runner\n"
            "        run: >\n"
            "          uname -a\n"
            "      - name: Build the api's and the sandbox's images\n",
            "unreadable_scripts",
        ),
        WorkflowMutation(
            "a new docker run after a blank line of the resolution's script",
            '              > "$environments/paddlepaddle-gpu.txt"\n',
            '              > "$environments/paddlepaddle-gpu.txt"\n\n'
            '          docker run --privileged "$SANDBOX_PYTHON_IMAGE"\n',
            "docker_calls",
        ),
        WorkflowMutation(
            "a script that moves the temporary directory of the runner into the results",
            "          work=$RUNNER_TEMP/resolution\n",
            "          RUNNER_TEMP=$RUNNER_TEMP/scan-results\n          work=$RUNNER_TEMP/resolution\n",
            "pinned_names",
        ),
        WorkflowMutation(
            "a script that sets the resolution's image to the sandbox's",
            '"$(< "$RUNNER_TEMP/sandbox-image-id")"\n',
            '"$(< "$RUNNER_TEMP/sandbox-image-id")"\n'
            '          SANDBOX_PYTHON_IMAGE=$(< "$RUNNER_TEMP/sandbox-image-id")\n',
            "pinned_names",
        ),
        WorkflowMutation(
            "a step that overrides the resolution's image",
            "      - name: Resolve the sandbox's environments as a new installation would, without installing them\n",
            "      - name: Resolve the sandbox's environments as a new installation would, without installing them\n"
            "        env:\n"
            "          SANDBOX_PYTHON_IMAGE: python:3.13-slim-trixie\n",
            "pinned_names",
        ),
        WorkflowMutation(
            "a second upload, of the work directory",
            "          if-no-files-found: error\n",
            "          if-no-files-found: error\n"
            "      - name: Keep the resolution\n"
            "        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2\n"
            "        with:\n"
            "          name: resolution\n"
            "          path: ${{ runner.temp }}/resolution\n",
            "uploaded_path",
        ),
    )

    def setUp(self) -> None:
        workflow_text = (WORKFLOWS / "vulnerability-scan.yml").read_text()
        self.anchor_counts = {mutation.name: workflow_text.count(mutation.anchor) for mutation in self.mutations}
        self.deviations_of_their_rules = {
            mutation.name: getattr(
                find_docker_deviations(workflow_text.replace(mutation.anchor, mutation.replacement, 1)), mutation.rule
            )
            for mutation in self.mutations
        }

    def test_should_find_each_anchor_in_the_workflow_so_that_no_row_checks_a_text_that_does_not_exist(self) -> None:
        self.assertEqual(len(self.anchor_counts), len(self.mutations))
        self.assertEqual({name: count for name, count in self.anchor_counts.items() if count != 1}, {})

    def test_should_report_each_mutation_in_the_field_of_its_rule(self) -> None:
        self.assertGreater(len(self.deviations_of_their_rules), 0)
        for name, deviations in self.deviations_of_their_rules.items():
            with self.subTest(name):
                self.assertNotEqual(deviations, ())


class TheVulnerabilityScanWorkflowWhenItResolvesTheEnvironmentsOfTheSandbox(unittest.TestCase):
    def setUp(self) -> None:
        workflow = (WORKFLOWS / "vulnerability-scan.yml").read_text()
        dockerfile = (OCR / "Dockerfile").read_text()
        installer = re.sub(r"\\\n\s*", " ", (OCR / "setup" / "install.sh").read_text())
        paddle_requirements = (OCR / "setup" / "requirements-paddle.in").read_text()
        self.workflow = workflow
        self.resolution_images = re.findall(r"^  SANDBOX_PYTHON_IMAGE: (\S+)$", workflow, re.MULTILINE)
        self.sandbox_images = re.findall(r"^FROM (\S+)$", dockerfile, re.MULTILINE)
        self.resolution_uv_versions = re.findall(r"^  SANDBOX_UV_VERSION: (\S+)$", workflow, re.MULTILINE)
        self.sandbox_uv_versions = re.findall(r"\buv==(\S+)", dockerfile)
        self.installations = re.findall(r"^\s*uv pip install .*$", installer, re.MULTILINE)
        self.installed_requirements = sorted(set(re.findall(r'"\$SETUP_DIR/(requirements-[^"]+\.in)"', installer)))
        self.setup_requirements = sorted(path.name for path in (OCR / "setup").glob("requirements-*.in"))
        self.scanned_paddle_versions = re.findall(r"^  PADDLE_VERSION: (\S+)$", workflow, re.MULTILINE)
        self.wheel_versions = re.findall(r"/paddlepaddle_gpu-([^-]+)-", paddle_requirements)
        self.requirement_lines = [
            (path.name, line)
            for path in sorted((OCR / "setup").glob("requirements-*.in"))
            for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    def test_should_resolve_in_the_base_image_of_the_sandbox(self) -> None:
        self.assertEqual(len(self.sandbox_images), 1)
        self.assertEqual(self.resolution_images, self.sandbox_images)

    def test_should_resolve_with_the_uv_version_of_the_sandbox_s_image(self) -> None:
        self.assertEqual(len(self.sandbox_uv_versions), 1)
        self.assertEqual(self.resolution_uv_versions, self.sandbox_uv_versions)

    def test_should_resolve_every_requirements_file_of_the_sandbox_s_setup(self) -> None:
        self.assertIn('for requirements in "$GITHUB_WORKSPACE"/ocr/setup/requirements-*.in; do', self.workflow)

    def test_should_find_in_the_sandbox_s_setup_exactly_the_files_the_installer_installs_from_so_it_scans_them_all(
        self,
    ) -> None:
        self.assertEqual(len(self.setup_requirements), 2)
        self.assertEqual(self.installed_requirements, self.setup_requirements)

    def test_should_find_the_installer_installing_each_environment_from_one_requirements_file_and_nothing_else(
        self,
    ) -> None:
        installation_from_one_file = re.compile(
            r'^\s*uv pip install --python "\$SANDBOX/venv-[a-z]+/bin/python" -r "\$SETUP_DIR/requirements-[a-z]+\.in"$'
        )
        self.assertEqual(len(self.installations), 2)
        self.assertEqual(
            [installation for installation in self.installations if not installation_from_one_file.match(installation)],
            [],
        )

    def test_should_find_no_option_in_the_requirements_files_so_that_neither_install_nor_scan_uses_another_index(
        self,
    ) -> None:
        self.assertGreater(len(self.requirement_lines), 0)
        self.assertEqual([(name, line) for name, line in self.requirement_lines if line.lstrip().startswith("-")], [])

    def test_should_scan_paddle_s_gpu_build_at_the_version_in_its_wheel_s_file_name(self) -> None:
        self.assertEqual(len(self.wheel_versions), 1)
        self.assertEqual(self.scanned_paddle_versions, self.wheel_versions)


if __name__ == "__main__":
    unittest.main()
