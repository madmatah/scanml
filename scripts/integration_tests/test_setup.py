"""The first installation of production (scripts/setup.sh), in throwaway installations (installation_support.py).

Needs git, bash and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_setup.py'
"""

from __future__ import annotations

import unittest
from typing import ClassVar

from installation_support import InstallationTestCase, ScriptRun, list_writing_calls, make_installation


class WhenRunOutsideProductionsCheckout(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.setup_run = installation.run_script(installation.worktree, "setup.sh")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_it_is_not_production_s_checkout(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("is not production's checkout", self.setup_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenProductionHoldsADatabase(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        cls.setup_run = installation.run_script(installation.production_checkout, "setup.sh")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_since_production_already_exists(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("production already exists", self.setup_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenProductionsContainersRunWithoutADatabase(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]
    writing_calls: ClassVar[list[list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.production_data / "state" / "scanmylib.db").unlink()
        cls.setup_run = installation.run_script(installation.production_checkout, "setup.sh")
        cls.writing_calls = list_writing_calls(installation.read_docker_calls())

    def test_should_refuse_and_say_that_new_versions_are_deployed_with_deploy_sh(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("deploy new versions with scripts/deploy.sh", self.setup_run.stderr)

    def test_should_only_read_from_docker(self) -> None:
        self.assertEqual(self.writing_calls, [])


class WhenTheCheckoutIsNotAPublishedRelease(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.production_data / "state" / "scanmylib.db").unlink()
        installation.commit_after_the_release()
        cls.setup_run = installation.run_script(installation.production_checkout, "setup.sh")

    def test_should_refuse_since_a_first_installation_is_a_published_release_too(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("install a published release: HEAD", self.setup_run.stderr)


class WhenAChangeIsHiddenFromGitStatus(InstallationTestCase):
    setup_run: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        installation.hide_a_change_with_skip_worktree()
        cls.setup_run = installation.run_script(installation.production_checkout, "setup.sh")

    def test_should_refuse_and_name_the_file_it_could_hide(self) -> None:
        self.assertNotEqual(self.setup_run.returncode, 0)
        self.assertIn("assume-unchanged or skip-worktree could hide changes: compose.yaml", self.setup_run.stderr)


if __name__ == "__main__":
    unittest.main()
