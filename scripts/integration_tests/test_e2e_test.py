"""The end-to-end test (scripts/e2e_test.py), which acts like the phone, against production's fake api in a throwaway
installation (installation_support.py).

Needs git, bash and the docker CLI with its compose plugin. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_e2e_test.py'
"""

from __future__ import annotations

import subprocess
import unittest
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar

from installation_support import InstallationTestCase, ScriptRun, make_installation, start_fake_api


@dataclass(frozen=True)
class RefusedApiUrl:
    url_template: str
    refusal: str


class WhenTheApiUrlMayReachProduction(InstallationTestCase):
    refused_api_urls: ClassVar[Mapping[str, RefusedApiUrl]] = MappingProxyType(
        {
            "production's port with a query": RefusedApiUrl(
                "http://127.0.0.1:{production_port}?x", "is production's port"
            ),
            "production's port with a fragment": RefusedApiUrl(
                "http://127.0.0.1:{production_port}#x", "is production's port"
            ),
            "production's port with a leading zero": RefusedApiUrl(
                "http://localhost:0{production_port}/", "is production's port"
            ),
            "production's default port": RefusedApiUrl("http://127.0.0.1:8765", "is production's port"),
            "no port": RefusedApiUrl("http://127.0.0.1", "no explicit port"),
            "a port out of range": RefusedApiUrl("http://127.0.0.1:99999", "cannot tell the port"),
            "another scheme": RefusedApiUrl("ftp://127.0.0.1:8770", "expected http://HOST:PORT"),
        }
    )
    end_to_end_runs: ClassVar[dict[str, ScriptRun]]
    production_request_count: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        installation = make_installation(cls)
        port = installation.production_api_port
        production_api = start_fake_api(cls, port)
        (installation.worktree / ".env").write_text(installation.build_development_env())
        image = installation.directory / "page.jpg"
        image.write_bytes(b"jpeg")
        cls.end_to_end_runs = {}
        for row, refused_api_url in cls.refused_api_urls.items():
            api_url = refused_api_url.url_template.format(production_port=port)
            completed = subprocess.run(
                ["python3", str(installation.worktree / "scripts" / "e2e_test.py"), str(image), "--api", api_url],
                cwd=installation.worktree,
                capture_output=True,
                text=True,
                timeout=60,
                env=installation.build_environment(),
                check=False,
            )
            cls.end_to_end_runs[row] = ScriptRun(completed.returncode, completed.stdout, completed.stderr)
        cls.production_request_count = production_api.request_count

    def test_should_refuse_to_write_a_test_document_into_production_and_say_why(self) -> None:
        self.assertEqual(sorted(self.end_to_end_runs), sorted(self.refused_api_urls))
        for row, end_to_end_run in self.end_to_end_runs.items():
            with self.subTest(row):
                self.assertNotEqual(end_to_end_run.returncode, 0)
                self.assertIn("refusing to write a test document into production", end_to_end_run.stderr)
                self.assertIn(self.refused_api_urls[row].refusal, end_to_end_run.stderr)

    def test_should_send_no_request_to_production_s_api(self) -> None:
        self.assertEqual(self.production_request_count, 0)


if __name__ == "__main__":
    unittest.main()
