#!/usr/bin/env python3
"""A stand-in for the docker CLI, for the tests of the scripts (test_scripts.py).

Usage: docker_shim.py CONFIG [docker arguments...], through a `docker` wrapper that the tests put
first in PATH. CONFIG is a JSON file:

    {"log": "...", "real_docker": "/usr/bin/docker",
     "rules": [{"match": "<regex>", "stdout": "...", "stderr": "...", "exit": 0, "snapshot": "<dir>"}, ...]}

Every call is appended to the log (one JSON line: the arguments, and the environment variables
that could change what docker compose does). The first rule whose regular expression matches the
arguments joined with spaces answers the call; with "snapshot", a `docker compose` call first
copies its --project-directory there (what a build would see). Without a matching rule, `docker compose ...
config ...` runs the real docker compose, which only resolves the configuration (DOCKER_HOST
points to a socket that does not exist: no daemon is ever reached), and anything else succeeds
without output.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

#: Global options of docker compose that take a value.
_COMPOSE_OPTIONS_WITH_VALUE = {
    "-f", "--file", "-p", "--project-name", "--project-directory", "--env-file", "--profile",
    "--ansi", "--progress", "--parallel",
}
#: Variables that would change what the scripts or docker compose do, if they leaked through.
_WATCHED = (
    "IMAGE_PREFIX", "DATA_DIR", "LIBRARY_DIR", "SANDBOX_DIR", "SANDBOX_SETUP_DIR", "ANDROID_DIR",
    "ANDROID_KEYSTORE_DIR", "API_PORT", "APP_VARIANT", "OCR_SERVICE",
)


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


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as file:
        config = json.load(file)
    argv = sys.argv[2:]
    watched = {name: value for name, value in os.environ.items()
               if name.startswith(("COMPOSE_", "DOCKER_", "BUILDKIT_")) or name in _WATCHED}
    with open(config["log"], "a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": argv, "env": watched}) + "\n")
    joined = " ".join(argv)
    for rule in config.get("rules", []):
        if re.search(rule["match"], joined):
            if rule.get("snapshot") and "--project-directory" in argv:
                project = argv[argv.index("--project-directory") + 1]
                shutil.copytree(project, rule["snapshot"], symlinks=True, dirs_exist_ok=True)
            sys.stdout.write(rule.get("stdout", ""))
            sys.stderr.write(rule.get("stderr", ""))
            return int(rule.get("exit", 0))
    if compose_command(argv) == "config":
        environment = dict(os.environ, DOCKER_HOST="unix:///nonexistent/docker.sock")
        return subprocess.run([config["real_docker"], *argv], env=environment, check=False).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
