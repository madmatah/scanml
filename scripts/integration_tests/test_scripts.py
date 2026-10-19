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

import fcntl
import http.server
import itertools
import json
import os
import pwd
import queue
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
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
VERSION_CODE = sum(int(part) * factor for part, factor in zip(VERSION.split("."), (10000, 100, 1), strict=True))
#: The version of a development build of the test repositories, whose only commit is the release
#: VERSION (scripts/lib/version.py): the next patch, no commit since, then the commit.
_MAJOR, _MINOR, _PATCH = (int(part) for part in VERSION.split("."))
DEV_VERSION = re.escape(f"{_MAJOR}.{_MINOR}.{_PATCH + 1}-dev.0+g") + "[0-9a-f]{12}"
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


def port_in_use(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


@dataclass(frozen=True)
class RunningScript:
    process: subprocess.Popen[str]
    lines: queue.Queue[str | None]


class Health:
    """GET /api/health of a fake api, reporting `version` and the published APK's `apk_version`
    (None: no APK); counts the requests it gets."""

    def __init__(self, port: int) -> None:
        self.version = VERSION
        self.apk_version: str | None = VERSION
        self.requests = 0
        health = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                health.requests += 1
                apk = None if health.apk_version is None else {"version": health.apk_version, "version_code": 1}
                body = json.dumps({"name": "ScanMyLib", "version": health.version, "api": 1, "apk": apk}).encode()
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


def sandbox_rules(sandbox: str, data: str, *, kind: str = "ocr", network: str = "none") -> list[Rule]:
    """Answers that make scripts/verify-sandbox.sh see a running, isolated OCR container."""
    if kind == "ocr":
        mounts = (
            f"bind|{sandbox}|/opt/sandbox|ro\nbind|{data}/run|/run/scanmylib|rw\n"
            f"bind|{data}/ocr-cache|/var/cache/ocr|rw\n"
        )
        found: list[Rule] = [{"match": r" ps -q ocr$", "stdout": "ocrid\n"}]
    else:
        mounts = f"bind|{data}/run|/run/scanmylib|rw\n"
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

    def dev_env(self, **changes: str | None) -> str:
        dev = f"{self.prod}-dev"
        values: dict[str, str | None] = {
            "COMPOSE_PROJECT_NAME": "scanmylib-dev",
            "IMAGE_PREFIX": "scanmylib-dev",
            "DATA_DIR": dev,
            "SANDBOX_DIR": f"{self.prod}/sandbox",
            "ANDROID_DIR": f"{dev}/android",
            "ANDROID_KEYSTORE_DIR": f"{self.prod}/android/keystore",
            "LIBRARY_DIR": f"{dev}/library",
            "API_PORT": "8770",
            "PUBLIC_URL": "http://127.0.0.1:8770",
            "OCR_SERVICE": "ocr-fake",
            "APP_VARIANT": "dev",
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

    def make_clone(self) -> Path:
        """Another clone of origin on main, with a copy of production's .env: not production."""
        clone = self.base / "clone"
        self.git(self.base, "clone", "--quiet", str(self.origin), str(clone))
        (clone / ".env").write_text(self.production_env())
        return clone

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

    def start_script(self, checkout: Path, script: str) -> RunningScript:
        process = subprocess.Popen(
            [str(checkout / "scripts" / script)],
            cwd=checkout,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=self.environment(),
            start_new_session=True,
        )
        self.addCleanup(self.stop, process)
        lines: queue.Queue[str | None] = queue.Queue()

        def read_lines() -> None:
            # A thread rather than select(): a line already read into the pipe's buffer would never wake select().
            for line in process.stdout or ():
                lines.put(line)
            lines.put(None)

        threading.Thread(target=read_lines, daemon=True).start()
        return RunningScript(process, lines)

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def stop(process: subprocess.Popen[str]) -> None:
        # The whole session: the script and what it waits on, such as flock.
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=60)
        if process.stdout is not None:
            process.stdout.close()

    def assert_only_reads(self) -> None:
        """Every docker call was read-only: listing, inspecting, resolving the configuration."""
        for call in self.calls():
            argv = call["argv"]
            if argv[0] == "compose":
                command = next(a for a in argv[1:] if not a.startswith("-") and a not in self.compose_values(argv))
                self.assertIn(command, ("config", "ps"), argv)
            else:
                self.assertTrue(argv[0] in ("ps", "inspect", "info") or argv[:2] == ["image", "inspect"], argv)

    @staticmethod
    def compose_values(argv: list[str]) -> set[str]:
        values = set()
        for option, value in itertools.pairwise(argv):
            if option in ("--project-directory", "--file", "--env-file", "--profile"):
                values.add(value)
        return values


class DevStackTest(ScriptsTestCase):
    def write_dev_env(self, text: str) -> None:
        (self.worktree / ".env").write_text(text)

    def test_dev_env_writes_an_isolated_development_env(self) -> None:
        if port_in_use(8770):
            self.skipTest("port 8770 is in use (a development stack runs)")
        result = self.run_script(self.worktree, "dev-env.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        env = dict(
            line.split("=", 1)
            for line in (self.worktree / ".env").read_text().splitlines()
            if line and not line.startswith("#")
        )
        self.assertEqual(env["COMPOSE_PROJECT_NAME"], "scanmylib-dev")
        self.assertEqual(env["DATA_DIR"], f"{self.prod}-dev")
        self.assertEqual(env["ANDROID_DIR"], f"{self.prod}-dev/android")
        self.assertEqual(env["ANDROID_KEYSTORE_DIR"], f"{self.prod}/android/keystore")
        self.assertEqual(env["SANDBOX_DIR"], f"{self.prod}/sandbox")
        self.assertEqual((env["APP_VARIANT"], env["OCR_SERVICE"], env["API_PORT"]), ("dev", "ocr-fake", "8770"))
        self.assertNotIn("SANDBOX_SETUP_DIR", env)
        self.assert_only_reads()

    def test_dev_env_refuses_production_s_checkout_and_foreign_env_files(self) -> None:
        result = self.run_script(self.primary, "dev-env.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is production's checkout", result.stderr)
        for text, expected in [
            ("COMPOSE_PROJECT_NAME=scanmylib-review\n", "not scanmylib-dev"),
            ("COMPOSE_PROJECT_NAME=scanmylib-dev # mine\n", "not a valid .env"),
        ]:
            self.write_dev_env(text)
            result = self.run_script(self.worktree, "dev-env.sh")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)
            self.assertEqual((self.worktree / ".env").read_text(), text)

    def test_a_valid_development_env_passes(self) -> None:
        self.write_dev_env(self.dev_env())
        result = self.run_script(self.worktree, "dev.sh", "compose", "ps")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(" ps" in command and "config" not in command for command in self.commands()))

    def test_the_development_api_reports_a_development_version(self) -> None:
        self.write_dev_env(self.dev_env())
        result = self.run_script(self.worktree, "dev.sh", "build")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        [build] = [command for command in self.commands() if re.search(r"^compose .* build ", command)]
        self.assertRegex(build, rf" build --build-arg DEV_VERSION={DEV_VERSION} api$")

    def test_dev_sh_refuses_whatever_production_owns(self) -> None:
        prod, base = str(self.prod), str(self.base)
        cases = [
            # .env lines that docker compose reads differently from a naive parser.
            (self.dev_env() + "COMPOSE_PROJECT_NAME=scanmylib # dev\n", "line 12"),
            (self.dev_env(COMPOSE_PROJECT_NAME="scanmylib # dev"), "line 1"),
            (self.dev_env() + "export COMPOSE_PROJECT_NAME=scanmylib\n", "line 12"),
            (self.dev_env() + "  DATA_DIR=" + prod + "\n", "line 12"),
            (self.dev_env() + "DATA_DIR: " + prod + "\n", "line 12"),
            (self.dev_env() + "IMAGE_PREFIX = scanmylib\n", "line 12"),
            (self.dev_env(DATA_DIR="${PRODUCTION}") + "PRODUCTION=" + prod + "\n", "line 3"),
            (self.dev_env().replace("\n", "\r\n"), "carriage returns"),
            (self.dev_env() + "COMPOSE_FILE=/elsewhere/compose.yaml\n", "COMPOSE_FILE"),
            # What production owns, as docker compose resolves it.
            (self.dev_env(COMPOSE_PROJECT_NAME="scanmylib"), "the project is production's"),
            (self.dev_env(IMAGE_PREFIX="scanmylib"), "the image scanmylib-api:latest is production's"),
            (self.dev_env(IMAGE_PREFIX="docker.io/library/scanmylib"), "may only contain lowercase letters"),
            (self.dev_env(API_PORT=str(self.api_port)), f"publishes port {self.api_port}"),
            (self.dev_env(API_PORT="8765"), "publishes port 8765"),
            (self.dev_env(DATA_DIR=prod), "is production's DATA_DIR"),
            (self.dev_env(DATA_DIR=f"{prod}/dev"), "is inside production's DATA_DIR"),
            (self.dev_env(DATA_DIR=base, LIBRARY_DIR=f"{base}/dev-library"), "contains production's DATA_DIR"),
            (self.dev_env(LIBRARY_DIR=str(self.library)), "is production's LIBRARY_DIR"),
            (self.dev_env(SANDBOX_SETUP_DIR=f"{prod}/sandbox"), "-> /opt/sandbox"),
            (self.dev_env(ANDROID_DIR=f"{prod}/android"), "ANDROID_DIR in .env"),
            (self.dev_env(APP_VARIANT="release"), "only production builds the release app"),
            (self.dev_env(DATA_DIR=None), "no DATA_DIR in .env"),
            (self.dev_env(DATA_DIR=""), "no DATA_DIR in .env"),
            # Outside the stack's own DATA_DIR, or on what every program shares.
            (self.dev_env(LIBRARY_DIR="/tmp"), "is or contains /tmp"),
            (self.dev_env(SANDBOX_DIR="/tmp"), "SANDBOX_DIR in .env"),
            (self.dev_env(LIBRARY_DIR=f"{self.home}/.ssh"), "is inside your home directory"),
            (self.dev_env(LIBRARY_DIR=f"{base}/elsewhere"), "is not inside the stack's DATA_DIR"),
            (
                self.dev_env(DATA_DIR=f"{self.home}/dev", LIBRARY_DIR=f"{self.home}/dev/library"),
                "is inside your home directory",
            ),
            # $HOME is the temporary home: the home directory of the password database still counts.
            (
                self.dev_env(LIBRARY_DIR=f"{PASSWD_HOME}/scanmylib-tests-never-created"),
                f"is inside your home directory ({PASSWD_HOME})",
            ),
        ]
        for text, expected in cases:
            with self.subTest(expected=expected, text=text):
                self.log.unlink(missing_ok=True)
                self.write_dev_env(text)
                result = self.run_script(self.worktree, "dev.sh", "compose", "ps")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assert_only_reads()
                self.assertFalse(
                    any(" ps" in c and " config" not in c and c.startswith("compose") for c in self.commands())
                )

    def test_compose_yaml_settings_outside_the_allowlist(self) -> None:
        # A branch that changes compose.yaml: privileges, another container's volumes, the Docker
        # API, host files read into a container, another project's network. As docker compose
        # really resolves them: env_file and label_file only show without interpolation.
        self.write_dev_env(self.dev_env())
        secrets = self.home / ".config" / "secrets.env"
        secrets.parent.mkdir(parents=True)
        secrets.write_text("TOKEN=secret\n")
        (self.worktree / "base.yaml").write_text(f"services:\n  base:\n    image: x\n    env_file: {secrets}\n")
        (self.worktree / "more.yaml").write_text(
            "services:\n  more:\n    image: scanmylib-dev-api:latest\n"
            "    network_mode: none\n    environment:\n      X: ${TOKEN-none}\n"
        )
        compose = self.worktree / "compose.yaml"
        original = compose.read_text()
        api = "    read_only: true\n"
        for change, expected in [
            ((api, api + "    privileged: true\n"), "privileged is not allowed"),
            ((api, api + '    volumes_from: ["container:scanmylib-api-1"]\n'), "volumes_from is not allowed"),
            ((api, api + "    use_api_socket: true\n"), "use_api_socket is not allowed"),
            ((api, api + "    cap_add: [SYS_ADMIN]\n"), "cap_add is not allowed"),
            ((api, api + "    pid: host\n"), "pid is not allowed"),
            ((api, api + f"    env_file: [{secrets}]\n"), "service api: env_file is not allowed"),
            ((api, api + f"    label_file: {secrets}\n"), "service api: label_file is not allowed"),
            ((api, api + "    extends:\n      file: base.yaml\n      service: base\n"), "service api: env_file"),
            ((api, api + "    network_mode: scanmylib_default\n"), "network_mode scanmylib_default is not allowed"),
            (
                ("services:\n", f"include:\n  - path: more.yaml\n    env_file: {secrets}\nservices:\n"),
                "include is not allowed",
            ),
            (
                ("services:\n", "networks:\n  default:\n    name: scanmylib_default\n    external: true\nservices:\n"),
                "network default (scanmylib_default) is not the stack's own",
            ),
        ]:
            with self.subTest(change=change[1]):
                self.log.unlink(missing_ok=True)
                compose.write_text(original.replace(*change, 1))
                result = self.run_script(self.worktree, "dev.sh", "compose", "ps")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assert_only_reads()

    def test_running_production_containers_are_production(self) -> None:
        moved = self.base / "moved-library"
        container = {
            "Name": "/scanmylib-api-1",
            "Config": {
                "Image": "scanmylib-api:latest",
                "Labels": {"com.docker.compose.project.working_dir": str(self.primary)},
            },
            "Mounts": [{"Type": "bind", "Source": str(moved), "Destination": "/library"}],
        }
        self.rules(
            [{"match": PRODUCTION_PS, "stdout": "abc\n"}, {"match": "^inspect abc$", "stdout": json.dumps([container])}]
        )
        self.write_dev_env(self.dev_env(LIBRARY_DIR=str(moved)))
        result = self.run_script(self.worktree, "dev.sh", "status")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mount /library of scanmylib-api-1", result.stderr)

    def test_the_callers_environment_never_reaches_docker_compose(self) -> None:
        self.write_dev_env(self.dev_env())
        leaked = {
            "COMPOSE_PROJECT_NAME": "scanmylib",
            "COMPOSE_FILE": "/elsewhere.yaml",
            "COMPOSE_PROFILES": "setup",
            "DATA_DIR": str(self.prod),
            "IMAGE_PREFIX": "scanmylib",
            "API_PORT": "8765",
        }
        result = self.run_script(self.worktree, "dev.sh", "compose", "ps", environment=leaked)
        self.assertEqual(result.returncode, 0, result.stderr)
        compose_calls = [call for call in self.calls() if call["argv"][0] == "compose"]
        self.assertTrue(compose_calls)
        for call in compose_calls:
            self.assertEqual(set(call["env"]) - {"DOCKER_HOST"}, set(), call)
            self.assertIn(f"--env-file {self.worktree}/.env", " ".join(call["argv"]))

    def test_compose_global_options_and_commands_outside_the_stack_are_refused(self) -> None:
        self.write_dev_env(self.dev_env())
        for args, expected in [
            (["-p", "scanmylib", "down"], "no global option"),
            (["--project-name=scanmylib", "down"], "no global option"),
            (["--file", "x.yaml", "ps"], "no global option"),
            (["run", "--rm", "-v", "/:/host", "api", "sh"], "run -v"),
            (["run", "-p", "8765:8765", "api"], "run -p"),
            (["run", "--cap-add", "SYS_ADMIN", "api"], "run --cap-add"),
            (["exec", "--privileged", "api", "sh"], "exec --privileged"),
            (["cp", "api:/state/token", str(self.home)], "compose cp is not allowed"),
            (["commit", "api", "scanmylib-api:latest"], "compose commit is not allowed"),
            (["build", "api", "--ssh", f"default={self.home}/.ssh/id_ed25519"], "build --ssh"),
            (["build", "api", "--push"], "build --push"),
            (["config", "-o", str(self.primary / ".env")], "config -o"),
            (["up", "-d"], "name them"),
            (["up", "-d", "api", "ocr", "ocr-fake"], "never start both"),
        ]:
            with self.subTest(args=args):
                self.log.unlink(missing_ok=True)
                result = self.run_script(self.worktree, "dev.sh", "compose", *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assert_only_reads()


class DeployTest(ScriptsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.health = Health(self.api_port)
        self.addCleanup(self.health.close)
        # Containers that run the images in place, never tagged :deployed yet (the first deploy
        # with this script).
        self.previous: list[Rule] = []
        for service in ("api", "ocr"):
            self.previous += [
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

    def deploy(
        self, *args: str, rules: list[Rule] | None = None, checkout: Path | None = None, **environment: str
    ) -> subprocess.CompletedProcess[str]:
        self.rules((rules or []) + self.previous + sandbox_rules(f"{self.prod}/sandbox", str(self.prod)))
        return self.run_script(checkout or self.primary, "deploy.sh", *args, timeout=120, environment=environment)

    def backups(self) -> list[str]:
        directory = self.prod / "backups"
        return sorted(entry.name for entry in directory.iterdir()) if directory.exists() else []

    def assert_tags_unchanged(self) -> None:
        """The tags of production's checkout and of origin are the release's: deploy.sh never tags."""
        self.assertEqual(self.git(self.primary, "tag"), f"v{VERSION}\n")
        self.assertEqual(
            [line.split("\t")[1] for line in self.git(self.primary, "ls-remote", "--tags", "origin").splitlines()],
            [f"refs/tags/v{VERSION}", f"refs/tags/v{VERSION}^{{}}"],
        )

    def test_dry_run_changes_nothing(self) -> None:
        result = self.deploy("--dry-run", "--apk")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Dry run: nothing was changed.", result.stdout)
        self.assertIn(f"production's checkout ({self.primary})", result.stdout)
        self.assertIn(f"the release v{VERSION}, as published on origin", result.stdout)
        self.assertIn("holds the database", result.stdout)
        self.assertIn("would run: docker tag sha256:oldapi scanmylib-api:deployed", result.stdout)
        self.assert_only_reads()
        self.assertEqual(self.health.requests, 0, "a dry run sends no request to the api")
        self.assertEqual(self.backups(), [])
        self.assertFalse((self.prod / "logs").exists())
        self.assert_tags_unchanged()

    def test_deploy(self) -> None:
        snapshot = self.base / "built"
        result = self.deploy("--apk", rules=[{"match": r"^compose .* build api ocr$", "snapshot": str(snapshot)}])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        build = next(command for command in commands if command.startswith("compose") and " build api ocr" in command)
        export = build.split("--project-directory ", 1)[1].split()[0]
        self.assertTrue(export.startswith(f"{self.base}/scanmylib-deploy."), build)
        self.assertFalse(Path(export).exists(), "the export is removed")
        self.assertEqual(
            sorted(str(path.relative_to(snapshot)) for path in snapshot.rglob("*") if path.is_file()),
            sorted(COPIED),
            "the export is the commit, without .env",
        )
        self.assertIn(f"--env-file {self.primary}/.env", build)
        self.assertNotIn("DEV_VERSION", build, "production's api reports VERSION")
        tests = commands.index(next(c for c in commands if "scanmylib-deploy-pytest" in c))
        self.assertLess(commands.index(build), tests, "the tests run on the new images")
        up = next(command for command in commands if " up -d --no-build --wait" in command)
        # Production's containers record this checkout; the compose.yaml is the commit's.
        self.assertIn(f"--project-directory {self.primary} --file {export}/compose.yaml ", up)
        self.assertTrue(
            all(f"--file {export}/compose.yaml " in command for command in commands if command.startswith("compose"))
        )
        self.assertIn("$ scripts/prod.sh compose up -d --no-build", result.stdout)
        self.assertNotIn("$ docker compose", result.stdout)
        sign = next(c for c in commands if "scanmylib-android-sign" in c)
        self.assertIn(f"{self.prod}/android/keystore:/keystore:ro", sign)
        self.assertIn("EXPECTED_PACKAGE=fr.scanmylib ", sign)
        # The backup: the database and the token, not the thumbnail cache.
        [backup] = self.backups()
        self.assertRegex(backup, rf"^state-\d{{8}}-\d{{6}}\.\d+-v{VERSION}$")
        copy = self.prod / "backups" / backup
        self.assertEqual(sorted(path.name for path in copy.iterdir()), ["scanmylib.db", "token"])
        with closing(sqlite3.connect(copy / "scanmylib.db")) as database:
            self.assertEqual(database.execute("SELECT id FROM documents").fetchall(), [("d1",)])
        self.assert_tags_unchanged()
        # :deployed names the images the containers ran before the build, then the new ones as
        # soon as they pass the isolation check, before the APK.
        self.assertLess(commands.index("tag sha256:oldapi scanmylib-api:deployed"), commands.index(build))
        self.assertLess(commands.index("tag sha256:oldocr scanmylib-ocr:deployed"), commands.index(build))
        retag = commands.index("tag scanmylib-api:latest scanmylib-api:deployed")
        self.assertEqual(commands.count("tag scanmylib-api:latest scanmylib-api:deployed"), 1)
        self.assertGreater(retag, max(i for i, command in enumerate(commands) if command.startswith("exec ")))
        self.assertLess(retag, min(i for i, command in enumerate(commands) if "scanmylib-android-build" in command))
        self.assertIn("tag scanmylib-ocr:latest scanmylib-ocr:deployed", commands[commands.index(up) :])
        [log] = (self.prod / "logs").iterdir()
        self.assertIn(f"Deployed scanmylib {VERSION}", log.read_text())

    def test_first_deploy_tags_the_images_the_containers_run(self) -> None:
        # :latest was rebuilt since the containers started: :deployed names what they run.
        rules: list[Rule] = [
            {"match": r"^image inspect --format \{\{\.Id\}\} scanmylib-api:latest$", "stdout": "sha256:newer\n"}
        ]
        result = self.deploy("--dry-run", rules=rules)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("scanmylib-api:latest (sha256:newer) is not the image api runs", result.stdout)
        self.assertIn("would run: docker tag sha256:oldapi scanmylib-api:deployed", result.stdout)

    def test_failed_tests_leave_production_unchanged(self) -> None:
        result = self.deploy(rules=[{"match": "scanmylib-deploy-pytest", "exit": 1}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "tests"', result.stdout)
        self.assertIn("Production is unchanged", result.stdout)
        commands = self.commands()
        self.assertIn("tag scanmylib-api:deployed scanmylib-api:latest", commands)
        self.assertIn("tag scanmylib-ocr:deployed scanmylib-ocr:latest", commands)
        self.assertFalse(any(" up " in command for command in commands))
        self.assertEqual(self.backups(), [])

    def test_failed_restart_explains_the_rollback(self) -> None:
        self.health.version = "0.0.1"
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "restart"', result.stdout)
        [backup] = self.backups()
        self.assertIn("docker tag scanmylib-api:deployed scanmylib-api:latest", result.stdout)
        rollback = result.stdout.split("DEPLOY FAILED", 1)[1]
        self.assertIn("scripts/prod.sh compose up -d --no-build api ocr", rollback)
        self.assertNotIn("docker compose", rollback)
        self.assertIn(f"cp -a {self.prod}/backups/{backup} {self.prod}/state", result.stdout)
        self.assertIn(f"mv {self.prod}/state {self.prod}/state.failed-", result.stdout)
        self.assertNotIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands())
        self.assert_tags_unchanged()

    def test_deployed_images_are_kept_for_rollbacks(self) -> None:
        # :deployed already names the images production runs: a new deploy keeps it until the
        # new images run and pass the isolation check, even after a failed attempt.
        deployed: list[Rule] = [
            {"match": r"^image inspect --format \{\{\.Id\}\} scanmylib-(api|ocr):deployed$", "stdout": "sha256:good\n"},
            {"match": r"^inspect --format \{\{\.Image\}\} (api|ocr)id$", "stdout": "sha256:good\n"},
        ]
        self.health.version = "0.0.1"
        result = self.deploy(rules=deployed)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands())
        self.assertFalse(any(command.startswith("tag sha256:") for command in self.commands()))
        self.assertIn("docker tag scanmylib-api:deployed scanmylib-api:latest", result.stdout)
        self.log.unlink()
        self.health.version = VERSION
        result = self.deploy(rules=deployed)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        self.assertEqual(commands.count("tag scanmylib-api:latest scanmylib-api:deployed"), 1)
        self.assertGreater(
            commands.index("tag scanmylib-api:latest scanmylib-api:deployed"),
            commands.index(next(c for c in commands if " up -d --no-build" in c)),
        )

    def test_deployed_follows_what_runs(self) -> None:
        # A deploy failed once the containers ran the new images (:deployed still names the
        # previous ones): the next deploy tags what runs, the truth to roll back to.
        lagging: list[Rule] = [
            {
                "match": r"^image inspect --format \{\{\.Id\}\} scanmylib-(api|ocr):deployed$",
                "stdout": "sha256:older\n",
            },
            {"match": "scanmylib-deploy-pytest", "exit": 1},
        ]
        result = self.deploy(rules=lagging)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "warn  scanmylib-api:deployed (sha256:older) is not the image api runs (sha256:oldapi)", result.stdout
        )
        commands = self.commands()
        tagged = commands.index("tag sha256:oldapi scanmylib-api:deployed")
        self.assertLess(tagged, commands.index(next(c for c in commands if " build api ocr" in c)))
        self.assertGreater(commands.index("tag scanmylib-api:deployed scanmylib-api:latest"), tagged)

    def test_failed_apk_leaves_deployed_on_what_runs(self) -> None:
        result = self.deploy("--apk", rules=[{"match": "^run .*scanmylib-android-build", "exit": 1}])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "apk"', result.stdout)
        self.assertIn("its images tagged :deployed", result.stdout)
        self.assertIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands())
        self.assert_tags_unchanged()

    def test_deploy_checks_that_the_api_offers_the_new_apk(self) -> None:
        for apk_version in (None, "0.0.1"):
            with self.subTest(apk_version=apk_version):
                if self.log.exists():
                    self.log.unlink()
                self.health.apk_version = apk_version
                result = self.deploy("--apk")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('DEPLOY FAILED during the step "apk"', result.stdout)
                self.assertIn(f"the api offers the APK '{apk_version}', not {VERSION}", result.stdout + result.stderr)
                self.assert_tags_unchanged()

    def test_failed_isolation_check_stops_the_ocr_service(self) -> None:
        result = self.deploy(rules=sandbox_rules(f"{self.prod}/sandbox", str(self.prod), network="bridge"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DEPLOY FAILED during the step "isolation"', result.stdout)
        self.assertTrue(
            any(command.startswith("compose") and command.endswith(" stop ocr") for command in self.commands())
        )
        self.assertNotIn("tag scanmylib-api:latest scanmylib-api:deployed", self.commands())
        self.assert_tags_unchanged()

    def test_old_backups_are_pruned(self) -> None:
        backups = self.prod / "backups"
        for day in range(1, 13):
            (backups / f"state-202001{day:02d}-000000-v0.0.1").mkdir(parents=True)
        (backups / "state-20200113-000000-v0.0.1.partial").mkdir()
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        remaining = self.backups()
        self.assertEqual(len(remaining), 10)
        self.assertEqual(remaining[0], "state-20200104-000000-v0.0.1")
        self.assertTrue(remaining[-1].endswith(f"-v{VERSION}"))

    def hide_a_change(self) -> None:
        """A change git status does not show: skip-worktree on a modified tracked file."""
        self.git(self.primary, "update-index", "--skip-worktree", "compose.yaml")
        with (self.primary / "compose.yaml").open("a") as compose:
            compose.write("# hidden change\n")

    def test_preconditions(self) -> None:
        refusals: list[tuple[str, Callable[[], object], str]] = [
            ("no database", lambda: (self.prod / "state" / "scanmylib.db").unlink(), "no database in"),
            (
                "a comment in .env",
                lambda: (self.primary / ".env").write_text(self.production_env(DATA_DIR=f"{self.prod} # data")),
                "line",
            ),
            (
                "a library that is not a directory",
                lambda: (self.primary / ".env").write_text(self.production_env(LIBRARY_DIR=f"{self.base}/missing")),
                "is not a directory",
            ),
            ("an untracked file", lambda: (self.primary / "notes.txt").write_text("x"), "untracked changes"),
            ("a hidden change", self.hide_a_change, "assume-unchanged or skip-worktree"),
            (
                "a commit after the release",
                lambda: self.git(self.primary, "commit", "--quiet", "--allow-empty", "-m", "x"),
                f"is not the release v{VERSION}",
            ),
            (
                "a release not published",
                lambda: self.git(self.primary, "push", "--quiet", "origin", f":refs/tags/v{VERSION}"),
                f"v{VERSION} is not published on origin",
            ),
            (
                "a development .env",
                lambda: (self.primary / ".env").write_text(self.production_env(COMPOSE_PROJECT_NAME="scanmylib-dev")),
                "not production's",
            ),
            ("an empty .env", lambda: (self.primary / ".env").write_text("# nothing\n"), "not production's"),
        ]
        for name, prepare, expected in refusals:
            with self.subTest(name):
                self.make_repository_fresh()
                prepare()
                result = self.deploy()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout + result.stderr)
                self.assertIn("Refusing to deploy", result.stderr)
                self.assert_only_reads()

    def test_never_an_older_release_than_production_runs(self) -> None:
        self.health.version = "99.0.0"
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"production runs 99.0.0, newer than this release {VERSION}", result.stdout)
        self.assertIn("Refusing to deploy", result.stderr)
        self.assert_only_reads()
        # A dry run sends no request to the api: it says what a real run checks.
        self.health.requests = 0
        result = self.deploy("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("a real run checks that production does not run a release newer", result.stdout)
        self.assertEqual(self.health.requests, 0)
        # A version that cannot be read, or is not a release, is not compared, and says so.
        for version, expected in (
            ("unknown", "reports 'unknown', not a release"),
            (None, "cannot read the version of the running api"),
        ):
            with self.subTest(version=version):
                self.log.unlink(missing_ok=True)
                if version is None:
                    self.health.close()
                else:
                    self.health.version = version
                result = self.deploy("--skip-tests")
                self.assertIn(expected, result.stdout)
                self.assertNotIn("newer than this release", result.stdout)
        self.health = Health(self.api_port)
        self.addCleanup(self.health.close)
        self.health.version = "99.0.0"
        # Unless the downgrade is wanted (the fake api then never reports VERSION).
        self.log.unlink()
        result = self.deploy("--allow-downgrade", "--skip-tests")
        self.assertIn("production runs 99.0.0, newer than", result.stdout)
        self.assertIn("a downgrade (--allow-downgrade)", result.stdout)
        self.assertNotIn("Refusing to deploy", result.stderr)

    def test_deploy_from_the_release_s_tag(self) -> None:
        # Production's checkout holds a release: its tag, checked out.
        self.git(self.primary, "checkout", "--quiet", f"v{VERSION}")
        result = self.deploy("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"the release v{VERSION}, as published on origin", result.stdout)

    def make_repository_fresh(self) -> None:
        for path in (self.origin, self.primary):
            shutil.rmtree(path)
        self.make_production_db()
        self.make_repository()
        self.log.unlink(missing_ok=True)

    def make_production_db(self) -> None:
        database = self.prod / "state" / "scanmylib.db"
        if not database.exists():
            sqlite3.connect(database).close()

    def test_first_install_without_database(self) -> None:
        (self.prod / "state" / "scanmylib.db").unlink()
        result = self.deploy("--first-install", "--skip-tests")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_one_deploy_at_a_time(self) -> None:
        lock = os.open(self.primary, os.O_RDONLY)
        self.addCleanup(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another deploy is running", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_never_from_a_worktree(self) -> None:
        result = self.deploy(checkout=self.worktree)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"not production's checkout: production runs from {self.primary}", result.stdout)

    def test_never_from_another_clone_with_production_s_env(self) -> None:
        clone = self.make_clone()
        result = self.deploy(checkout=clone)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"not production's checkout: production runs from {self.primary}", result.stdout)
        self.assertIn("Refusing to deploy", result.stderr)
        self.assert_only_reads()

    def test_production_s_checkout_is_where_its_containers_run_from(self) -> None:
        # Production's containers were started from the clone: ~/Dev/scanmylib is not production.
        clone = self.make_clone()
        self.rules(production_container_rules(clone))
        result = self.run_script(self.primary, "deploy.sh", "--dry-run", timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"not production's checkout: production runs from {clone}", result.stdout)

    def test_rehearsal_on_a_throwaway_stack(self) -> None:
        data = self.base / "rehearsal"
        port = free_port()
        rehearsal = Health(port)
        self.addCleanup(rehearsal.close)
        (self.worktree / ".env").write_text(
            self.dev_env(
                COMPOSE_PROJECT_NAME="scanmylib-review-test",
                IMAGE_PREFIX="scanmylib-review-test",
                DATA_DIR=str(data),
                LIBRARY_DIR=f"{data}/library",
                ANDROID_DIR=f"{data}/android",
                API_PORT=str(port),
            )
        )
        # Uncommitted and untracked changes are reported, and never built: the export is HEAD.
        (self.worktree / "compose.yaml").write_text((self.worktree / "compose.yaml").read_text() + "# uncommitted\n")
        (self.worktree / "untracked.txt").write_text("x")
        snapshot = self.base / "built"
        self.rules(
            [
                {"match": r"^compose .* build api ocr$", "snapshot": str(snapshot)},
                *sandbox_rules(f"{self.prod}/sandbox", str(data), kind="ocr-fake"),
            ]
        )
        # The rehearsal publishes the dev app, a development build: the api must offer the version
        # build-apk.sh published (the stand-in builds nothing: its metadata is written here).
        (data / "app").mkdir(parents=True)
        (data / "app" / "scanmylib.json").write_text(json.dumps({"version_name": "0.2.4-dev+g1a2b3c4d5e6f.dirty"}))
        rehearsal.apk_version = VERSION
        result = self.run_script(
            self.worktree,
            "deploy.sh",
            "--first-install",
            "--apk",
            timeout=120,
            environment={"SCANMYLIB_DEPLOY_REHEARSAL": "scanmylib-review-test"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            f"the api offers the APK '{VERSION}', not 0.2.4-dev+g1a2b3c4d5e6f.dirty ", result.stdout + result.stderr
        )
        rehearsal.apk_version = "0.2.4-dev+g1a2b3c4d5e6f.dirty"
        self.log.unlink()
        result = self.run_script(
            self.worktree,
            "deploy.sh",
            "--first-install",
            "--apk",
            timeout=120,
            environment={"SCANMYLIB_DEPLOY_REHEARSAL": "scanmylib-review-test"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"the api offers the APK {rehearsal.apk_version} to the phones", result.stdout)
        self.assertIn("skip  the release on origin (rehearsal", result.stdout)
        self.assertIn("uncommitted or untracked changes", result.stdout)
        self.assertNotIn("# uncommitted", (snapshot / "compose.yaml").read_text())
        self.assertFalse((snapshot / "untracked.txt").exists())
        self.assert_tags_unchanged()
        self.assertFalse(
            any(
                "scanmylib-api" in command and "scanmylib-review" not in command
                for command in self.commands()
                if not command.startswith(("ps", "inspect"))
            )
        )
        self.assertIn("tag scanmylib-review-test-api:latest scanmylib-review-test-api:deployed", self.commands())
        self.assertIn("$ scripts/dev.sh compose up -d --no-build", result.stdout)
        # The same .env pointing at production is refused before anything happens.
        (self.worktree / ".env").write_text(
            self.dev_env(
                COMPOSE_PROJECT_NAME="scanmylib-review-test",
                IMAGE_PREFIX="scanmylib-review-test",
                DATA_DIR=str(self.prod),
                API_PORT=str(port),
            )
        )
        self.log.unlink()
        result = self.run_script(
            self.worktree, "deploy.sh", timeout=120, environment={"SCANMYLIB_DEPLOY_REHEARSAL": "scanmylib-review-test"}
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not isolated from production", result.stdout)
        self.assert_only_reads()

    def test_rehearsal_checks_the_commit_it_builds(self) -> None:
        # A committed mistake (production's image name) that the working tree no longer shows:
        # the commit is what would be built, so the commit is what is checked.
        data = self.base / "rehearsal"
        (self.worktree / ".env").write_text(
            self.dev_env(
                COMPOSE_PROJECT_NAME="scanmylib-review-test",
                IMAGE_PREFIX="scanmylib-review-test",
                DATA_DIR=str(data),
                LIBRARY_DIR=f"{data}/library",
                ANDROID_DIR=f"{data}/android",
                API_PORT=str(free_port()),
            )
        )
        compose = self.worktree / "compose.yaml"
        original = compose.read_text()
        compose.write_text(
            original.replace(
                "image: ${IMAGE_PREFIX:-${COMPOSE_PROJECT_NAME}}-api:latest", "image: scanmylib-api:latest", 1
            )
        )
        self.git(self.worktree, "commit", "--quiet", "--all", "--message", "Wrong image")
        compose.write_text(original)
        for args in (["--dry-run"], []):
            with self.subTest(args=args):
                self.log.unlink(missing_ok=True)
                result = self.run_script(
                    self.worktree,
                    "deploy.sh",
                    "--first-install",
                    *args,
                    timeout=120,
                    environment={"SCANMYLIB_DEPLOY_REHEARSAL": "scanmylib-review-test"},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not isolated from production", result.stdout)
                self.assertIn("the image scanmylib-api:latest is production's", result.stdout)
                self.assert_only_reads()
        self.assertFalse(list(self.base.glob("scanmylib-deploy.*")), "the export is removed")

    def commit_rehearsal(self, compose_text: str) -> None:
        """A rehearsal .env, and compose_text committed as compose.yaml with any new file."""
        data = self.base / "rehearsal"
        (self.worktree / ".env").write_text(
            self.dev_env(
                COMPOSE_PROJECT_NAME="scanmylib-review-test",
                IMAGE_PREFIX="scanmylib-review-test",
                DATA_DIR=str(data),
                LIBRARY_DIR=f"{data}/library",
                ANDROID_DIR=f"{data}/android",
                API_PORT=str(free_port()),
            )
        )
        compose = self.worktree / "compose.yaml"
        self.assertNotEqual(compose.read_text(), compose_text, "the test changes compose.yaml")
        compose.write_text(compose_text)
        self.git(self.worktree, "add", "--all")
        self.git(self.worktree, "commit", "--quiet", "--message", "Relative paths in compose.yaml")

    def rehearse(self) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            self.worktree,
            "deploy.sh",
            "--first-install",
            timeout=120,
            environment={"SCANMYLIB_DEPLOY_REHEARSAL": "scanmylib-review-test"},
        )

    def test_rehearsal_checks_the_extends_files_of_this_checkout(self) -> None:
        # up reads relative extends files from this checkout, not from the export: an uncommitted
        # change there is what would start.
        compose = (self.worktree / "compose.yaml").read_text()
        extra = self.worktree / "fake-extra.yaml"
        extra.write_text("services:\n  extra:\n    environment:\n      EXTRA: '1'\n")
        self.commit_rehearsal(
            compose.replace("  ocr-fake:\n", "  ocr-fake:\n    extends: {file: fake-extra.yaml, service: extra}\n", 1)
        )
        extra.write_text("services:\n  extra:\n    privileged: true\n")
        result = self.rehearse()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not isolated from production", result.stdout)
        self.assertIn("privileged", result.stdout)
        self.assert_only_reads()

    def test_rehearsal_checks_the_bind_sources_of_this_checkout(self) -> None:
        # A relative bind source missing from the export is never mounted by the build's resolution,
        # but up resolves it in this checkout, where it exists.
        compose = (self.worktree / "compose.yaml").read_text()
        # The last volume of ocr-fake comes right before its environment.
        anchor = "    environment:\n      SCANMYLIB_PROJECT:"
        self.commit_rehearsal(
            compose.replace(
                anchor,
                "      - {type: bind, source: ./.git, target: /repo, bind: {create_host_path: false}}\n" + anchor,
                1,
            )
        )
        result = self.rehearse()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not isolated from production", result.stdout)
        self.assertIn(".git", result.stdout)
        self.assert_only_reads()


class BuildApkTest(ScriptsTestCase):
    def runs(self) -> list[str]:
        return [command for command in self.commands() if command.startswith("run ")]

    def test_a_worktree_builds_the_dev_app_with_its_own_toolchain(self) -> None:
        (self.worktree / ".env").write_text(self.dev_env())
        dev = f"{self.prod}-dev"
        # The environment cannot turn this into a release build in production's directories.
        result = self.run_script(
            self.worktree,
            "build-apk.sh",
            environment={"APP_VARIANT": "release", "DATA_DIR": str(self.prod), "ANDROID_DIR": f"{self.prod}/android"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        build, sign = self.runs()
        self.assertIn(f"{dev}/android/sdk:/opt/android-sdk", build)
        self.assertIn(f"{dev}/android/gradle:/gradle", build)
        self.assertIn("assembleDev", build)
        self.assertNotIn(str(self.prod) + "/", build.replace(f"{dev}/", ""))
        self.assertIn("--network none", sign)
        self.assertIn(f"{self.prod}/android/keystore:/keystore:ro", sign)
        self.assertIn(f"{dev}/android/sdk/build-tools/36.0.0:/build-tools:ro", sign)
        self.assertIn(f"{dev}/app:/out", sign)
        self.assertIn("APP_VARIANT=dev", sign)
        # A development build: its version comes from git, its versionCode from the time of the build.
        name = re.search(rf"--env SCANMYLIB_DEV_VERSION_NAME=({DEV_VERSION}) ", build)
        code = re.search(r"--env SCANMYLIB_DEV_VERSION_CODE=([0-9]+) ", build)
        assert name is not None, build
        assert code is not None, build
        self.assertGreater(int(code[1]), 400_000)
        self.assertIn(f"Version {name[1]} (versionCode {code[1]})", result.stdout)
        # The signer refuses any other app than fr.scanmylib.dev with that versionCode.
        self.assertIn("EXPECTED_PACKAGE=fr.scanmylib.dev ", sign)
        self.assertIn(f"EXPECTED_VERSION_CODE={code[1]} ", sign)
        # The definitions, not only their calls in sign_main ("declare -f" prints "name () ").
        self.assertIn("apk_identity () ", sign)
        # Its version is published next to it, for /api/health.
        self.assertIn(f"EXPECTED_VERSION_NAME={name[1]} ", sign)
        self.assertIn("write_apk_metadata () ", sign)
        # A later build installs over the published one, even within the same minute; uncommitted
        # changes say so.
        (self.worktree / "VERSION").write_text(VERSION + "\n\n")
        Path(f"{dev}/app/scanmylib.json").write_text(json.dumps({"version_code": int(code[1]) + 5}))
        self.log.unlink()
        result = self.run_script(self.worktree, "build-apk.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        build, sign = self.runs()
        self.assertRegex(build, rf"--env SCANMYLIB_DEV_VERSION_NAME={DEV_VERSION}\.dirty ")
        self.assertIn(f"EXPECTED_VERSION_CODE={int(code[1]) + 6} ", sign)

    def write_apk_metadata(self, file: Path, *values: str) -> subprocess.CompletedProcess[str]:
        """Runs write_apk_metadata of build-apk.sh, as the signing container does, in its locale."""
        script = (REPO / "scripts" / "build-apk.sh").read_text()
        function = script[script.index("write_apk_metadata() {") :]
        function = function[: function.index("\n}\n") + 3]
        return subprocess.run(
            [
                "bash",
                "-c",
                'die() { echo "error: $*" >&2; exit 1; }\n' + function + '\nwrite_apk_metadata "$@"',
                "bash",
                str(file),
                *values,
            ],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "LC_ALL": "en_US.UTF-8"},
        )

    def test_the_published_apk_metadata_is_checked_json(self) -> None:
        out = self.base / "app"
        out.mkdir()
        sha256 = "0123456789abcdef" * 4
        metadata = out / ".scanmylib.json.partial"
        longest = "0.2.4-dev+g" + "a" * 53  # 64 characters
        for name in ("0.2.4-dev.27+g1a2b3c4d5e6f", "0.2.4-dev+g1a2b3c4d5e6f.dirty", "0.2.4-dev", longest):
            with self.subTest(name=name):
                result = self.write_apk_metadata(metadata, "fr.scanmylib.dev", name, "416057", sha256, "4567")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(metadata.read_text())["version_name"], name)
        result = self.write_apk_metadata(metadata, "fr.scanmylib.dev", "1.2.3", "10203", sha256, "4567")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(metadata.read_text()),
            {
                "application_id": "fr.scanmylib.dev",
                "version_name": "1.2.3",
                "version_code": 10203,
                "sha256": sha256,
                "size": 4567,
            },
        )
        self.assertEqual(sorted(path.name for path in out.iterdir()), [".scanmylib.json.partial"])
        # Anything that could break the JSON, or that the app could not trust, is refused.
        for values in [
            ('fr.scanmylib", "x": "', "1.2.3", "10203", sha256, "4567"),
            ("fr.scanmylib", '1.2.3"', "10203", sha256, "4567"),
            ("fr.scanmylib", '1.2.3-dev", "x": "', "10203", sha256, "4567"),
            ("fr.scanmylib", longest + "a", "10203", sha256, "4567"),
            ("fr.scanmylib", "1.2.3-dév", "10203", sha256, "4567"),
            ("fr.scanmylib", "١.2.3", "10203", sha256, "4567"),
            ("fr.scanmylib", "1.2.3", '10203, "x": 1', sha256, "4567"),
            ("fr.scanmylib", "1.2.3", "10203", "not-a-digest", "4567"),
            ("fr.scanmylib", "1.2.3", "10203", sha256, ""),
        ]:
            with self.subTest(values=values):
                result = self.write_apk_metadata(metadata, *values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unexpected APK metadata", result.stderr)
                self.assertEqual(json.loads(metadata.read_text())["version_code"], 10203)

    def test_a_worktree_never_builds_the_release_app(self) -> None:
        (self.worktree / ".env").write_text(self.dev_env(APP_VARIANT="release"))
        result = self.run_script(self.worktree, "build-apk.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("production's checkout", result.stderr)
        self.assertEqual(self.runs(), [])
        # Nor with production's .env copied into it, nor in another clone.
        (self.worktree / ".env").write_text(self.production_env())
        result = self.run_script(self.worktree, "build-apk.sh")
        self.assertNotEqual(result.returncode, 0)
        clone = self.make_clone()
        result = self.run_script(clone, "build-apk.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"only built in production's checkout ({self.primary})", result.stderr)
        self.assertEqual(self.runs(), [])

    def test_the_release_app_comes_from_production_s_checkout_on_a_published_release(self) -> None:
        result = self.run_script(self.primary, "build-apk.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        build, sign = self.runs()
        self.assertIn("assembleRelease", build)
        self.assertIn(f"{self.prod}/android/keystore:/keystore:ro", sign)
        self.assertIn("EXPECTED_PACKAGE=fr.scanmylib ", sign)
        # The release is VERSION, which the build reads itself.
        self.assertIn(f"EXPECTED_VERSION_CODE={VERSION_CODE} ", sign)
        self.assertIn(f"EXPECTED_VERSION_NAME={VERSION} ", sign)
        self.assertNotIn("SCANMYLIB_DEV_VERSION", build)
        self.log.unlink()

        def add_a_stray_file() -> None:
            (self.primary / "android" / "app" / "src").mkdir(parents=True)
            (self.primary / "android" / "app" / "src" / "stray.jks").write_bytes(b"key")

        refusals: list[tuple[str, Callable[[], object], str]] = [
            ("a stray file", add_a_stray_file, "could end up in the release app"),
            ("an untracked file", lambda: (self.primary / "notes.txt").write_text("x"), "clean checkout"),
            (
                "a hidden change",
                lambda: (
                    self.git(self.primary, "update-index", "--assume-unchanged", "VERSION"),
                    (self.primary / "VERSION").write_text("9.9.9\n"),
                ),
                "assume-unchanged or skip-worktree",
            ),
            (
                "a commit after the release",
                lambda: self.git(self.primary, "commit", "--quiet", "--allow-empty", "-m", "x"),
                "built from a published release only: HEAD",
            ),
            (
                "a release not published",
                lambda: self.git(self.primary, "push", "--quiet", "origin", f":refs/tags/v{VERSION}"),
                f"v{VERSION} is not published on origin",
            ),
        ]
        for name, prepare, expected in refusals:
            with self.subTest(name):
                for path in (self.origin, self.primary):
                    shutil.rmtree(path)
                self.make_repository()
                prepare()
                result = self.run_script(self.primary, "build-apk.sh")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertEqual(self.runs(), [])

    def test_the_signing_key_is_only_created_on_request(self) -> None:
        for name in ("scanmylib-release.p12", "password"):
            (self.prod / "android" / "keystore" / name).unlink()
        result = self.run_script(self.primary, "build-apk.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no signing key", result.stderr)
        self.assertEqual(self.runs(), [])
        result = self.run_script(self.primary, "build-apk.sh", "--create-signing-key")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        _, key, sign = self.runs()
        self.assertIn(f"{self.prod}/android/keystore:/keystore ", key + " ")
        self.assertIn("--network none", key)
        self.assertIn(f"{self.prod}/android/keystore:/keystore:ro", sign)
        (self.worktree / ".env").write_text(self.dev_env())
        result = self.run_script(self.worktree, "build-apk.sh", "--create-signing-key")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only production creates the signing key", result.stderr)

    def test_without_env_only_ci_builds_and_never_signs(self) -> None:
        data = self.base / "ci"
        result = self.run_script(self.worktree, "build-apk.sh", "test", "lint", environment={"DATA_DIR": str(data)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only CI builds", result.stderr)
        result = self.run_script(self.worktree, "build-apk.sh", environment={"DATA_DIR": str(data), "CI": "true"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("never published", result.stdout)
        [build] = self.runs()
        self.assertIn(f"{data}/android/sdk:/opt/android-sdk", build)
        # Never production's toolchain or data, mounted read-write into a networked build.
        for environment, expected in [
            ({"DATA_DIR": str(self.prod)}, "is production's DATA_DIR"),
            ({"DATA_DIR": str(data), "ANDROID_DIR": f"{self.prod}/android"}, "is production's ANDROID_DIR"),
            ({"DATA_DIR": str(self.base)}, "contains production's DATA_DIR"),
        ]:
            with self.subTest(environment=environment):
                self.log.unlink()
                result = self.run_script(
                    self.worktree, "build-apk.sh", "test", "lint", environment={"GITHUB_ACTIONS": "true", **environment}
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertEqual(self.runs(), [])

    def test_ci_builds_stay_out_of_the_home_directory(self) -> None:
        # CI=true on a workstation: the home directory is refused, and nothing is created there.
        android = self.home / "android-ci"
        result = self.run_script(
            self.worktree,
            "build-apk.sh",
            "test",
            "lint",
            environment={"CI": "true", "DATA_DIR": str(self.base / "ci"), "ANDROID_DIR": str(android)},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"ANDROID_DIR: {android} is inside your home directory", result.stderr)
        self.assertFalse(android.exists())
        self.assertEqual(self.runs(), [])
        # GitHub Actions keeps RUNNER_TEMP in the runner's home directory: allowed there only.
        runner_temp = self.home / "work" / "_temp"
        result = self.run_script(
            self.worktree,
            "build-apk.sh",
            "test",
            "lint",
            environment={
                "GITHUB_ACTIONS": "true",
                "RUNNER_TEMP": str(runner_temp),
                "DATA_DIR": str(runner_temp / "data"),
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"{runner_temp}/data/android/sdk:/opt/android-sdk", self.runs()[0])
        self.log.unlink()
        result = self.run_script(
            self.worktree,
            "build-apk.sh",
            "test",
            "lint",
            environment={
                "GITHUB_ACTIONS": "true",
                "RUNNER_TEMP": str(runner_temp),
                "DATA_DIR": str(runner_temp / "data"),
                "ANDROID_DIR": str(android),
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is inside your home directory", result.stderr)
        self.assertEqual(self.runs(), [])

    def test_one_build_at_a_time_per_toolchain(self) -> None:
        (self.worktree / ".env").write_text(self.dev_env())
        android = Path(f"{self.prod}-dev/android")
        android.mkdir(parents=True)
        lock = os.open(android, os.O_RDONLY)
        self.addCleanup(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build = self.start_script(self.worktree, "build-apk.sh")
        output_while_locked = self.read_output_until(build, "Waiting for another build")
        waits_on_the_lock = self.is_waiting_on(build, "flock")
        runs_while_locked = self.runs()
        fcntl.flock(lock, fcntl.LOCK_UN)
        output_once_released = self.read_output_until(build, "Version ")
        self.assertIn("Waiting for another build", output_while_locked)
        self.assertTrue(waits_on_the_lock)
        self.assertEqual(runs_while_locked, [])
        self.assertIn("Version ", output_once_released)


class ProdShTest(ScriptsTestCase):
    def test_docker_compose_on_production_with_its_env_only(self) -> None:
        leaked = {
            "COMPOSE_PROJECT_NAME": "scanmylib-dev",
            "COMPOSE_FILE": "/elsewhere.yaml",
            "DATA_DIR": "/elsewhere",
            "COMPOSE_PROFILES": "fake-ocr",
        }
        result = self.run_script(self.primary, "prod.sh", "compose", "ps", environment=leaked)
        self.assertEqual(result.returncode, 0, result.stderr)
        [call] = [call for call in self.calls() if call["argv"][0] == "compose"]
        self.assertEqual(set(call["env"]) - {"DOCKER_HOST"}, set(), call)
        joined = " ".join(call["argv"])
        self.assertIn(f"--project-directory {self.primary} ", joined)
        self.assertIn(f"--env-file {self.primary}/.env ps", joined)
        self.assertNotIn("--profile", joined)

    def test_only_in_production_s_checkout(self) -> None:
        (self.worktree / ".env").write_text(self.dev_env())
        for checkout in (self.worktree, self.make_clone()):
            with self.subTest(checkout=checkout):
                result = self.run_script(checkout, "prod.sh", "compose", "ps")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("is not production's checkout", result.stderr)
        (self.primary / ".env").write_text(self.production_env(COMPOSE_PROJECT_NAME="scanmylib-dev"))
        result = self.run_script(self.primary, "prod.sh", "compose", "ps")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not production's", result.stderr)
        self.assert_only_reads()

    def test_up_never_builds(self) -> None:
        result = self.run_script(self.primary, "prod.sh", "compose", "up", "-d", "api", "ocr")
        self.assertEqual(result.returncode, 0, result.stderr)
        [call] = [call for call in self.calls() if call["argv"][0] == "compose"]
        self.assertEqual(call["argv"][-5:], ["up", "--no-build", "-d", "api", "ocr"])

    def test_up_only_on_a_clean_release(self) -> None:
        refusals: list[tuple[str, Callable[[], object], str]] = [
            ("an untracked file", lambda: (self.primary / "notes.txt").write_text("x"), "uncommitted or untracked"),
            ("a change", lambda: (self.primary / "compose.yaml").write_text("services: {}\n"), "uncommitted"),
            (
                "a hidden change",
                lambda: (
                    self.git(self.primary, "update-index", "--skip-worktree", "compose.yaml"),
                    (self.primary / "compose.yaml").write_text("services: {}\n"),
                ),
                "assume-unchanged or skip-worktree",
            ),
            (
                "a commit after the release",
                lambda: self.git(self.primary, "commit", "--quiet", "--allow-empty", "-m", "x"),
                f"is not the release v{VERSION}",
            ),
            ("no tag", lambda: self.git(self.primary, "tag", "--delete", f"v{VERSION}"), f"no tag v{VERSION}"),
        ]
        for name, prepare, expected in refusals:
            with self.subTest(name):
                for path in (self.origin, self.primary):
                    shutil.rmtree(path)
                self.make_repository()
                self.log.unlink(missing_ok=True)
                prepare()
                result = self.run_script(self.primary, "prod.sh", "compose", "up", "-d", "api")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertFalse(any(call["argv"][0] == "compose" for call in self.calls()))
                # Reading production's state, or restarting its containers as they were created
                # (an emergency restart), needs none of that.
                for command in ("ps", "restart", "start"):
                    result = self.run_script(self.primary, "prod.sh", "compose", command, "api")
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_changes_through_deploy_sh(self) -> None:
        for args in (
            ["build", "api"],
            ["up", "-d", "--build", "api"],
            ["up", "-d", "api", "--build"],
            ["run", "api", "sh"],
            ["cp", "api:/state", "."],
            ["up", "-d", "ocr-fake"],
            ["config", "-o", str(self.primary / ".env")],
        ):
            with self.subTest(args=args):
                result = self.run_script(self.primary, "prod.sh", "compose", *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("refused", result.stderr)
        self.assertEqual(self.calls(), [])


class E2eTest(ScriptsTestCase):
    def test_refuses_production_s_port_however_it_is_written(self) -> None:
        health = Health(self.api_port)
        self.addCleanup(health.close)
        (self.worktree / ".env").write_text(self.dev_env())
        image = self.base / "page.jpg"
        image.write_bytes(b"jpeg")
        for api, expected in [
            (f"http://127.0.0.1:{self.api_port}?x", "is production's port"),
            (f"http://127.0.0.1:{self.api_port}#x", "is production's port"),
            (f"http://localhost:0{self.api_port}/", "is production's port"),
            ("http://127.0.0.1:8765", "is production's port"),
            ("http://127.0.0.1", "no explicit port"),
            ("http://127.0.0.1:99999", "cannot tell the port"),
            ("ftp://127.0.0.1:8770", "expected http://HOST:PORT"),
        ]:
            with self.subTest(api=api):
                result = subprocess.run(
                    ["python3", str(self.worktree / "scripts" / "e2e_test.py"), str(image), "--api", api],
                    cwd=self.worktree,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=self.environment(),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("refusing to write a test document into production", result.stderr)
                self.assertIn(expected, result.stderr)
        self.assertEqual(health.requests, 0)


class SetupAndVerifyTest(ScriptsTestCase):
    def test_setup_only_installs_a_new_production(self) -> None:
        result = self.run_script(self.worktree, "setup.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not production's checkout", result.stderr)
        result = self.run_script(self.primary, "setup.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("production already exists", result.stderr)
        self.rules(production_container_rules(self.primary))
        (self.prod / "state" / "scanmylib.db").unlink()
        result = self.run_script(self.primary, "setup.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("deploy new versions with scripts/deploy.sh", result.stderr)
        self.assert_only_reads()
        # A first installation is a published release too.
        self.git(self.primary, "commit", "--quiet", "--allow-empty", "--message", "x")
        result = self.run_script(self.primary, "setup.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("install a published release: HEAD", result.stderr)

    def test_verify_sandbox_passes_on_an_isolated_sandbox(self) -> None:
        self.rules(sandbox_rules(f"{self.prod}/sandbox", str(self.prod)))
        result = self.run_script(
            self.primary, "verify-sandbox.sh", environment={"DATA_DIR": "/elsewhere", "SANDBOX_DIR": "/elsewhere"}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RESULT: all checks passed", result.stdout)

    def test_production_never_falls_back_to_the_fake_ocr(self) -> None:
        self.rules(sandbox_rules(f"{self.prod}/sandbox", str(self.prod), kind="ocr-fake"))
        result = self.run_script(self.primary, "verify-sandbox.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("production's OCR sandbox (ocr) is not running", result.stdout)
        result = self.run_script(self.primary, "verify-sandbox.sh", "fakeid")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is the fake OCR", result.stdout)
        # A development stack may run it.
        (self.worktree / ".env").write_text(self.dev_env())
        self.rules(sandbox_rules(f"{self.prod}/sandbox", f"{self.prod}-dev", kind="ocr-fake"))
        result = self.run_script(self.worktree, "verify-sandbox.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


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
