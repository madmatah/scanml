"""The integration tests of the scripts: the scripts themselves, against a throwaway repository and a docker stand-in
(docker_shim.py).

Each test builds, in a temporary directory: a bare "origin", production's checkout (at
~/Dev/scanmylib of a temporary home directory, with a production .env whose paths are all
temporary) on the release VERSION, published on origin (the tag vVERSION), and a worktree, with
the scripts of this checkout. `docker` is the stand-in: docker
compose only resolves configurations (offline), any other call is logged and answered by the
test's rules; nothing reaches the Docker daemon. Production's containers (the stand-in's answer
unless a test says otherwise) were started from that checkout: without them, the scripts would
take the real ~/Dev/scanmylib of the password database for production's checkout.

Needs git, bash, curl, flock and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests
"""

from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import unittest
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

from docker_shim import LoggedCall, Rule, image_id

REPO = Path(__file__).resolve().parents[2]
SHIM = Path(__file__).resolve().parent / "docker_shim.py"
#: What the scripts need from the repository (the docker builds are only logged).
COPIED = [
    "compose.yaml",
    ".env.example",
    ".gitignore",
    "VERSION",
    "scripts/lib/common.sh",
    "scripts/lib/commit_areas.py",
    "scripts/lib/formatting.py",
    "scripts/lib/parallel_tests.py",
    "scripts/tests/test_parallel_tests.py",
    "scripts/lib/stack.py",
    "scripts/lib/version.py",
    "scripts/dev-env.sh",
    "scripts/dev.sh",
    "scripts/prod.sh",
    "scripts/deploy.sh",
    "scripts/build-apk.sh",
    "scripts/setup.sh",
    "scripts/verify-sandbox.sh",
    "scripts/e2e_test.py",
    "scripts/check.sh",
    "ocr/setup/install.sh",
    "scripts/lint/Dockerfile",
    "scripts/lint/Dockerfile.web",
    "scripts/lint/requirements.lock",
    "server/requirements-test.lock",
    "server/scanmylib/web/package.json",
    "server/scanmylib/web/package-lock.json",
    # A skill, so that .claude/skills/ exists to mount, as in the repository.
    ".claude/skills/pull-request/SKILL.md",
]
VERSION = (REPO / "VERSION").read_text().strip()
REAL_DOCKER = shutil.which("docker")
#: The home directory of the password database, which the scripts refuse whatever $HOME says.
PASSWD_HOME = pwd.getpwuid(os.getuid()).pw_dir
#: The answer of the stand-in to production_containers() (scripts/lib/common.sh).
PRODUCTION_PS = r"^ps --all --quiet --filter label=com\.docker\.compose\.project=scanmylib$"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def production_container_rules(working_dir: Path | str) -> list[Rule]:
    """Answers that make production_containers() see production's api, started from working_dir."""
    container = {
        "Name": "/scanmylib-api-1",
        "Config": {
            "Image": "scanmylib-api:latest",
            "Labels": {
                "com.docker.compose.project": "scanmylib",
                "com.docker.compose.project.working_dir": str(working_dir),
            },
        },
    }
    return [
        {"match": PRODUCTION_PS, "stdout": "prodapi\n"},
        {"match": "^inspect prodapi$", "stdout": json.dumps([container])},
    ]


@unittest.skipUnless(REAL_DOCKER, "the docker CLI (with compose) resolves the configurations")
class ScriptsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="scanmylib-scripts-")
        self.addCleanup(self.directory.cleanup)
        self.base = Path(os.path.realpath(self.directory.name))
        if self.base.is_relative_to(os.path.realpath(PASSWD_HOME)):
            self.skipTest(f"{self.base} is in your home directory, which the scripts refuse: set TMPDIR elsewhere")
        self.home = self.base / "home"
        self.bin = self.base / "bin"
        self.home.mkdir()
        self.bin.mkdir()
        self.log = self.base / "docker.log"
        self.shim_config = self.base / "shim.json"
        (self.bin / "docker").write_text(f'#!/bin/sh\nexec python3 "{SHIM}" "{self.shim_config}" "$@"\n')
        (self.bin / "docker").chmod(0o755)
        self.rules([])
        self.make_production()
        self.make_repository()

    # -- fixtures ---------------------------------------------------------------

    def make_production(self) -> None:
        self.prod = self.base / "prod"
        self.library = self.base / "library"
        (self.prod / "state" / "thumbs").mkdir(parents=True)
        # The connection's context manager commits but does not close it: closing does.
        with closing(sqlite3.connect(self.prod / "state" / "scanmylib.db")) as database, database:
            database.execute("CREATE TABLE documents (id TEXT)")
            database.execute("INSERT INTO documents VALUES ('d1')")
        (self.prod / "state" / "token").write_text("token\n")
        (self.prod / "state" / "thumbs" / "page.jpg").write_bytes(b"jpeg")
        (self.prod / "sandbox").mkdir()
        (self.prod / "sandbox" / "MANIFEST.json").write_text("{}")
        (self.prod / "android" / "keystore").mkdir(parents=True)
        (self.prod / "android" / "keystore" / "scanmylib-release.p12").write_bytes(b"key")
        (self.prod / "android" / "keystore" / "password").write_text("secret")
        self.library.mkdir()
        self.api_port = free_port()

    def production_env(self, **changes: str | None) -> str:
        values: dict[str, str | None] = {
            "SCANMYLIB_UID": str(os.getuid()),
            "SCANMYLIB_GID": str(os.getgid()),
            "DATA_DIR": str(self.prod),
            "SANDBOX_DIR": f"{self.prod}/sandbox",
            "ANDROID_DIR": f"{self.prod}/android",
            "LIBRARY_DIR": str(self.library),
            "API_PORT": str(self.api_port),
            "PUBLIC_URL": f"http://127.0.0.1:{self.api_port}",
            "COMPOSE_PROJECT_NAME": "scanmylib",
            "IMAGE_PREFIX": "scanmylib",
            "SANDBOX_SETUP_DIR": f"{self.prod}/sandbox",
            "OCR_SERVICE": "ocr",
            "APP_VARIANT": "release",
        }
        values.update(changes)
        return "".join(f"{key}={value}\n" for key, value in values.items() if value is not None)

    def make_repository(self) -> None:
        self.origin = self.base / "origin.git"
        # Production's checkout when no production container names another: ~/Dev/scanmylib.
        self.primary = self.home / "Dev" / "scanmylib"
        # Where the worktrees of production's checkout live, ignored by its .gitignore.
        self.worktree = self.primary / ".claude" / "worktrees" / "feature"
        self.primary.parent.mkdir(parents=True, exist_ok=True)
        self.git(self.base, "init", "--quiet", "--bare", "--initial-branch=main", str(self.origin))
        self.git(self.base, "init", "--quiet", "--initial-branch=main", str(self.primary))
        for name in COPIED:
            target = self.primary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, target)
        self.git(self.primary, "add", "--all")
        self.git(self.primary, "commit", "--quiet", "--message", "Initial commit")
        # The release VERSION, as .github/workflows/release.yml publishes it.
        self.git(self.primary, "tag", "--annotate", f"v{VERSION}", "--message", f"ScanMyLib {VERSION}")
        self.git(self.primary, "remote", "add", "origin", str(self.origin))
        self.git(self.primary, "push", "--quiet", "origin", "main", f"refs/tags/v{VERSION}")
        self.git(self.primary, "worktree", "add", "--quiet", "-b", "feature", str(self.worktree), "main")
        (self.primary / ".env").write_text(self.production_env())

    def git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.environment(), check=True, capture_output=True, text=True
        ).stdout

    def environment(self, **extra: str) -> dict[str, str]:
        environment = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
            "TMPDIR": str(self.base),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            # The real docker CLI resolves configurations only; it could not reach a daemon anyway.
            "DOCKER_HOST": "unix:///nonexistent/docker.sock",
        }
        environment.update(extra)
        return environment

    def rules(self, rules: list[Rule]) -> None:
        rules = rules + production_container_rules(self.home / "Dev" / "scanmylib")
        self.shim_config.write_text(json.dumps({"log": str(self.log), "real_docker": REAL_DOCKER, "rules": rules}))

    def calls(self) -> list[LoggedCall]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def commands(self) -> list[str]:
        return [" ".join(call["argv"]) for call in self.calls()]

    def run_script(
        self,
        checkout: Path,
        script: str,
        *args: str,
        timeout: float = 60,
        environment: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(checkout / "scripts" / script), *args],
            cwd=checkout,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=self.environment(**(environment or {})),
        )


class CheckTest(ScriptsTestCase):
    def list_checks(self) -> list[list[str]]:
        return [call["argv"] for call in self.calls() if call["argv"][:1] in (["build"], ["run"])]

    @staticmethod
    def list_areas_checked(gate_run: subprocess.CompletedProcess[str]) -> list[str]:
        return re.findall(r"Checking (\w+)", gate_run.stdout)

    def write_scripts_test(self, body: str, directory: str = "tests") -> None:
        # The fixture holds none of the tests of scripts/ but the runner's own: the areas run this one next to them.
        tests = self.worktree / "scripts" / directory
        tests.mkdir(parents=True, exist_ok=True)
        (tests / "test_placeholder.py").write_text(
            "import os\nimport unittest\n\n\nclass Placeholder(unittest.TestCase):\n"
            f"    def test_placeholder(self) -> None:\n        {body}\n"
        )

    def commit_in_worktree(self, path: str, text: str) -> None:
        (self.worktree / path).parent.mkdir(parents=True, exist_ok=True)
        (self.worktree / path).write_text(text)
        self.git(self.worktree, "add", path)
        self.git(self.worktree, "commit", "--quiet", "--message", f"Change {path}")

    def test_a_commit_is_checked_on_the_areas_its_files_reach(self) -> None:
        self.commit_in_worktree("server/scanmylib/notes.py", "NOTES = 1\n")
        gate_run = self.run_script(self.worktree, "check.sh", "--last-commit")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        self.assertEqual(self.list_areas_checked(gate_run), ["lint", "server"])

    def test_a_commit_of_documents_only_is_checked_on_no_area(self) -> None:
        self.commit_in_worktree("docs/guide.md", "# Guide\n")
        gate_run = self.run_script(self.worktree, "check.sh", "--last-commit")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        self.assertIn("Nothing to check: no area reads what the last commit changes", gate_run.stdout)
        self.assertEqual(self.list_checks(), [])

    def test_a_commit_whose_areas_cannot_be_told_fails_its_check(self) -> None:
        self.commit_in_worktree("server/scanmylib/notes.py", "NOTES = 1\n")
        (self.worktree / "scripts" / "lib" / "commit_areas.py").write_text("import sys\n\nsys.exit(1)\n")
        gate_run = self.run_script(self.worktree, "check.sh", "--last-commit")
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn("cannot tell the areas the last commit touches", gate_run.stderr)
        self.assertEqual(self.list_checks(), [])

    def test_the_check_of_a_commit_takes_no_area(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "--last-commit", "server")
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn("--last-commit takes no area", gate_run.stderr)

    def test_the_gate_runs_only_the_areas_given_in_their_order(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "server", "web")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        self.assertEqual(self.list_areas_checked(gate_run), ["server", "web"])
        build, _, web_tests = (" ".join(argv) for argv in self.list_checks())
        self.assertIn(f"--target test {self.worktree}/server", build)
        self.assertIn("node --test", web_tests)

    def test_the_web_server_and_sandbox_tests_run_without_network_on_a_read_only_filesystem(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "web", "server", "ocr")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        runs = [" ".join(argv) for argv in self.list_checks() if argv[0] == "run"]
        self.assertEqual(len(runs), 3)
        for run in runs:
            self.assertIn("--network none --read-only", run)

    def test_the_gate_runs_the_image_its_build_wrote(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "server")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        build, server_tests = self.list_checks()
        self.assertEqual(server_tests[-1], image_id(build))

    def test_the_web_and_sandbox_tests_run_without_privileges_on_read_only_sources(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "web", "ocr")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        web_tests, build, sandbox_tests = self.list_checks()
        self.assertTrue(build[-1].endswith(f"{self.worktree}/ocr"), build)
        for run, mount in (
            (web_tests, f"{self.worktree}/server/scanmylib/web:/web:ro"),
            (sandbox_tests, f"{self.worktree}/ocr:/app:ro"),
        ):
            with self.subTest(run=run):
                self.assert_isolated(run)
                self.assertEqual(self.list_mounts(run), [mount])

    def test_on_github_actions_the_android_area_hands_its_settings_to_the_build(self) -> None:
        runner_temp = self.home / "work" / "_temp"
        ci_data_directory = runner_temp / "data"
        gate_run = self.run_script(
            self.worktree,
            "check.sh",
            "android",
            environment={"GITHUB_ACTIONS": "true", "RUNNER_TEMP": str(runner_temp), "DATA_DIR": str(ci_data_directory)},
        )
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        [android_build] = (" ".join(argv) for argv in self.list_checks())
        self.assertIn(f"{ci_data_directory}/android/sdk:/opt/android-sdk", android_build)

    def test_the_android_area_runs_the_tests_lint_and_ktlint(self) -> None:
        gate_run = self.run_script(
            self.worktree, "check.sh", "android", environment={"CI": "true", "DATA_DIR": str(self.base / "ci")}
        )
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        [android_build] = self.list_checks()
        self.assertEqual(android_build[-3:], ["test", "lint", "ktlintCheck"])

    def list_tool_runs(self) -> list[list[str]]:
        # The app's build container, which runs ktlint, is scripts/build-apk.sh's: its own tests cover it.
        return [argv for argv in self.list_checks() if argv[0] == "run" and "ktlintFormat" not in argv]

    @staticmethod
    def list_mounts(run: list[str]) -> list[str]:
        return [run[index + 1] for index, argument in enumerate(run) if argument == "-v"]

    def assert_isolated(self, run: list[str]) -> None:
        flags = {"--rm", "--read-only", "--init"}
        options_with_any_value = {"--env", "-v", "-w"}
        allowed_values = {
            "--network": {"none"},
            "--cap-drop": {"ALL"},
            "--security-opt": {"no-new-privileges:true"},
            "--user": {f"{os.getuid()}:{os.getgid()}"},
            "--tmpfs": {"/tmp"},
        }
        options = []
        index = 1
        while run[index].startswith("-"):
            option = run[index]
            options.append(option)
            if option in flags:
                index += 1
                continue
            self.assertIn(option, options_with_any_value | allowed_values.keys(), run)
            if option in allowed_values:
                self.assertIn(run[index + 1], allowed_values[option], run)
            index += 2
        for option in ("--network", "--read-only", "--cap-drop", "--security-opt", "--user"):
            self.assertEqual(options.count(option), 1, (option, run))

    def test_the_lint_area_checks_every_language(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "lint")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        tools = [" ".join(argv) for argv in self.list_tool_runs()]
        for expected in (
            "ruff format --check .",
            "ruff check .",
            "mypy --config-file ../mypy.ini scanmylib tests",
            "mypy --config-file ../mypy.ini scanmylib_ocr tests bench",
            "mypy --config-file ../mypy.ini lib release.py e2e_test.py tests integration_tests",
            "zizmor --offline",
            "koalaman/shellcheck:",
            "-d -- ",
            "biome ci",
        ):
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in tool for tool in tools), tools)

    def test_the_lint_tools_run_without_network_or_privileges_on_read_only_sources(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "lint")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        runs = self.list_tool_runs()
        self.assertEqual(len(runs), 9)
        for run in runs:
            with self.subTest(run=run):
                self.assert_isolated(run)
                mounts = self.list_mounts(run)
                self.assertTrue(mounts and all(mount.endswith(":ro") for mount in mounts), mounts)

    def test_the_lint_area_types_the_scripts_of_the_skills_new_ones_included_and_deleted_ones_skipped(self) -> None:
        scripts = self.worktree / ".claude" / "skills" / "example" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "gone.py").write_text("print('gone')\n")
        self.git(self.worktree, "add", str(scripts / "gone.py"))
        self.git(self.worktree, "commit", "--quiet", "--message", "A script of a skill")
        (scripts / "gone.py").unlink()
        (scripts / "tool.py").write_text("print('tool')\n")
        gate_run = self.run_script(self.worktree, "check.sh", "lint")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        tools = [" ".join(argv) for argv in self.list_tool_runs()]
        [skills_mypy] = (tool for tool in tools if "mypy --config-file mypy.ini --" in tool)
        self.assertTrue(skills_mypy.endswith("mypy --config-file mypy.ini -- .claude/skills/example/scripts/tool.py"))

    def test_the_lint_area_checks_new_shell_scripts_and_skips_deleted_ones(self) -> None:
        (self.worktree / "scripts" / "new.sh").write_text("#!/usr/bin/env bash\n")
        (self.worktree / "scripts" / "setup.sh").unlink()
        gate_run = self.run_script(self.worktree, "check.sh", "lint")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        [shellcheck] = (run for run in self.list_tool_runs() if any("koalaman/shellcheck" in part for part in run))
        shell_scripts = shellcheck[shellcheck.index("--") + 1 :]
        self.assertIn("scripts/new.sh", shell_scripts)
        self.assertNotIn("scripts/setup.sh", shell_scripts)

    def test_a_tool_that_reports_findings_fails_and_stops_the_lint_area(self) -> None:
        self.rules([{"match": r" ruff check \.$", "exit": 1}])
        gate_run = self.run_script(self.worktree, "check.sh", "lint")
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertTrue(" ".join(self.list_tool_runs()[-1]).endswith("ruff check ."))

    def test_the_lint_tools_are_built_from_their_locks_alone(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "lint")
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        contexts = [call.get("context") for call in self.calls() if call["argv"][:1] == ["build"]]
        self.assertEqual(
            contexts,
            [
                ["scripts/lint/Dockerfile", "scripts/lint/requirements.lock", "server/requirements-test.lock"],
                [
                    "scripts/lint/Dockerfile.web",
                    "server/scanmylib/web/package-lock.json",
                    "server/scanmylib/web/package.json",
                ],
            ],
        )

    def run_fix(self) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            self.worktree, "check.sh", "--fix", environment={"CI": "true", "DATA_DIR": str(self.base / "ci")}
        )

    def find_last_copy(self) -> Path:
        mounts = [mount for run in self.list_tool_runs() for mount in self.list_mounts(run)]
        server_mount = next(mount for mount in reversed(mounts) if mount.endswith(":/src/server"))
        return Path(server_mount.split(":")[0]).parent.parent

    def test_fix_formats_and_fixes_every_language_and_checks_nothing(self) -> None:
        gate_run = self.run_fix()
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        tools = [" ".join(argv) for argv in self.list_checks() if argv[0] == "run"]
        for expected in ("ruff check --fix .", "ruff format .", "-w -- ", "biome check --write", "ktlintFormat"):
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in tool for tool in tools), tools)
        self.assertFalse(any("ruff format --check" in tool or "biome ci" in tool for tool in tools), tools)
        self.assertEqual(self.list_areas_checked(gate_run), [])

    def test_fix_runs_the_formatters_without_network_or_privileges_writing_to_the_copy_alone(self) -> None:
        gate_run = self.run_fix()
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        copy = self.find_last_copy()
        self.assertFalse(copy.is_relative_to(self.home), copy)
        tree = copy / "tree"
        biome, ruff_check, ruff_format, shfmt = self.list_tool_runs()
        self.assertEqual(self.list_mounts(biome), [f"{tree}/server/scanmylib/web:/web"])
        for run in (ruff_check, ruff_format, shfmt):
            self.assertEqual(
                self.list_mounts(run),
                [
                    f"{self.worktree}:/src:ro",
                    f"{tree}/server:/src/server",
                    f"{tree}/ocr:/src/ocr",
                    f"{tree}/scripts:/src/scripts",
                    f"{tree}/.claude/skills:/src/.claude/skills",
                ],
            )
        for run in (biome, ruff_check, ruff_format, shfmt):
            with self.subTest(run=run):
                self.assert_isolated(run)

    def test_fix_brings_back_what_each_formatter_changes_in_tracked_files(self) -> None:
        for tool, container_path, path, text in (
            (r" ruff format \.$", "/src/scripts/e2e_test.py", "scripts/e2e_test.py", "# formatted\n"),
            (r" -w -- ", "/src/scripts/dev.sh", "scripts/dev.sh", "# formatted\n"),
            ("biome check --write", "/web/package.json", "server/scanmylib/web/package.json", "{}\n"),
        ):
            with self.subTest(tool=tool):
                self.rules([{"match": tool, "files": {container_path: text}}])
                gate_run = self.run_fix()
                self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
                self.assertEqual((self.worktree / path).read_text(), text)

    def test_fix_never_brings_back_a_file_a_formatter_creates(self) -> None:
        self.rules([{"match": r" ruff format \.$", "files": {"/src/scripts/tests/test_planted.py": "planted\n"}}])
        gate_run = self.run_fix()
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        self.assertFalse((self.worktree / "scripts" / "tests" / "test_planted.py").exists())

    def test_fix_never_brings_back_a_file_the_formatters_do_not_format(self) -> None:
        vendored = self.worktree / "server" / "scanmylib" / "web" / "static" / "vendor" / "library.min.js"
        vendored.parent.mkdir(parents=True)
        vendored.write_text("library\n")
        self.git(self.worktree, "add", str(vendored))
        self.git(self.worktree, "commit", "--quiet", "--message", "Vendored library")
        lock = self.worktree / "server" / "scanmylib" / "web" / "package-lock.json"
        for path, container_path in ((vendored, "/web/static/vendor/library.min.js"), (lock, "/web/package-lock.json")):
            with self.subTest(container_path=container_path):
                text_before = path.read_text()
                self.rules([{"match": "biome check --write", "files": {container_path: "spliced\n"}}])
                gate_run = self.run_fix()
                self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
                self.assertEqual(path.read_text(), text_before)

    def test_fix_leaves_untracked_files_alone_and_says_so(self) -> None:
        (self.worktree / "scripts" / "local.sh").write_text("#!/usr/bin/env bash\n")
        self.rules([{"match": r" -w -- ", "files": {"/src/scripts/local.sh": "formatted\n"}}])
        gate_run = self.run_fix()
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        self.assertEqual((self.worktree / "scripts" / "local.sh").read_text(), "#!/usr/bin/env bash\n")
        self.assertIn("scripts/local.sh", gate_run.stderr)

    def test_fix_runs_ktlint_before_anything_comes_back(self) -> None:
        # Brought back first, this script would run in place of the checkout's own, which builds the app.
        planted = "#!/usr/bin/env bash\nexit 3\n"
        self.rules([{"match": r" ruff format \.$", "files": {"/src/scripts/build-apk.sh": planted}}])
        gate_run = self.run_fix()
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        self.assertTrue(any("ktlintFormat" in argv for argv in self.list_checks()))
        self.assertEqual((self.worktree / "scripts" / "build-apk.sh").read_text(), planted)

    def assert_nothing_came_back(
        self, gate_run: subprocess.CompletedProcess[str], texts_before: dict[str, str]
    ) -> None:
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn("into something other than a file", gate_run.stderr)
        self.assertEqual({path: (self.worktree / path).read_text() for path in texts_before}, texts_before)

    def test_fix_brings_back_nothing_once_a_formatter_turns_a_file_into_a_link(self) -> None:
        (self.base / "secret").write_text("secret\n")
        texts_before = {path: (self.worktree / path).read_text() for path in ("scripts/dev.sh", "scripts/prod.sh")}
        self.rules(
            [
                {"match": r" ruff format \.$", "files": {"/src/scripts/dev.sh": "formatted\n"}},
                {"match": r" -w -- ", "links": {"/src/scripts/prod.sh": str(self.base / "secret")}},
            ]
        )
        self.assert_nothing_came_back(self.run_fix(), texts_before)
        self.assertFalse((self.worktree / "scripts" / "prod.sh").is_symlink())

    def test_fix_brings_back_nothing_once_a_formatter_turns_a_directory_into_a_link(self) -> None:
        elsewhere = self.base / "elsewhere"
        shutil.copytree(self.worktree / "scripts" / "lib", elsewhere)
        texts_before = {
            path: (self.worktree / path).read_text() for path in ("scripts/dev.sh", "scripts/lib/common.sh")
        }
        self.rules(
            [
                {"match": r" ruff format \.$", "files": {"/src/scripts/dev.sh": "formatted\n"}},
                {"match": r" -w -- ", "links": {"/src/scripts/lib": str(elsewhere)}},
            ]
        )
        self.assert_nothing_came_back(self.run_fix(), texts_before)
        self.assertFalse((self.worktree / "scripts" / "lib").is_symlink())

    def test_fix_brings_back_nothing_once_a_tracked_file_changes_while_the_formatters_run(self) -> None:
        self.rules(
            [
                {
                    "match": r" ruff format \.$",
                    "files": {"/src/scripts/dev.sh": "formatted\n"},
                    "host_files": {str(self.worktree / "scripts" / "dev.sh"): "edited meanwhile\n"},
                }
            ]
        )
        gate_run = self.run_fix()
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn("scripts/dev.sh changed in the checkout", gate_run.stderr)
        self.assertEqual((self.worktree / "scripts" / "dev.sh").read_text(), "edited meanwhile\n")

    def assert_fix_refuses_a_file_marked_assume_unchanged(self, path: str) -> None:
        self.git(self.worktree, "update-index", "--assume-unchanged", path)
        gate_run = self.run_fix()
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn(path, gate_run.stderr)
        self.assertEqual([argv for argv in self.list_checks() if argv[0] == "run"], [])

    def test_fix_refuses_tracked_files_that_git_diff_would_not_show_before_any_formatter_runs(self) -> None:
        self.assert_fix_refuses_a_file_marked_assume_unchanged("scripts/dev.sh")

    def test_fix_refuses_an_android_file_git_diff_would_not_show_as_ktlint_formats_android_in_place(self) -> None:
        (self.worktree / "android").mkdir()
        (self.worktree / "android" / "Example.kt").write_text("class Example\n")
        self.git(self.worktree, "add", "android/Example.kt")
        self.git(self.worktree, "commit", "--quiet", "--message", "Example")
        self.assert_fix_refuses_a_file_marked_assume_unchanged("android/Example.kt")

    def test_fix_removes_its_copy_once_it_succeeds(self) -> None:
        gate_run = self.run_fix()
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        self.assertFalse(self.find_last_copy().exists())

    def test_fix_removes_its_copy_once_it_brings_back_nothing(self) -> None:
        self.rules([{"match": r" -w -- ", "links": {"/src/scripts/prod.sh": "/nonexistent"}}])
        gate_run = self.run_fix()
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn("into something other than a file", gate_run.stderr)
        self.assertFalse(self.find_last_copy().exists())

    def test_fix_runs_every_tool_after_those_that_leave_findings(self) -> None:
        self.rules([{"match": r"ruff check --fix|ruff format \.$| -w -- |biome check --write|ktlintFormat", "exit": 1}])
        self.run_fix()
        tools = [" ".join(argv) for argv in self.list_checks() if argv[0] == "run"]
        for expected in ("ruff check --fix .", "ruff format .", "-w -- ", "biome check --write", "ktlintFormat"):
            with self.subTest(expected=expected):
                self.assertTrue(any(expected in tool for tool in tools), tools)

    def test_fix_fails_when_any_tool_leaves_findings(self) -> None:
        for failing in (
            r" ruff check --fix \.$",
            r" ruff format \.$",
            r" -w -- ",
            "biome check --write",
            "ktlintFormat",
        ):
            with self.subTest(failing=failing):
                self.rules([{"match": failing, "exit": 1}])
                gate_run = self.run_fix()
                self.assertNotEqual(gate_run.returncode, 0)
                self.assertIn("left to fix by hand", gate_run.stderr)

    def test_fix_takes_no_area(self) -> None:
        gate_run = self.run_script(self.worktree, "check.sh", "--fix", "server")
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn("--fix takes no area", gate_run.stderr)
        self.assertEqual(self.calls(), [])

    def test_by_default_the_gate_checks_every_area_in_order(self) -> None:
        # Each placeholder leaves its mark, so that each area shows it ran its own directory.
        self.write_scripts_test('open(os.environ["SCRIPTS_MARK"], "w").close()')
        self.write_scripts_test('open(os.environ["INTEGRATION_MARK"], "w").close()', directory="integration_tests")
        marks = {"SCRIPTS_MARK": str(self.base / "scripts-ran"), "INTEGRATION_MARK": str(self.base / "integration-ran")}
        gate_run = self.run_script(
            self.worktree, "check.sh", environment={"CI": "true", "DATA_DIR": str(self.base / "ci"), **marks}
        )
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)
        self.assertEqual(
            self.list_areas_checked(gate_run), ["lint", "scripts", "web", "server", "ocr", "android", "integration"]
        )
        self.assertEqual([Path(mark).exists() for mark in marks.values()], [True, True])

    def test_the_gate_drops_the_git_variables_of_its_caller(self) -> None:
        self.write_scripts_test('self.assertNotIn("GIT_DIR", os.environ)')
        # What `git rebase --exec` exports in a worktree, at a path where no repository can be touched.
        gate_run = self.run_script(
            self.worktree, "check.sh", "scripts", environment={"GIT_DIR": "/nonexistent/caller/.git"}
        )
        self.assertEqual(gate_run.returncode, 0, gate_run.stdout + gate_run.stderr)

    def test_a_failing_build_stops_the_gate(self) -> None:
        self.rules([{"match": r"^build ", "exit": 1}])
        gate_run = self.run_script(self.worktree, "check.sh", "server", "web")
        self.assertNotEqual(gate_run.returncode, 0)
        [build] = self.list_checks()
        self.assertIn("--target test", " ".join(build))

    def test_a_build_that_writes_no_image_id_stops_the_gate(self) -> None:
        self.rules([{"match": r"^build ", "no_image_id": True}])
        gate_run = self.run_script(self.worktree, "check.sh", "server")
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn("docker build wrote no image id", gate_run.stderr)
        self.assertEqual([argv[0] for argv in self.list_checks()], ["build"])

    def test_a_failed_build_never_runs_the_image_of_an_earlier_one(self) -> None:
        self.rules([{"match": r"^build .*/ocr$", "exit": 1}])
        gate_run = self.run_script(self.worktree, "check.sh", "server", "ocr")
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertEqual([argv[0] for argv in self.list_checks()], ["build", "run", "build"])

    def test_the_gate_refuses_an_area_it_does_not_know(self) -> None:
        # The second is one argument holding two areas, which a match on the joined list of areas would accept.
        for arguments in (["web", "docs"], ["web server"]):
            with self.subTest(arguments=arguments):
                gate_run = self.run_script(self.worktree, "check.sh", *arguments)
                self.assertNotEqual(gate_run.returncode, 0)
                self.assertIn(f"unknown area '{arguments[-1]}'", gate_run.stderr)
                self.assertEqual(self.calls(), [])

    def test_the_gate_never_runs_in_production_s_checkout(self) -> None:
        # --fix would write there.
        for arguments in (["web"], ["--fix"]):
            with self.subTest(arguments=arguments):
                gate_run = self.run_script(self.primary, "check.sh", *arguments)
                self.assertNotEqual(gate_run.returncode, 0)
                self.assertIn("is production's checkout", gate_run.stderr)
                self.assertEqual(self.list_checks(), [])

    def test_the_check_of_a_commit_refuses_production_s_checkout_before_anything_else(self) -> None:
        # A commit_areas.py that would fail shows whether the refusal comes first.
        (self.primary / "scripts" / "lib" / "commit_areas.py").write_text("import sys\n\nsys.exit(1)\n")
        gate_run = self.run_script(self.primary, "check.sh", "--last-commit")
        self.assertNotEqual(gate_run.returncode, 0)
        self.assertIn("is production's checkout", gate_run.stderr)


if __name__ == "__main__":
    unittest.main()
