#!/usr/bin/env python3
"""A stand-in for the docker CLI, for the tests of the scripts (test_scripts.py).

Usage: docker_shim.py CONFIG [docker arguments...], through a `docker` wrapper that the tests put
first in PATH. CONFIG is a JSON file:

    {"log": "...", "real_docker": "/usr/bin/docker",
     "rules": [{"match": "<regex>", "stdout": "...", "stderr": "...", "exit": 0, "snapshot": "<dir>",
                "no_image_id": true, "files": {"<path in the container>": "<text>"},
                "links": {"<path in the container>": "<target>"}, "host_files": {"<path>": "<text>"}}, ...]}

Every call is appended to the log (one JSON line: the arguments, the environment variables that could change what docker
compose does, and the files of a build context read from stdin, which `docker build ... -` reads in full, as docker
does, and refuses without the Dockerfile its --file names). The first rule whose regular expression matches the
arguments joined with spaces answers the call; with "snapshot", a `docker compose` call first copies its
--project-directory there (what a build would see); with "files" or "links", a `docker run` call writes a file or makes
a link (in place of a file or a directory) where its -v mounts put that path of the container, as the tool would, and
fails as docker does: on a read-only mount, on a mount point, or through a link that leaves the mount; with
"host_files", it writes files of the host, as a person editing them meanwhile would. A `docker run` whose -v mount lies
in a read-only one without its mount point fails, as docker cannot create it. Without a matching rule, `docker compose
... config ...` runs the real docker compose, which only resolves the configuration (DOCKER_HOST points to a socket that
does not exist: no daemon is ever reached), and anything else succeeds without output. A `docker build --iidfile FILE
...` that succeeds writes a made-up image id there, unless its rule says "no_image_id".
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from typing import NotRequired, Required, TypedDict

#: Global options of docker compose that take a value.
_COMPOSE_OPTIONS_WITH_VALUE = {
    "-f",
    "--file",
    "-p",
    "--project-name",
    "--project-directory",
    "--env-file",
    "--profile",
    "--ansi",
    "--progress",
    "--parallel",
}
#: Variables that would change what the scripts or docker compose do, if they leaked through.
_WATCHED = (
    "IMAGE_PREFIX",
    "DATA_DIR",
    "LIBRARY_DIR",
    "SANDBOX_DIR",
    "SANDBOX_SETUP_DIR",
    "ANDROID_DIR",
    "ANDROID_KEYSTORE_DIR",
    "API_PORT",
    "APP_VARIANT",
    "OCR_SERVICE",
)


class Rule(TypedDict, total=False):
    match: Required[str]
    stdout: str
    stderr: str
    exit: int
    snapshot: str
    no_image_id: bool
    files: dict[str, str]
    links: dict[str, str]
    host_files: dict[str, str]


class LoggedCall(TypedDict):
    argv: list[str]
    env: dict[str, str]
    context: NotRequired[list[str]]


def compose_command(argv: list[str]) -> str | None:
    """The docker compose subcommand of `docker compose ...` arguments."""
    if argv[:1] != ["compose"]:
        return None
    arguments = iter(argv[1:])
    for argument in arguments:
        if argument in _COMPOSE_OPTIONS_WITH_VALUE:
            next(arguments, None)
        elif not argument.startswith("-"):
            return argument
    return None


def image_id(build_argv: list[str]) -> str:
    arguments = build_argv[build_argv.index("--iidfile") + 2 :]
    return "sha256:" + hashlib.sha256(" ".join(arguments).encode()).hexdigest()


def read_build_context(argv: list[str]) -> list[str] | None:
    if argv[:1] != ["build"] or argv[-1:] != ["-"]:
        return None
    with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read())) as context:
        return sorted(context.getnames())


def find_dockerfile(build_argv: list[str]) -> str:
    return build_argv[build_argv.index("--file") + 1] if "--file" in build_argv else "Dockerfile"


@dataclass(frozen=True)
class Mount:
    host_path: str
    container_path: str
    options: list[str]

    @property
    def is_read_only(self) -> bool:
        return "ro" in self.options


def list_mounts(run_argv: list[str]) -> list[Mount]:
    mounts = []
    for index, argument in enumerate(run_argv[:-1]):
        if argument == "-v":
            host_path, container_path, *options = run_argv[index + 1].split(":")
            mounts.append(Mount(host_path, container_path.rstrip("/"), ",".join(options).split(",")))
    return mounts


def find_mount(mounts: list[Mount], container_path: str) -> Mount | None:
    enclosing_mounts = [mount for mount in mounts if (container_path + "/").startswith(mount.container_path + "/")]
    return max(enclosing_mounts, key=lambda mount: len(mount.container_path), default=None)


def find_writable_host_path(run_argv: list[str], container_path: str, *, replaces_last_component: bool) -> str | None:
    mount = find_mount(list_mounts(run_argv), container_path)
    if mount is None or mount.is_read_only or container_path == mount.container_path:
        return None
    path = mount.host_path + container_path[len(mount.container_path) :]
    # A link replaces the last component of its path, so only its directory must lie in the mount; a file is written
    # through every component, links included.
    resolved_path = os.path.realpath(os.path.dirname(path) if replaces_last_component else path) + "/"
    return path if resolved_path.startswith(os.path.realpath(mount.host_path) + "/") else None


def find_missing_mount_point(run_argv: list[str]) -> str | None:
    mounts = list_mounts(run_argv)
    for mount in mounts:
        others = [other for other in mounts if other.container_path != mount.container_path]
        parent = find_mount(others, mount.container_path)
        if parent is not None and parent.is_read_only:
            if not os.path.isdir(parent.host_path + mount.container_path[len(parent.container_path) :]):
                return mount.container_path
    return None


def act_as_the_tool(argv: list[str], rule: Rule) -> bool:
    for container_path, text in rule.get("files", {}).items():
        path = find_writable_host_path(argv, container_path, replaces_last_component=False)
        if path is None:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            file.write(text)
    for container_path, target in rule.get("links", {}).items():
        path = find_writable_host_path(argv, container_path, replaces_last_component=True)
        if path is None:
            return False
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        os.symlink(target, path)
    return True


def edit_host_files(rule: Rule) -> None:
    for path, text in rule.get("host_files", {}).items():
        with open(path, "w", encoding="utf-8") as file:
            file.write(text)


def write_image_id(argv: list[str]) -> None:
    if argv[:1] == ["build"] and "--iidfile" in argv:
        with open(argv[argv.index("--iidfile") + 1], "w", encoding="utf-8") as file:
            file.write(image_id(argv))


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as file:
        config = json.load(file)
    argv = sys.argv[2:]
    watched = {
        name: value
        for name, value in os.environ.items()
        if name.startswith(("COMPOSE_", "DOCKER_", "BUILDKIT_")) or name in _WATCHED
    }
    call: LoggedCall = {"argv": argv, "env": watched}
    context = read_build_context(argv)
    if context is not None:
        call["context"] = context
    with open(config["log"], "a", encoding="utf-8") as log:
        log.write(json.dumps(call) + "\n")
    if context is not None and find_dockerfile(argv) not in context:
        sys.stderr.write(f"failed to read dockerfile: open {find_dockerfile(argv)}: no such file or directory\n")
        return 1
    missing_mount_point = find_missing_mount_point(argv) if argv[:1] == ["run"] else None
    if missing_mount_point is not None:
        sys.stderr.write(f"error mounting {missing_mount_point}: read-only file system\n")
        return 1
    joined = " ".join(argv)
    for rule in config.get("rules", []):
        if re.search(rule["match"], joined):
            if rule.get("snapshot") and "--project-directory" in argv:
                project = argv[argv.index("--project-directory") + 1]
                shutil.copytree(project, rule["snapshot"], symlinks=True, dirs_exist_ok=True)
            if not act_as_the_tool(argv, rule):
                sys.stderr.write("read-only file system\n")
                return 1
            edit_host_files(rule)
            sys.stdout.write(rule.get("stdout", ""))
            sys.stderr.write(rule.get("stderr", ""))
            if int(rule.get("exit", 0)) == 0 and not rule.get("no_image_id"):
                write_image_id(argv)
            return int(rule.get("exit", 0))
    write_image_id(argv)
    if compose_command(argv) == "config":
        environment = dict(os.environ, DOCKER_HOST="unix:///nonexistent/docker.sock")
        return subprocess.run([config["real_docker"], *argv], env=environment, check=False).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
