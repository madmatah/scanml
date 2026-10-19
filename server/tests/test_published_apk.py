"""The published APK's metadata, relayed by /api/health."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from scanmylib.published_apk import metadata_path, published_apk
from support import running_api

SHA256 = "0123456789abcdef" * 4
APK = b"PK\x03\x04 fake apk"
METADATA = {
    "application_id": "fr.scanmylib",
    "version_name": "1.2.3",
    "version_code": 10203,
    "sha256": SHA256,
    "size": len(APK),
}
OFFERED_APK = {
    "application_id": "fr.scanmylib",
    "version": "1.2.3",
    "version_code": 10203,
    "sha256": SHA256,
    "size": len(APK),
    "path": "/download/scanmylib.apk",
}
#: Neither UTF-8 nor anything else JSON reads.
UNDECODABLE_METADATA = b"\xff\xfe{"


def publish(apk_path: Path, metadata: dict[str, object] | str) -> None:
    apk_path.parent.mkdir(parents=True, exist_ok=True)
    apk_path.write_bytes(APK)
    text = metadata if isinstance(metadata, str) else json.dumps(metadata)
    metadata_path(apk_path).write_text(text, encoding="utf-8")


@dataclass(frozen=True)
class HealthApks:
    before_publication: object
    after_publication: object


@dataclass(frozen=True)
class OfferedVersion:
    version_name: str
    offered: dict[str, object] | None


@pytest.fixture(scope="module")
def health_apks(tmp_path_factory: pytest.TempPathFactory) -> HealthApks:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        before_publication = api.client.get("/api/health").json()["apk"]
        publish(api.settings.apk_path, METADATA)
        after_publication = api.client.get("/api/health").json()["apk"]
    return HealthApks(before_publication, after_publication)


class TestThePublishedApk:
    class TestWhenTheApiReportsItsHealth:
        class TestWhenNoApkIsPublished:
            def test_should_offer_no_apk(self, health_apks: HealthApks) -> None:
                assert health_apks.before_publication is None

            class TestWhenAnApkIsPublishedWhileTheApiRuns:
                def test_should_offer_it_with_its_download_path(self, health_apks: HealthApks) -> None:
                    assert health_apks.after_publication == OFFERED_APK

    class TestThePublishedApkFunction:
        class TestWhenAReleaseOrADevelopmentBuildIsPublished:
            @pytest.fixture(
                params=[
                    "0.3.0",
                    "0.2.4-dev.27+g1a2b3c4d5e6f",
                    "0.2.4-dev+g1a2b3c4d5e6f.dirty",
                    "0.2.4-dev",
                    "0.2.4-dev+g" + "a" * 53,
                ],
                ids=[
                    "a-release",
                    "a-development-build",
                    "a-development-build-with-uncommitted-changes",
                    "a-development-build-without-its-commit",
                    "a-version-of-64-characters-the-longest-accepted",
                ],
            )
            def offered_version(self, request: pytest.FixtureRequest, tmp_path: Path) -> OfferedVersion:
                apk = tmp_path / "app" / "scanmylib.apk"
                publish(apk, {**METADATA, "version_name": request.param})
                return OfferedVersion(request.param, published_apk(apk))

            def test_should_offer_it_with_its_version(self, offered_version: OfferedVersion) -> None:
                assert offered_version.offered == {**OFFERED_APK, "version": offered_version.version_name}

        class TestWhenNothingIsPublished:
            @pytest.fixture
            def offered(self, tmp_path: Path) -> dict[str, object] | None:
                return published_apk(tmp_path / "app" / "scanmylib.apk")

            def test_should_offer_nothing(self, offered: dict[str, object] | None) -> None:
                assert offered is None

        class TestWhenTheApkIsGoneAndItsMetadataLeft:
            @pytest.fixture
            def offered(self, tmp_path: Path) -> dict[str, object] | None:
                apk = tmp_path / "app" / "scanmylib.apk"
                publish(apk, METADATA)
                apk.unlink()
                return published_apk(apk)

            def test_should_offer_nothing(self, offered: dict[str, object] | None) -> None:
                assert offered is None

        class TestWhenTheApkIsPublishedWithoutItsMetadata:
            @pytest.fixture
            def offered(self, tmp_path: Path) -> dict[str, object] | None:
                apk = tmp_path / "app" / "scanmylib.apk"
                publish(apk, METADATA)
                metadata_path(apk).unlink()
                return published_apk(apk)

            def test_should_offer_nothing(self, offered: dict[str, object] | None) -> None:
                assert offered is None

        class TestWhenTheMetadataIsOfAnotherApk:
            @pytest.fixture
            def offered(self, tmp_path: Path) -> dict[str, object] | None:
                # An APK published without its metadata (a build from before it, or cut short) leaves the previous
                # APK's.
                apk = tmp_path / "app" / "scanmylib.apk"
                publish(apk, METADATA)
                apk.write_bytes(APK + b" rebuilt")
                return published_apk(apk)

            def test_should_offer_nothing_so_that_the_app_never_downloads_a_file_that_fails_its_check(
                self, offered: dict[str, object] | None
            ) -> None:
                assert offered is None

        class TestWhenTheMetadataIsNotText:
            @pytest.fixture
            def offered(self, tmp_path: Path) -> dict[str, object] | None:
                apk = tmp_path / "app" / "scanmylib.apk"
                apk.parent.mkdir(parents=True)
                apk.write_bytes(b"PK")
                metadata_path(apk).write_bytes(UNDECODABLE_METADATA)
                return published_apk(apk)

            def test_should_offer_nothing(self, offered: dict[str, object] | None) -> None:
                assert offered is None

        class TestWhenTheMetadataDoesNotHoldUp:
            @pytest.fixture(
                params=[
                    "not json",
                    "[1, 2]",
                    {**METADATA, "version_code": True},
                    {**METADATA, "version_code": 0},
                    {**METADATA, "version_code": 2**31},
                    {**METADATA, "version_code": "10203"},
                    {**METADATA, "version_name": "1.2"},
                    {**METADATA, "version_name": "1.2.3<script>"},
                    {**METADATA, "version_name": "1.2.3-dev\n"},
                    {**METADATA, "version_name": "0.2.4-dev+g" + "a" * 54},
                    {**METADATA, "version_name": "1.2.3-dév"},
                    {**METADATA, "version_name": '1.2.3-dev"x'},
                    {**METADATA, "version_name": "1.2.3+"},
                    {**METADATA, "application_id": "Fr.Scanmylib"},
                    {**METADATA, "application_id": "scanmylib"},
                    {**METADATA, "sha256": SHA256.upper()},
                    {**METADATA, "size": -1},
                    {name: field for name, field in METADATA.items() if name != "sha256"},
                    {**METADATA, "padding": "x" * 5000},
                    {**METADATA, "version_name": "\u0661.2.3"},
                    "[" * 2000 + "]" * 2000,
                ],
                ids=[
                    "not-json",
                    "not-an-object",
                    "a-version-code-that-is-a-boolean",
                    "a-version-code-of-zero",
                    "a-version-code-beyond-32-bits",
                    "a-version-code-written-as-text",
                    "a-version-without-its-patch-number",
                    "a-version-with-markup",
                    "a-version-with-a-line-end",
                    "a-version-of-65-characters",
                    "a-version-with-an-accented-letter",
                    "a-version-with-a-quote",
                    "a-version-with-empty-build-metadata",
                    "an-application-id-with-capitals",
                    "an-application-id-of-one-name",
                    "an-uppercase-sha256",
                    "a-negative-size",
                    "no-sha256",
                    "metadata-over-4096-bytes",
                    "a-version-with-an-arabic-indic-digit",
                    "json-nested-2000-deep",
                ],
            )
            def offered(self, request: pytest.FixtureRequest, tmp_path: Path) -> dict[str, object] | None:
                apk = tmp_path / "app" / "scanmylib.apk"
                publish(apk, request.param)
                return published_apk(apk)

            def test_should_offer_nothing(self, offered: dict[str, object] | None) -> None:
                assert offered is None
