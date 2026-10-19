"""The development stack of a worktree (scripts/dev.sh), in throwaway installations (installation_support.py), whose
docker compose only resolves the configuration it checks.

Needs git, bash and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_dev.py'
"""

from __future__ import annotations

import json
import re
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from docker_shim import LoggedCall
from installation_support import (
    DEV_VERSION,
    PASSWD_HOME,
    PRODUCTION_PS,
    Installation,
    InstallationTestCase,
    ScriptRun,
    list_writing_calls,
    make_installation,
)


@dataclass(frozen=True)
class RefusedEnv:
    text: str
    refusal: str


@dataclass(frozen=True)
class ComposeChange:
    anchor: str
    replacement: str


def is_compose_ps(command: str) -> bool:
    return command.startswith("compose") and " ps" in command and " config" not in command


def build_refused_envs(installation: Installation) -> dict[str, RefusedEnv]:
    build_env = installation.build_development_env
    env = build_env()
    production_data = str(installation.production_data)
    production_api_port = str(installation.production_api_port)
    directory = str(installation.directory)
    home = installation.home
    return {
        # Lines that docker compose reads otherwise than a naive parser.
        "a comment after a value": RefusedEnv(env + "COMPOSE_PROJECT_NAME=scanmylib # dev\n", "line 12"),
        "a comment in a value": RefusedEnv(build_env(COMPOSE_PROJECT_NAME="scanmylib # dev"), "line 1"),
        "an export": RefusedEnv(env + "export COMPOSE_PROJECT_NAME=scanmylib\n", "line 12"),
        "an indented line": RefusedEnv(env + f"  DATA_DIR={production_data}\n", "line 12"),
        "a colon for an equals sign": RefusedEnv(env + f"DATA_DIR: {production_data}\n", "line 12"),
        "spaces around the equals sign": RefusedEnv(env + "IMAGE_PREFIX = scanmylib\n", "line 12"),
        "an interpolation": RefusedEnv(
            build_env(DATA_DIR="${PRODUCTION}") + f"PRODUCTION={production_data}\n", "line 3"
        ),
        "carriage returns": RefusedEnv(env.replace("\n", "\r\n"), "carriage returns"),
        "another compose file": RefusedEnv(env + "COMPOSE_FILE=/elsewhere/compose.yaml\n", "COMPOSE_FILE"),
        # What production owns, as docker compose resolves it.
        "production's project": RefusedEnv(build_env(COMPOSE_PROJECT_NAME="scanmylib"), "the project is production's"),
        "production's images": RefusedEnv(
            build_env(IMAGE_PREFIX="scanmylib"), "the image scanmylib-api:latest is production's"
        ),
        "production's images in a registry": RefusedEnv(
            build_env(IMAGE_PREFIX="docker.io/library/scanmylib"),
            "may only contain lowercase letters",
        ),
        "production's port": RefusedEnv(
            build_env(API_PORT=production_api_port), f"publishes port {production_api_port}"
        ),
        "production's default port": RefusedEnv(build_env(API_PORT="8765"), "publishes port 8765"),
        "production's DATA_DIR": RefusedEnv(build_env(DATA_DIR=production_data), "is production's DATA_DIR"),
        "a DATA_DIR inside production's": RefusedEnv(
            build_env(DATA_DIR=f"{production_data}/dev"),
            "is inside production's DATA_DIR",
        ),
        "a DATA_DIR that contains production's": RefusedEnv(
            build_env(DATA_DIR=directory, LIBRARY_DIR=f"{directory}/dev-library"),
            "contains production's DATA_DIR",
        ),
        "production's library": RefusedEnv(
            build_env(LIBRARY_DIR=str(installation.library)), "is production's LIBRARY_DIR"
        ),
        "the setup of production's sandbox": RefusedEnv(
            build_env(SANDBOX_SETUP_DIR=f"{production_data}/sandbox"),
            "-> /opt/sandbox",
        ),
        "production's ANDROID_DIR": RefusedEnv(
            build_env(ANDROID_DIR=f"{production_data}/android"), "ANDROID_DIR in .env"
        ),
        "the release app": RefusedEnv(build_env(APP_VARIANT="release"), "only production builds the release app"),
        "no DATA_DIR": RefusedEnv(build_env(DATA_DIR=None), "no DATA_DIR in .env"),
        "an empty DATA_DIR": RefusedEnv(build_env(DATA_DIR=""), "no DATA_DIR in .env"),
        # Outside the stack's own DATA_DIR, or on what every program shares.
        "a library in /tmp": RefusedEnv(build_env(LIBRARY_DIR="/tmp"), "is or contains /tmp"),
        "a sandbox in /tmp": RefusedEnv(build_env(SANDBOX_DIR="/tmp"), "SANDBOX_DIR in .env"),
        "a library in the home directory": RefusedEnv(
            build_env(LIBRARY_DIR=f"{home}/.ssh"), "is inside your home directory"
        ),
        "a library outside the stack's DATA_DIR": RefusedEnv(
            build_env(LIBRARY_DIR=f"{directory}/elsewhere"),
            "is not inside the stack's DATA_DIR",
        ),
        "a DATA_DIR in the home directory": RefusedEnv(
            build_env(DATA_DIR=f"{home}/dev", LIBRARY_DIR=f"{home}/dev/library"),
            "is inside your home directory",
        ),
        # $HOME is the temporary home: the home directory of the password database still counts.
        "a library in the home directory of the password database": RefusedEnv(
            build_env(LIBRARY_DIR=f"{PASSWD_HOME}/scanmylib-tests-never-created"),
            f"is inside your home directory ({PASSWD_HOME})",
        ),
    }


class TheComposeCommandWhenTheEnvIsAValidDevelopmentOne(InstallationTestCase):
    compose_run: ClassVar[ScriptRun]
    docker_commands: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.worktree / ".env").write_text(installation.build_development_env())
        cls.compose_run = installation.run_script(installation.worktree, "dev.sh", "compose", "ps")
        cls.docker_commands = installation.read_docker_commands()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.compose_run.returncode, 0, self.compose_run.stderr)

    def test_should_run_docker_compose_ps(self) -> None:
        self.assertTrue(any(" ps" in command and "config" not in command for command in self.docker_commands))


class TheComposeCommandWhenTheEnvWouldNotKeepTheStackApartFromProduction(InstallationTestCase):
    expected_refusals: ClassVar[dict[str, str]]
    compose_runs: ClassVar[dict[str, ScriptRun]]
    docker_calls: ClassVar[dict[str, list[LoggedCall]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        refused_envs = build_refused_envs(installation)
        cls.expected_refusals = {row: refused_env.refusal for row, refused_env in refused_envs.items()}
        cls.compose_runs, cls.docker_calls = {}, {}
        for row, refused_env in refused_envs.items():
            installation.forget_docker_calls()
            (installation.worktree / ".env").write_text(refused_env.text)
            cls.compose_runs[row] = installation.run_script(installation.worktree, "dev.sh", "compose", "ps")
            cls.docker_calls[row] = installation.read_docker_calls()

    def test_should_refuse_each_and_say_why(self) -> None:
        self.assertEqual(sorted(self.compose_runs), sorted(self.expected_refusals))
        for row, compose_run in self.compose_runs.items():
            with self.subTest(row):
                self.assertNotEqual(compose_run.returncode, 0)
                self.assertIn(self.expected_refusals[row], compose_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(sorted(self.docker_calls), sorted(self.expected_refusals))
        for row, docker_calls in self.docker_calls.items():
            with self.subTest(row):
                self.assertEqual(list_writing_calls(docker_calls), [])

    def test_should_never_run_docker_compose_ps(self) -> None:
        self.assertEqual(sorted(self.docker_calls), sorted(self.expected_refusals))
        for row, docker_calls in self.docker_calls.items():
            with self.subTest(row):
                commands = [" ".join(call["argv"]) for call in docker_calls]
                self.assertEqual([command for command in commands if is_compose_ps(command)], [])


class TheComposeCommandWhenComposeYamlHasASettingOutsideTheAllowlist(InstallationTestCase):
    expected_refusals: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "privileged": "privileged is not allowed",
            "volumes_from": "volumes_from is not allowed",
            "use_api_socket": "use_api_socket is not allowed",
            "cap_add": "cap_add is not allowed",
            "pid": "pid is not allowed",
            "env_file": "service api: env_file is not allowed",
            "label_file": "service api: label_file is not allowed",
            "extends of a service with an env_file": "service api: env_file",
            "network_mode of production's network": "network_mode scanmylib_default is not allowed",
            "include": "include is not allowed",
            "production's network as an external one": "network default (scanmylib_default) is not the stack's own",
        }
    )
    compose_runs: ClassVar[dict[str, ScriptRun]]
    docker_calls: ClassVar[dict[str, list[LoggedCall]]]

    @classmethod
    def setUpClass(cls) -> None:
        # A branch that changes compose.yaml: privileges, another container's volumes, the Docker API, host files read
        # into a container, another project's network. As docker compose really resolves them: env_file and label_file
        # only show without interpolation.
        installation = make_installation(cls)
        worktree = installation.worktree
        (worktree / ".env").write_text(installation.build_development_env())
        secrets = installation.home / ".config" / "secrets.env"
        secrets.parent.mkdir(parents=True)
        secrets.write_text("TOKEN=secret\n")
        (worktree / "base.yaml").write_text(f"services:\n  base:\n    image: x\n    env_file: {secrets}\n")
        (worktree / "more.yaml").write_text(
            "services:\n  more:\n    image: scanmylib-dev-api:latest\n"
            "    network_mode: none\n    environment:\n      X: ${TOKEN-none}\n"
        )
        api = "    read_only: true\n"
        changes = {
            "privileged": ComposeChange(api, api + "    privileged: true\n"),
            "volumes_from": ComposeChange(api, api + '    volumes_from: ["container:scanmylib-api-1"]\n'),
            "use_api_socket": ComposeChange(api, api + "    use_api_socket: true\n"),
            "cap_add": ComposeChange(api, api + "    cap_add: [SYS_ADMIN]\n"),
            "pid": ComposeChange(api, api + "    pid: host\n"),
            "env_file": ComposeChange(api, api + f"    env_file: [{secrets}]\n"),
            "label_file": ComposeChange(api, api + f"    label_file: {secrets}\n"),
            "extends of a service with an env_file": ComposeChange(
                api,
                api + "    extends:\n      file: base.yaml\n      service: base\n",
            ),
            "network_mode of production's network": ComposeChange(api, api + "    network_mode: scanmylib_default\n"),
            "include": ComposeChange(
                "services:\n",
                f"include:\n  - path: more.yaml\n    env_file: {secrets}\nservices:\n",
            ),
            "production's network as an external one": ComposeChange(
                "services:\n",
                "networks:\n  default:\n    name: scanmylib_default\n    external: true\nservices:\n",
            ),
        }
        compose = worktree / "compose.yaml"
        original = compose.read_text()
        cls.compose_runs, cls.docker_calls = {}, {}
        for row, change in changes.items():
            installation.forget_docker_calls()
            compose.write_text(original.replace(change.anchor, change.replacement, 1))
            cls.compose_runs[row] = installation.run_script(worktree, "dev.sh", "compose", "ps")
            cls.docker_calls[row] = installation.read_docker_calls()

    def test_should_refuse_each_and_say_why(self) -> None:
        self.assertEqual(sorted(self.compose_runs), sorted(self.expected_refusals))
        for row, compose_run in self.compose_runs.items():
            with self.subTest(row):
                self.assertNotEqual(compose_run.returncode, 0)
                self.assertIn(self.expected_refusals[row], compose_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(sorted(self.docker_calls), sorted(self.expected_refusals))
        for row, docker_calls in self.docker_calls.items():
            with self.subTest(row):
                self.assertEqual(list_writing_calls(docker_calls), [])


class TheComposeCommandWhenTheCallerSetsVariablesOfDockerCompose(InstallationTestCase):
    caller_variables: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "COMPOSE_PROJECT_NAME": "scanmylib",
            "COMPOSE_FILE": "/elsewhere.yaml",
            "COMPOSE_PROFILES": "setup",
            "IMAGE_PREFIX": "scanmylib",
            "API_PORT": "8765",
        }
    )
    worktree: ClassVar[Path]
    compose_run: ClassVar[ScriptRun]
    compose_calls: ClassVar[list[LoggedCall]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.worktree = installation.worktree
        (cls.worktree / ".env").write_text(installation.build_development_env())
        caller_variables = {**cls.caller_variables, "DATA_DIR": str(installation.production_data)}
        cls.compose_run = installation.run_script(cls.worktree, "dev.sh", "compose", "ps", environment=caller_variables)
        cls.compose_calls = installation.read_compose_calls()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.compose_run.returncode, 0, self.compose_run.stderr)

    def test_should_hand_none_of_them_to_docker_compose(self) -> None:
        self.assertNotEqual(self.compose_calls, [])
        for call in self.compose_calls:
            with self.subTest(call=call["argv"]):
                self.assertEqual(set(call["env"]) - {"DOCKER_HOST"}, set())

    def test_should_read_the_worktree_s_env_alone(self) -> None:
        self.assertNotEqual(self.compose_calls, [])
        for call in self.compose_calls:
            with self.subTest(call=call["argv"]):
                self.assertIn(f"--env-file {self.worktree}/.env", " ".join(call["argv"]))


class TheComposeCommandWhenItWouldReachBeyondTheStack(InstallationTestCase):
    expected_refusals: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "another project": "no global option",
            "another project with an equals sign": "no global option",
            "another compose file": "no global option",
            "a one-off container mounting the host's root": "run -v",
            "a one-off container publishing production's port": "run -p",
            "a one-off container with a capability": "run --cap-add",
            "a privileged exec": "exec --privileged",
            "a copy out of a container": "compose cp is not allowed",
            "a commit into production's image": "compose commit is not allowed",
            "a build with an SSH key": "build --ssh",
            "a build that pushes its image": "build --push",
            "a configuration written over production's .env": "config -o",
            "up of no service named": "name them",
            "up of both OCR services": "never start both",
        }
    )
    compose_runs: ClassVar[dict[str, ScriptRun]]
    docker_calls: ClassVar[dict[str, list[LoggedCall]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.worktree / ".env").write_text(installation.build_development_env())
        home = installation.home
        arguments = {
            "another project": ["-p", "scanmylib", "down"],
            "another project with an equals sign": ["--project-name=scanmylib", "down"],
            "another compose file": ["--file", "x.yaml", "ps"],
            "a one-off container mounting the host's root": ["run", "--rm", "-v", "/:/host", "api", "sh"],
            "a one-off container publishing production's port": ["run", "-p", "8765:8765", "api"],
            "a one-off container with a capability": ["run", "--cap-add", "SYS_ADMIN", "api"],
            "a privileged exec": ["exec", "--privileged", "api", "sh"],
            "a copy out of a container": ["cp", "api:/state/token", str(home)],
            "a commit into production's image": ["commit", "api", "scanmylib-api:latest"],
            "a build with an SSH key": ["build", "api", "--ssh", f"default={home}/.ssh/id_ed25519"],
            "a build that pushes its image": ["build", "api", "--push"],
            "a configuration written over production's .env": [
                "config",
                "-o",
                str(installation.production_checkout / ".env"),
            ],
            "up of no service named": ["up", "-d"],
            "up of both OCR services": ["up", "-d", "api", "ocr", "ocr-fake"],
        }
        cls.compose_runs, cls.docker_calls = {}, {}
        for row, row_arguments in arguments.items():
            installation.forget_docker_calls()
            cls.compose_runs[row] = installation.run_script(installation.worktree, "dev.sh", "compose", *row_arguments)
            cls.docker_calls[row] = installation.read_docker_calls()

    def test_should_refuse_each_and_say_why(self) -> None:
        self.assertEqual(sorted(self.compose_runs), sorted(self.expected_refusals))
        for row, compose_run in self.compose_runs.items():
            with self.subTest(row):
                self.assertNotEqual(compose_run.returncode, 0)
                self.assertIn(self.expected_refusals[row], compose_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(sorted(self.docker_calls), sorted(self.expected_refusals))
        for row, docker_calls in self.docker_calls.items():
            with self.subTest(row):
                self.assertEqual(list_writing_calls(docker_calls), [])


class TheBuildCommand(InstallationTestCase):
    build_run: ClassVar[ScriptRun]
    compose_builds: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.worktree / ".env").write_text(installation.build_development_env())
        cls.build_run = installation.run_script(installation.worktree, "dev.sh", "build")
        commands = installation.read_docker_commands()
        cls.compose_builds = [command for command in commands if re.search(r"^compose .* build ", command)]

    def test_should_succeed(self) -> None:
        self.assertEqual(self.build_run.returncode, 0, self.build_run.output)

    def test_should_build_the_api_once_so_that_it_reports_the_version_of_a_development_build(self) -> None:
        self.assertEqual(len(self.compose_builds), 1)
        self.assertRegex(self.compose_builds[0], rf" build --build-arg DEV_VERSION={DEV_VERSION} api$")


class TheStatusCommandWhenProductionsRunningApiMountsTheLibrary(InstallationTestCase):
    status_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        moved_library = installation.directory / "moved-library"
        container = {
            "Name": "/scanmylib-api-1",
            "Config": {
                "Image": "scanmylib-api:latest",
                "Labels": {"com.docker.compose.project.working_dir": str(installation.production_checkout)},
            },
            "Mounts": [{"Type": "bind", "Source": str(moved_library), "Destination": "/library"}],
        }
        installation.answer_docker(
            [{"match": PRODUCTION_PS, "stdout": "abc\n"}, {"match": "^inspect abc$", "stdout": json.dumps([container])}]
        )
        (installation.worktree / ".env").write_text(installation.build_development_env(LIBRARY_DIR=str(moved_library)))
        cls.status_run = installation.run_script(installation.worktree, "dev.sh", "status")

    def test_should_refuse_since_what_production_s_running_containers_mount_is_production_s(self) -> None:
        self.assertNotEqual(self.status_run.returncode, 0)
        self.assertIn("mount /library of scanmylib-api-1", self.status_run.stderr)


if __name__ == "__main__":
    unittest.main()
