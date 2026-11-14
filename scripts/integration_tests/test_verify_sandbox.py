"""The check of the OCR sandbox's isolation (scripts/verify-sandbox.sh), against the answers of the docker stand-in in
throwaway installations (installation_support.py).

Needs git, bash and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_verify_sandbox.py'
"""

from __future__ import annotations

import unittest
from typing import ClassVar

from docker_shim import Rule
from installation_support import InstallationTestCase, ScriptRun, build_running_sandbox_rules, make_installation

CLIPBOARD_WRITE = "\N{ESCAPE}]52;c;aGk=\a"
SHOWN_CLIPBOARD_WRITE = "^[]52;c;aGk=^G"
SCREEN_CLEAR = "\N{ESCAPE}[2J"
SHOWN_SCREEN_CLEAR = "^[[2J"


class WhenProductionsSandboxIsIsolated(InstallationTestCase):
    verification: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        production_data = installation.production_data
        installation.answer_docker(build_running_sandbox_rules(f"{production_data}/sandbox", str(production_data)))
        cls.verification = installation.run_script(
            installation.production_checkout,
            "verify-sandbox.sh",
            environment={"DATA_DIR": "/elsewhere", "SANDBOX_DIR": "/elsewhere"},
        )

    def test_should_pass_whatever_directories_the_caller_s_environment_names(self) -> None:
        self.assertEqual(self.verification.returncode, 0, self.verification.output)

    def test_should_say_that_every_check_passed(self) -> None:
        self.assertIn("RESULT: all checks passed", self.verification.stdout)


class WhenProductionRunsTheFakeOcr(InstallationTestCase):
    verification: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        production_data = installation.production_data
        fake_ocr_rules = build_running_sandbox_rules(
            f"{production_data}/sandbox", str(production_data), kind="ocr-fake"
        )
        installation.answer_docker(fake_ocr_rules)
        cls.verification = installation.run_script(installation.production_checkout, "verify-sandbox.sh")

    def test_should_fail_since_production_s_sandbox_does_not_run(self) -> None:
        self.assertNotEqual(self.verification.returncode, 0)
        self.assertIn("production's OCR sandbox (ocr) is not running", self.verification.stdout)


class WhenGivenTheContainerOfTheFakeOcr(InstallationTestCase):
    verification: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        production_data = installation.production_data
        fake_ocr_rules = build_running_sandbox_rules(
            f"{production_data}/sandbox", str(production_data), kind="ocr-fake"
        )
        installation.answer_docker(fake_ocr_rules)
        cls.verification = installation.run_script(installation.production_checkout, "verify-sandbox.sh", "fakeid")

    def test_should_fail_since_production_never_falls_back_to_the_fake_ocr(self) -> None:
        self.assertNotEqual(self.verification.returncode, 0)
        self.assertIn("is the fake OCR", self.verification.stdout)


class WhenADevelopmentStackRunsTheFakeOcr(InstallationTestCase):
    verification: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        (installation.worktree / ".env").write_text(installation.build_development_env())
        installation.answer_docker(
            build_running_sandbox_rules(
                f"{installation.production_data}/sandbox", str(installation.development_data), kind="ocr-fake"
            )
        )
        cls.verification = installation.run_script(installation.worktree, "verify-sandbox.sh")

    def test_should_pass(self) -> None:
        self.assertEqual(self.verification.returncode, 0, self.verification.output)


class WhenTheChecksInsideTheSandboxPrintControlSequences(InstallationTestCase):
    verification: ClassVar[ScriptRun]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        production_data = installation.production_data
        printing_controls: Rule = {
            "match": r"^exec ",
            "stdout": f"FAIL: a check ({CLIPBOARD_WRITE})\n",
            "stderr": f"{SCREEN_CLEAR}\n",
            "exit": 1,
        }
        installation.answer_docker(
            [printing_controls, *build_running_sandbox_rules(f"{production_data}/sandbox", str(production_data))]
        )
        cls.verification = installation.run_script(installation.production_checkout, "verify-sandbox.sh")

    def test_should_fail_as_the_checks_inside_do(self) -> None:
        self.assertEqual((self.verification.returncode, "RESULT: FAIL" in self.verification.stdout), (1, True))

    def test_should_show_their_standard_output_through_cat_v(self) -> None:
        self.assertIn(SHOWN_CLIPBOARD_WRITE, self.verification.stdout)

    def test_should_show_their_error_output_through_cat_v_since_a_process_of_the_sandbox_can_write_there(self) -> None:
        self.assertIn(SHOWN_SCREEN_CLEAR, self.verification.stdout)

    def test_should_hand_the_terminal_no_control_character(self) -> None:
        self.assertNotIn("\N{ESCAPE}", self.verification.output)


if __name__ == "__main__":
    unittest.main()
