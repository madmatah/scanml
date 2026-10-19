"""The project version: the repository's VERSION file, copied into the api image."""

from __future__ import annotations

from pathlib import Path

import pytest

from scanmylib import read_version

UNKNOWN = "unknown"


def write_version_file(folder: Path, content: str) -> Path:
    version_file = folder / "VERSION"
    version_file.write_text(content)
    return version_file


class TestTheVersion:
    class TestTheReadVersionFunction:
        class TestWhenTheVersionEndsWithALineEnd:
            @pytest.fixture
            def version(self, tmp_path: Path) -> str:
                return read_version(write_version_file(tmp_path, "0.2.3\n"))

            def test_should_read_the_version_without_the_line_end(self, version: str) -> None:
                assert version == "0.2.3"

        class TestWhenTheVersionIsSurroundedByBlanks:
            @pytest.fixture
            def version(self, tmp_path: Path) -> str:
                return read_version(write_version_file(tmp_path, " 1.10.0 \n\n"))

            def test_should_read_the_version_without_the_blanks(self, version: str) -> None:
                assert version == "1.10.0"

        class TestWhenTheVersionIsAPrerelease:
            @pytest.fixture
            def version(self, tmp_path: Path) -> str:
                return read_version(write_version_file(tmp_path, "0.3.0-rc.1"))

            def test_should_read_the_version_whole(self, version: str) -> None:
                assert version == "0.3.0-rc.1"

        class TestWhenTheFileHoldsNoSingleVersion:
            @pytest.fixture(
                params=["", "0.2.3\n0.2.4\n", "<b>1</b>", "1" * 65],
                ids=["an empty file", "two versions", "markup", "a version longer than 64 characters"],
            )
            def version(self, request: pytest.FixtureRequest, tmp_path: Path) -> str:
                return read_version(write_version_file(tmp_path, request.param))

            def test_should_report_an_unknown_version(self, version: str) -> None:
                assert version == UNKNOWN

        class TestWhenTheFileIsMissing:
            @pytest.fixture
            def version(self, tmp_path: Path) -> str:
                return read_version(tmp_path / "VERSION")

            def test_should_report_an_unknown_version(self, version: str) -> None:
                assert version == UNKNOWN

        class TestWhenTheVersionIsWrittenInThe16BitUnicodeFormatWithItsByteOrderMark:
            @pytest.fixture
            def version(self, tmp_path: Path) -> str:
                version_file = tmp_path / "VERSION"
                version_file.write_text("0.2.3", encoding="utf-16")
                return read_version(version_file)

            def test_should_report_an_unknown_version(self, version: str) -> None:
                assert version == UNKNOWN
