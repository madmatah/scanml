"""The pins of the web UI's toolchain: Node and pnpm in the image of the gate's web tools (scripts/lint/Dockerfile.web)
and in the api's image (server/Dockerfile), and the pnpm that the web UI's package.json names, which must all agree, so
that no copy is bumped without the others.

Standard library only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILES = {
    "the gate's web tools": ROOT / "scripts" / "lint" / "Dockerfile.web",
    "the api": ROOT / "server" / "Dockerfile",
}
PACKAGE_MANIFEST = ROOT / "server" / "scanmylib" / "web" / "package.json"
NODE_IMAGE_PATTERN = re.compile(r"^FROM (?P<image>node:\S+)", re.MULTILINE)
PNPM_DOWNLOAD_PATTERN = re.compile(
    r"^ADD --checksum=(?P<checksum>\S+)\s+"
    r"(?P<url>https://github\.com/pnpm/pnpm/releases/download/v(?P<version>[^/\s]+)/pnpm-linux-x64\.tar\.gz)\s",
    re.MULTILINE,
)


def read_joined_lines(dockerfile: Path) -> str:
    return re.sub(r"\\\n\s*", " ", dockerfile.read_text())


class TheDockerfiles(unittest.TestCase):
    def setUp(self) -> None:
        texts = {name: read_joined_lines(path) for name, path in DOCKERFILES.items()}
        self.node_images = {name: NODE_IMAGE_PATTERN.findall(text) for name, text in texts.items()}
        self.pnpm_downloads = {
            name: [(match["checksum"], match["url"]) for match in PNPM_DOWNLOAD_PATTERN.finditer(text)]
            for name, text in texts.items()
        }

    def test_should_each_start_one_stage_from_node(self) -> None:
        self.assertEqual(
            {name: len(images) for name, images in self.node_images.items()}, dict.fromkeys(DOCKERFILES, 1)
        )

    def test_should_pull_the_same_node_image_by_the_same_digest(self) -> None:
        self.assertEqual(len({tuple(images) for images in self.node_images.values()}), 1, self.node_images)

    def test_should_each_download_pnpm_once(self) -> None:
        self.assertEqual(
            {name: len(downloads) for name, downloads in self.pnpm_downloads.items()}, dict.fromkeys(DOCKERFILES, 1)
        )

    def test_should_download_the_same_pnpm_checked_by_the_same_checksum(self) -> None:
        self.assertEqual(len({tuple(downloads) for downloads in self.pnpm_downloads.values()}), 1, self.pnpm_downloads)


class ThePackageManifest(unittest.TestCase):
    def setUp(self) -> None:
        self.package_manager = json.loads(PACKAGE_MANIFEST.read_text())["packageManager"]
        downloads = PNPM_DOWNLOAD_PATTERN.finditer(read_joined_lines(DOCKERFILES["the gate's web tools"]))
        self.downloaded_versions = [match["version"] for match in downloads]

    def test_should_name_the_pnpm_that_the_dockerfiles_download(self) -> None:
        self.assertEqual([f"pnpm@{version}" for version in self.downloaded_versions], [self.package_manager])


if __name__ == "__main__":
    unittest.main()
