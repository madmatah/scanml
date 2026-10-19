"""The .env of a development stack (scripts/dev-env.sh), written in the worktrees of throwaway installations
(installation_support.py).

Needs git, bash and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_dev_env.py'
"""

from __future__ import annotations

import socket
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from installation_support import (
    InstallationTestCase,
    ScriptRun,
    list_writing_calls,
    make_installation,
    read_text_if_present,
)

DEVELOPMENT_PORT = 8770


def is_port_listened_on(port: int) -> bool:
    with socket.socket() as probe:
        # The probes of the processes that import this module at the same time then bind the port together: only a
        # listening socket, such as a development stack's, refuses them.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


@dataclass(frozen=True)
class ForeignEnv:
    text: str
    refusal: str


def parse_env(env_text: str | None) -> dict[str, str]:
    if env_text is None:
        raise FileNotFoundError("dev-env.sh wrote no .env")
    lines = env_text.splitlines()
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


@unittest.skipIf(is_port_listened_on(DEVELOPMENT_PORT), f"port {DEVELOPMENT_PORT} is in use (a development stack runs)")
class WhenRunInAWorktree(InstallationTestCase):
    dev_env_run: ClassVar[ScriptRun]
    env_text: ClassVar[str | None]
    production_data: ClassVar[Path]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.production_data = installation.production_data
        cls.dev_env_run = installation.run_script(installation.worktree, "dev-env.sh")
        cls.env_text = read_text_if_present(installation.worktree / ".env")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_succeed(self) -> None:
        self.assertEqual(self.dev_env_run.returncode, 0, self.dev_env_run.stderr)

    def test_should_name_the_development_project(self) -> None:
        self.assertEqual(parse_env(self.env_text)["COMPOSE_PROJECT_NAME"], "scanmylib-dev")

    def test_should_keep_the_stack_s_data_next_to_production_s(self) -> None:
        self.assertEqual(parse_env(self.env_text)["DATA_DIR"], f"{self.production_data}-dev")

    def test_should_give_the_stack_an_android_toolchain_of_its_own(self) -> None:
        self.assertEqual(parse_env(self.env_text)["ANDROID_DIR"], f"{self.production_data}-dev/android")

    def test_should_sign_with_production_s_key(self) -> None:
        self.assertEqual(parse_env(self.env_text)["ANDROID_KEYSTORE_DIR"], f"{self.production_data}/android/keystore")

    def test_should_read_production_s_ocr_models(self) -> None:
        self.assertEqual(parse_env(self.env_text)["SANDBOX_DIR"], f"{self.production_data}/sandbox")

    def test_should_build_the_dev_app_and_run_the_fake_ocr_on_the_development_port(self) -> None:
        development_env = parse_env(self.env_text)
        settings = [development_env[name] for name in ("APP_VARIANT", "OCR_SERVICE", "API_PORT")]
        self.assertEqual(settings, ["dev", "ocr-fake", str(DEVELOPMENT_PORT)])

    def test_should_never_write_the_sandbox_since_only_production_s_setup_does(self) -> None:
        self.assertNotIn("SANDBOX_SETUP_DIR", parse_env(self.env_text))

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenRunInProductionsCheckout(InstallationTestCase):
    dev_env_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.dev_env_run = installation.run_script(installation.production_checkout, "dev-env.sh")

    def test_should_refuse_since_its_env_is_production_s(self) -> None:
        self.assertNotEqual(self.dev_env_run.returncode, 0)
        self.assertIn("is production's checkout", self.dev_env_run.stderr)


class WhenTheWorktreeHoldsAnEnvThatIsNotADevelopmentOne(InstallationTestCase):
    foreign_envs: ClassVar[Mapping[str, ForeignEnv]] = MappingProxyType(
        {
            "another stack's .env": ForeignEnv("COMPOSE_PROJECT_NAME=scanmylib-review\n", "not scanmylib-dev"),
            "a .env in another format": ForeignEnv("COMPOSE_PROJECT_NAME=scanmylib-dev # mine\n", "not a valid .env"),
        }
    )
    dev_env_runs: ClassVar[dict[str, ScriptRun]]
    env_texts_after: ClassVar[dict[str, str | None]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        env_path = installation.worktree / ".env"
        cls.dev_env_runs, cls.env_texts_after = {}, {}
        for row, foreign_env in cls.foreign_envs.items():
            env_path.write_text(foreign_env.text)
            cls.dev_env_runs[row] = installation.run_script(installation.worktree, "dev-env.sh")
            cls.env_texts_after[row] = read_text_if_present(env_path)

    def test_should_refuse_to_write_over_it_and_say_why(self) -> None:
        self.assertEqual(sorted(self.dev_env_runs), sorted(self.foreign_envs))
        for row, dev_env_run in self.dev_env_runs.items():
            with self.subTest(row):
                self.assertNotEqual(dev_env_run.returncode, 0)
                self.assertIn(self.foreign_envs[row].refusal, dev_env_run.stderr)

    def test_should_leave_it_as_it_was(self) -> None:
        self.assertEqual(
            self.env_texts_after, {row: foreign_env.text for row, foreign_env in self.foreign_envs.items()}
        )


if __name__ == "__main__":
    unittest.main()
