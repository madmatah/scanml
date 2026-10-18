"""The project version: the repository's VERSION file, copied into the api image."""

from __future__ import annotations

from pathlib import Path

import pytest

from scanmylib import read_version


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("0.2.3\n", "0.2.3"),
        (" 1.10.0 \n\n", "1.10.0"),
        ("0.3.0-rc.1", "0.3.0-rc.1"),
        ("", "unknown"),
        ("0.2.3\n0.2.4\n", "unknown"),
        ("<b>1</b>", "unknown"),
        ("1" * 65, "unknown"),
    ],
)
def test_version_comes_from_the_version_file(tmp_path: Path, content: str, expected: str) -> None:
    version_file = tmp_path / "VERSION"
    version_file.write_text(content)
    assert read_version(version_file) == expected


def test_unreadable_version_file(tmp_path: Path) -> None:
    assert read_version(tmp_path / "VERSION") == "unknown"
    (tmp_path / "binary").write_bytes(b"\xff\xfe")
    assert read_version(tmp_path / "binary") == "unknown"
