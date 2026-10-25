"""Test support of the integration tests of the scripts: a throwaway installation of ScanMyLib, whose docker calls the
docker stand-in (docker_shim.py) answers, and a fake api that reports its health.

An installation lies in a temporary directory: a bare "origin", production's checkout (at ~/Dev/scanmylib of a
temporary home directory, with a production .env whose paths are all temporary) on the release VERSION, published on
origin (the tag vVERSION), and a worktree, with the scripts of this checkout. `docker` is the stand-in: docker compose
only resolves configurations (offline), any other call is logged and answered by the test's rules; nothing reaches the
Docker daemon. Production's containers (the stand-in's answer unless a test says otherwise) were started from that
checkout: without them, the scripts would take the real ~/Dev/scanmylib of the password database for production's
checkout.

Needs git, bash, curl, flock and the docker CLI with its compose plugin.
"""

from __future__ import annotations

import http.server
import json
import os
import pwd
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from docker_shim import LoggedCall, Rule, compose_command

REPO = Path(__file__).resolve().parents[2]
SHIM = Path(__file__).resolve().parent / "docker_shim.py"
#: What the scripts need from the repository (the docker builds are only logged).
COPIED = (
    "compose.yaml",
    ".env.example",
    ".gitignore",
    "VERSION",
    "scripts/lib/common.sh",
    "scripts/lib/engine_check.sh",
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
)
VERSION = (REPO / "VERSION").read_text().strip()
VERSION_CODE = sum(int(part) * factor for part, factor in zip(VERSION.split("."), (10000, 100, 1), strict=True))
_MAJOR, _MINOR, _PATCH = (int(part) for part in VERSION.split("."))
#: The version of a development build of the throwaway repositories, whose only commit is the release VERSION
#: (scripts/lib/version.py): the next patch, no commit since, then the commit.
DEV_VERSION = re.escape(f"{_MAJOR}.{_MINOR}.{_PATCH + 1}-dev.0+g") + "[0-9a-f]{12}"
REAL_DOCKER = shutil.which("docker")
#: The home directory of the password database, which the scripts refuse whatever $HOME says.
PASSWD_HOME = pwd.getpwuid(os.getuid()).pw_dir
#: The call of production_containers() (scripts/lib/common.sh) that the stand-in answers.
PRODUCTION_PS = r"^ps --all --quiet --filter label=com\.docker\.compose\.project=scanmylib$"
TEMPORARY_DIRECTORY = Path(os.path.realpath(tempfile.gettempdir()))
_READING_COMPOSE_COMMANDS = ("config", "ps")
_READING_COMMANDS = ("ps", "inspect", "info")


def find_free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@dataclass(frozen=True)
class ScriptRun:
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


@unittest.skipUnless(REAL_DOCKER, "the docker CLI (with compose) resolves the configurations")
@unittest.skipIf(
    TEMPORARY_DIRECTORY.is_relative_to(os.path.realpath(PASSWD_HOME)),
    f"{TEMPORARY_DIRECTORY} is in your home directory, which the scripts refuse: set TMPDIR elsewhere",
)
class InstallationTestCase(unittest.TestCase):
    pass


class FakeApi:
    """GET /api/health of production's api, reporting `version` and the published APK's `apk_version` (None: no APK),
    which counts the requests it gets."""

    def __init__(self, port: int) -> None:
        self.version = VERSION
        self.apk_version: str | None = VERSION
        self.request_count = 0
        fake_api = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                fake_api.request_count += 1
                apk = None if fake_api.apk_version is None else {"version": fake_api.apk_version, "version_code": 1}
                body = json.dumps({"name": "ScanMyLib", "version": fake_api.version, "api": 1, "apk": apk}).encode()
                self.send_response(200 if self.path == "/api/health" else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def start_fake_api(test_case: type[unittest.TestCase], port: int) -> FakeApi:
    fake_api = FakeApi(port)
    test_case.addClassCleanup(fake_api.close)
    return fake_api


class Installation:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.home = directory / "home"
        self.tools = directory / "bin"
        self.docker_log = directory / "docker.log"
        self.shim_config = directory / "shim.json"
        self.production_data = directory / "prod"
        self.development_data = Path(f"{self.production_data}-dev")
        self.library = directory / "library"
        self.origin = directory / "origin.git"
        # Production's checkout when no production container names another: ~/Dev/scanmylib.
        self.production_checkout = self.home / "Dev" / "scanmylib"
        # Where the worktrees of production's checkout live, ignored by its .gitignore.
        self.worktree = self.production_checkout / ".claude" / "worktrees" / "feature"
        self.production_api_port = find_free_port()
        self.home.mkdir()
        self.tools.mkdir()
        shim = f"{shlex.quote(str(SHIM))} {shlex.quote(str(self.shim_config))}"
        (self.tools / "docker").write_text(f'#!/bin/sh\nexec python3 {shim} "$@"\n')
        (self.tools / "docker").chmod(0o755)
        self.answer_docker([])
        self._make_production_data()
        self._make_repositories()

    def _make_production_data(self) -> None:
        state = self.production_data / "state"
        (state / "thumbs").mkdir(parents=True)
        # The connection's context manager commits but does not close it: closing does.
        with closing(sqlite3.connect(state / "scanmylib.db")) as database, database:
            database.execute("CREATE TABLE documents (id TEXT)")
            database.execute("INSERT INTO documents VALUES ('d1')")
        (state / "token").write_text("token\n")
        (state / "thumbs" / "page.jpg").write_bytes(b"jpeg")
        (self.production_data / "sandbox").mkdir()
        (self.production_data / "sandbox" / "MANIFEST.json").write_text("{}")
        keystore = self.production_data / "android" / "keystore"
        keystore.mkdir(parents=True)
        (keystore / "scanmylib-release.p12").write_bytes(b"key")
        (keystore / "password").write_text("secret")
        self.library.mkdir()

    def _make_repositories(self) -> None:
        self.production_checkout.parent.mkdir(parents=True)
        self.run_git(self.directory, "init", "--quiet", "--bare", "--initial-branch=main", str(self.origin))
        self.run_git(self.directory, "init", "--quiet", "--initial-branch=main", str(self.production_checkout))
        for name in COPIED:
            target = self.production_checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, target)
        self.run_git(self.production_checkout, "add", "--all")
        self.run_git(self.production_checkout, "commit", "--quiet", "--message", "Initial commit")
        # The release VERSION, as .github/workflows/release.yml publishes it.
        self.run_git(self.production_checkout, "tag", "--annotate", f"v{VERSION}", "--message", f"ScanMyLib {VERSION}")
        self.run_git(self.production_checkout, "remote", "add", "origin", str(self.origin))
        self.run_git(self.production_checkout, "push", "--quiet", "origin", "main", f"refs/tags/v{VERSION}")
        self.run_git(
            self.production_checkout, "worktree", "add", "--quiet", "-b", "feature", str(self.worktree), "main"
        )
        (self.production_checkout / ".env").write_text(self.build_production_env())

    def build_production_env(self, **changes: str | None) -> str:
        variables: dict[str, str | None] = {
            "SCANMYLIB_UID": str(os.getuid()),
            "SCANMYLIB_GID": str(os.getgid()),
            "DATA_DIR": str(self.production_data),
            "SANDBOX_DIR": f"{self.production_data}/sandbox",
            "ANDROID_DIR": f"{self.production_data}/android",
            "LIBRARY_DIR": str(self.library),
            "API_PORT": str(self.production_api_port),
            "PUBLIC_URL": f"http://127.0.0.1:{self.production_api_port}",
            "COMPOSE_PROJECT_NAME": "scanmylib",
            "IMAGE_PREFIX": "scanmylib",
            "SANDBOX_SETUP_DIR": f"{self.production_data}/sandbox",
            "OCR_SERVICE": "ocr",
            "APP_VARIANT": "release",
        }
        variables.update(changes)
        return "".join(f"{name}={value}\n" for name, value in variables.items() if value is not None)

    def build_development_env(self, **changes: str | None) -> str:
        variables: dict[str, str | None] = {
            "COMPOSE_PROJECT_NAME": "scanmylib-dev",
            "IMAGE_PREFIX": "scanmylib-dev",
            "DATA_DIR": str(self.development_data),
            "SANDBOX_DIR": f"{self.production_data}/sandbox",
            "ANDROID_DIR": f"{self.development_data}/android",
            "ANDROID_KEYSTORE_DIR": f"{self.production_data}/android/keystore",
            "LIBRARY_DIR": f"{self.development_data}/library",
            "API_PORT": "8770",
            "PUBLIC_URL": "http://127.0.0.1:8770",
            "OCR_SERVICE": "ocr-fake",
            "APP_VARIANT": "dev",
        }
        variables.update(changes)
        return "".join(f"{name}={value}\n" for name, value in variables.items() if value is not None)

    def make_clone(self) -> Path:
        """Another clone of origin on main, with a copy of production's .env: not production."""
        clone = self.directory / "clone"
        self.run_git(self.directory, "clone", "--quiet", str(self.origin), str(clone))
        (clone / ".env").write_text(self.build_production_env())
        return clone

    def add_an_untracked_file(self) -> None:
        (self.production_checkout / "notes.txt").write_text("x")

    def commit_after_the_release(self) -> None:
        self.run_git(self.production_checkout, "commit", "--quiet", "--allow-empty", "-m", "x")

    def hide_a_change_with_skip_worktree(self) -> None:
        self.run_git(self.production_checkout, "update-index", "--skip-worktree", "compose.yaml")
        with (self.production_checkout / "compose.yaml").open("a") as compose:
            compose.write("# hidden change\n")

    def unpublish_the_release(self) -> None:
        self.run_git(self.production_checkout, "push", "--quiet", "origin", f":refs/tags/v{VERSION}")

    def run_git(self, checkout: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=checkout,
            env=self.build_environment(),
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def build_environment(self, **extra: str) -> dict[str, str]:
        """The whole environment of the scripts: nothing of the caller's but its PATH, after the stand-in."""
        environment = {
            "PATH": f"{self.tools}:{os.environ['PATH']}",
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
            "TMPDIR": str(self.directory),
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

    def answer_docker(self, rules: list[Rule]) -> None:
        rules = rules + build_production_container_rules(self.production_checkout)
        self.shim_config.write_text(
            json.dumps({"log": str(self.docker_log), "real_docker": REAL_DOCKER, "rules": rules})
        )

    def read_docker_calls(self) -> list[LoggedCall]:
        if not self.docker_log.exists():
            return []
        return [json.loads(line) for line in self.docker_log.read_text().splitlines()]

    def read_compose_calls(self) -> list[LoggedCall]:
        return [call for call in self.read_docker_calls() if call["argv"][0] == "compose"]

    def read_docker_commands(self) -> list[str]:
        return [" ".join(call["argv"]) for call in self.read_docker_calls()]

    def forget_docker_calls(self) -> None:
        self.docker_log.unlink(missing_ok=True)

    def run_script(
        self,
        checkout: Path,
        script: str,
        *arguments: str,
        timeout_seconds: float = 60,
        environment: Mapping[str, str] | None = None,
    ) -> ScriptRun:
        completed = subprocess.run(
            [str(checkout / "scripts" / script), *arguments],
            cwd=checkout,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=self.build_environment(**(environment or {})),
            check=False,
        )
        return ScriptRun(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class UncleanCheckout:
    make_unclean: Callable[[Installation], None]
    refusal: str


def make_installation(test_case: type[InstallationTestCase]) -> Installation:
    directory = tempfile.TemporaryDirectory(prefix="scanmylib-scripts-")
    test_case.addClassCleanup(directory.cleanup)
    return Installation(Path(os.path.realpath(directory.name)))


def build_running_sandbox_rules(
    sandbox: str, stack_data: str, *, kind: str = "ocr", network: str = "none"
) -> list[Rule]:
    if kind == "ocr":
        mounts = (
            f"bind|{sandbox}|/opt/sandbox|ro\nbind|{stack_data}/run|/run/scanmylib|rw\n"
            f"bind|{stack_data}/ocr-cache|/var/cache/ocr|rw\n"
        )
        found: list[Rule] = [{"match": r" ps -q ocr$", "stdout": "ocrid\n"}]
    else:
        mounts = f"bind|{stack_data}/run|/run/scanmylib|rw\n"
        found = [{"match": r" ps -q ocr$", "stdout": ""}, {"match": r" ps -q ocr-fake$", "stdout": "fakeid\n"}]
    return [
        *found,
        {"match": r"\{\{\.State\.Running\}\}", "stdout": "true\n"},
        {"match": r"com\.docker\.compose\.service", "stdout": f"{kind}\n"},
        {"match": r"\{\{\.Name\}\}", "stdout": f"/stack-{kind}-1\n"},
        {"match": r"\{\{\.HostConfig\.NetworkMode\}\}", "stdout": f"{network}\n"},
        {"match": r"\{\{\.HostConfig\.ReadonlyRootfs\}\}", "stdout": "true\n"},
        {"match": r"\{\{\.HostConfig\.Privileged\}\}", "stdout": "false\n"},
        {"match": r"\{\{json \.HostConfig\.CapDrop\}\}", "stdout": '["ALL"]\n'},
        {"match": r"\{\{json \.HostConfig\.CapAdd\}\}", "stdout": "null\n"},
        {"match": r"\{\{json \.HostConfig\.SecurityOpt\}\}", "stdout": '["no-new-privileges:true"]\n'},
        {"match": r"MaskedPaths", "stdout": '11 ["/proc/bus","/proc/sys"]\n'},
        {"match": r"\{\{\.HostConfig\.PidMode\}\}", "stdout": "\n"},
        {"match": r"\{\{\.HostConfig\.IpcMode\}\}", "stdout": "private\n"},
        {"match": r"\{\{\.HostConfig\.UTSMode\}\}", "stdout": "\n"},
        {"match": r"\{\{\.HostConfig\.CgroupnsMode\}\}", "stdout": "private\n"},
        {"match": r"\{\{json \.HostConfig\.Devices\}\}", "stdout": "null\n"},
        {"match": r"DeviceCgroupRules", "stdout": "null\n"},
        {"match": r"DeviceRequests", "stdout": "cdi:nvidia.com/gpu=all \n"},
        {"match": r"\{\{range \.Mounts\}\}", "stdout": mounts},
        {"match": r"PidsLimit", "stdout": "4096\n"},
        {"match": r"\{\{\.HostConfig\.Memory\}\}", "stdout": "536870912\n"},
        {"match": r"LogConfig\.Type", "stdout": "json-file\n"},
        {"match": r'"max-size"', "stdout": "10m\n"},
        {"match": r"^exec ", "stdout": "PASS: the checks inside the container (stand-in)\n"},
    ]


def build_production_container_rules(working_directory: Path) -> list[Rule]:
    """Answers that make production_containers() see production's api, started from `working_directory`."""
    container = {
        "Name": "/scanmylib-api-1",
        "Config": {
            "Image": "scanmylib-api:latest",
            "Labels": {
                "com.docker.compose.project": "scanmylib",
                "com.docker.compose.project.working_dir": str(working_directory),
            },
        },
    }
    return [
        {"match": PRODUCTION_PS, "stdout": "prodapi\n"},
        {"match": "^inspect prodapi$", "stdout": json.dumps([container])},
    ]


def read_text_if_present(path: Path) -> str | None:
    return path.read_text() if path.exists() else None


def read_gradle_tasks(calls: list[LoggedCall]) -> list[str]:
    for call in calls:
        argv = call["argv"]
        if argv[0] == "run" and "build_main" in argv:
            return argv[argv.index("build_main") + 1 :]
    return []


def list_writing_calls(calls: list[LoggedCall]) -> list[list[str]]:
    return [call["argv"] for call in calls if not _is_reading(call["argv"])]


def _is_reading(argv: list[str]) -> bool:
    if argv[0] == "compose":
        return compose_command(argv) in _READING_COMPOSE_COMMANDS
    return argv[0] in _READING_COMMANDS or argv[:2] == ["image", "inspect"]
