"""The operation of production by hand (scripts/prod.sh), in throwaway installations (installation_support.py).

Needs git, bash and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_prod.py'
"""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from docker_shim import LoggedCall
from installation_support import (
    VERSION,
    Installation,
    InstallationTestCase,
    ScriptRun,
    UncleanCheckout,
    list_writing_calls,
    make_installation,
)


def change_a_tracked_file(installation: Installation) -> None:
    (installation.production_checkout / "compose.yaml").write_text("services: {}\n")


def delete_the_release_tag(installation: Installation) -> None:
    installation.run_git(installation.production_checkout, "tag", "--delete", f"v{VERSION}")


class WhenTheCallerSetsVariablesOfDockerCompose(InstallationTestCase):
    caller_variables: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "COMPOSE_PROJECT_NAME": "scanmylib-dev",
            "COMPOSE_FILE": "/elsewhere.yaml",
            "DATA_DIR": "/elsewhere",
            "COMPOSE_PROFILES": "fake-ocr",
        }
    )
    production_checkout: ClassVar[Path]
    compose_run: ClassVar[ScriptRun]
    compose_calls: ClassVar[list[LoggedCall]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.production_checkout = installation.production_checkout
        cls.compose_run = installation.run_script(
            cls.production_checkout, "prod.sh", "compose", "ps", environment=cls.caller_variables
        )
        cls.compose_calls = installation.read_compose_calls()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.compose_run.returncode, 0, self.compose_run.stderr)

    def test_should_hand_none_of_them_to_docker_compose(self) -> None:
        self.assertEqual([set(call["env"]) - {"DOCKER_HOST"} for call in self.compose_calls], [set()])

    def test_should_run_docker_compose_on_production_s_checkout(self) -> None:
        self.assertIn(f"--project-directory {self.production_checkout} ", " ".join(self.compose_calls[0]["argv"]))

    def test_should_read_production_s_env_alone(self) -> None:
        self.assertIn(f"--env-file {self.production_checkout}/.env ps", " ".join(self.compose_calls[0]["argv"]))

    def test_should_enable_no_profile(self) -> None:
        self.assertNotIn("--profile", " ".join(self.compose_calls[0]["argv"]))


class WhenRunOutsideProductionsCheckout(InstallationTestCase):
    checkout_kinds: ClassVar[tuple[str, ...]] = ("a worktree", "another clone with a copy of production's .env")
    compose_runs: ClassVar[dict[str, ScriptRun]]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.worktree / ".env").write_text(installation.build_development_env())
        checkouts = (installation.worktree, installation.make_clone())
        cls.compose_runs = {
            row: installation.run_script(checkout, "prod.sh", "compose", "ps")
            for row, checkout in zip(cls.checkout_kinds, checkouts, strict=True)
        }
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_it_is_not_production_s_checkout(self) -> None:
        self.assertEqual(sorted(self.compose_runs), sorted(self.checkout_kinds))
        for row, compose_run in self.compose_runs.items():
            with self.subTest(row):
                self.assertNotEqual(compose_run.returncode, 0)
                self.assertIn("is not production's checkout", compose_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenProductionsEnvIsADevelopmentOne(InstallationTestCase):
    compose_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        checkout = installation.production_checkout
        (checkout / ".env").write_text(installation.build_production_env(COMPOSE_PROJECT_NAME="scanmylib-dev"))
        cls.compose_run = installation.run_script(checkout, "prod.sh", "compose", "ps")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_it_is_not_production_s(self) -> None:
        self.assertNotEqual(self.compose_run.returncode, 0)
        self.assertIn("is not production's", self.compose_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenUpRunsOnTheCleanRelease(InstallationTestCase):
    up_run: ClassVar[ScriptRun]
    compose_calls: ClassVar[list[LoggedCall]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.up_run = installation.run_script(
            installation.production_checkout, "prod.sh", "compose", "up", "-d", "api", "ocr"
        )
        cls.compose_calls = installation.read_compose_calls()

    def test_should_succeed(self) -> None:
        self.assertEqual(self.up_run.returncode, 0, self.up_run.stderr)

    def test_should_never_build_so_that_production_starts_the_images_that_deploy_sh_built(self) -> None:
        self.assertEqual([call["argv"][-5:] for call in self.compose_calls], [["up", "--no-build", "-d", "api", "ocr"]])


class WhenTheCheckoutIsNotTheCleanRelease(InstallationTestCase):
    unclean_checkouts: ClassVar[Mapping[str, UncleanCheckout]] = MappingProxyType(
        {
            "an untracked file": UncleanCheckout(Installation.add_an_untracked_file, "uncommitted or untracked"),
            "a change": UncleanCheckout(change_a_tracked_file, "uncommitted"),
            "a hidden change": UncleanCheckout(
                Installation.hide_a_change_with_skip_worktree, "assume-unchanged or skip-worktree"
            ),
            "a commit after the release": UncleanCheckout(
                Installation.commit_after_the_release, f"is not the release v{VERSION}"
            ),
            "no tag": UncleanCheckout(delete_the_release_tag, f"no tag v{VERSION}"),
        }
    )
    reading_or_restarting_commands: ClassVar[tuple[str, ...]] = ("ps", "restart", "start")
    up_runs: ClassVar[dict[str, ScriptRun]]
    compose_calls_of_up: ClassVar[dict[str, list[LoggedCall]]]
    reading_or_restarting_runs: ClassVar[dict[str, dict[str, ScriptRun]]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.up_runs, cls.compose_calls_of_up, cls.reading_or_restarting_runs = {}, {}, {}
        for row, unclean_checkout in cls.unclean_checkouts.items():
            installation = make_installation(cls)
            checkout = installation.production_checkout
            unclean_checkout.make_unclean(installation)
            cls.up_runs[row] = installation.run_script(checkout, "prod.sh", "compose", "up", "-d", "api")
            cls.compose_calls_of_up[row] = installation.read_compose_calls()
            cls.reading_or_restarting_runs[row] = {
                command: installation.run_script(checkout, "prod.sh", "compose", command, "api")
                for command in cls.reading_or_restarting_commands
            }

    def test_should_refuse_up_and_say_why(self) -> None:
        self.assertEqual(sorted(self.up_runs), sorted(self.unclean_checkouts))
        for row, up_run in self.up_runs.items():
            with self.subTest(row):
                self.assertNotEqual(up_run.returncode, 0)
                self.assertIn(self.unclean_checkouts[row].refusal, up_run.stderr)

    def test_should_run_no_docker_compose_command_for_up(self) -> None:
        self.assertEqual(sorted(self.compose_calls_of_up), sorted(self.unclean_checkouts))
        for row, compose_calls in self.compose_calls_of_up.items():
            with self.subTest(row):
                self.assertEqual(compose_calls, [])

    def test_should_still_read_production_s_state_and_restart_its_containers_as_they_were_created_in_an_emergency(
        self,
    ) -> None:
        self.assertEqual(sorted(self.reading_or_restarting_runs), sorted(self.unclean_checkouts))
        for row, runs in self.reading_or_restarting_runs.items():
            for command, reading_or_restarting_run in runs.items():
                with self.subTest(row=row, command=command):
                    self.assertEqual(reading_or_restarting_run.returncode, 0, reading_or_restarting_run.stderr)


class WhenACommandWouldChangeProduction(InstallationTestCase):
    commands: ClassVar[Mapping[str, tuple[str, ...]]] = MappingProxyType(
        {
            "a build": ("build", "api"),
            "up with --build": ("up", "-d", "--build", "api"),
            "up with --build last": ("up", "-d", "api", "--build"),
            "a one-off container": ("run", "api", "sh"),
            "a copy out of a container": ("cp", "api:/state", "."),
            "up of the fake OCR": ("up", "-d", "ocr-fake"),
        }
    )
    compose_runs: ClassVar[dict[str, ScriptRun]]
    docker_calls: ClassVar[list[LoggedCall]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.compose_runs = {
            row: installation.run_script(installation.production_checkout, "prod.sh", "compose", *arguments)
            for row, arguments in cls.commands.items()
        }
        cls.docker_calls = installation.read_docker_calls()

    def test_should_refuse_each_since_production_changes_through_deploy_sh(self) -> None:
        self.assertEqual(sorted(self.compose_runs), sorted(self.commands))
        for row, compose_run in self.compose_runs.items():
            with self.subTest(row):
                self.assertNotEqual(compose_run.returncode, 0)
                self.assertIn("refused", compose_run.stderr)

    def test_should_call_docker_for_nothing(self) -> None:
        self.assertEqual(self.docker_calls, [])


class WhenConfigWouldWriteOverProductionsEnv(InstallationTestCase):
    compose_run: ClassVar[ScriptRun]
    docker_calls: ClassVar[list[LoggedCall]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        checkout = installation.production_checkout
        cls.compose_run = installation.run_script(
            checkout, "prod.sh", "compose", "config", "-o", str(checkout / ".env")
        )
        cls.docker_calls = installation.read_docker_calls()

    def test_should_refuse_since_production_changes_through_deploy_sh(self) -> None:
        self.assertNotEqual(self.compose_run.returncode, 0)
        self.assertIn("refused", self.compose_run.stderr)

    def test_should_call_docker_for_nothing(self) -> None:
        self.assertEqual(self.docker_calls, [])


if __name__ == "__main__":
    unittest.main()
