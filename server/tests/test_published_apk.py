"""The published APK's metadata, relayed by /api/health."""

from __future__ import annotations

import json

import pytest

from scanmylib.published_apk import metadata_path, published_apk

SHA256 = "0123456789abcdef" * 4
APK = b"PK\x03\x04 fake apk"
METADATA = {
    "application_id": "fr.scanmylib",
    "version_name": "1.2.3",
    "version_code": 10203,
    "sha256": SHA256,
    "size": len(APK),
}


def publish(apk_path, metadata) -> None:
    apk_path.parent.mkdir(parents=True, exist_ok=True)
    apk_path.write_bytes(APK)
    text = metadata if isinstance(metadata, str) else json.dumps(metadata)
    metadata_path(apk_path).write_text(text, encoding="utf-8")


def test_health_offers_the_published_apk(client, settings):
    assert client.get("/api/health").json()["apk"] is None
    publish(settings.apk_path, METADATA)
    assert client.get("/api/health").json()["apk"] == {
        "application_id": "fr.scanmylib",
        "version": "1.2.3",
        "version_code": 10203,
        "sha256": SHA256,
        "size": len(APK),
        "path": "/download/scanmylib.apk",
    }


@pytest.mark.parametrize(
    "version",
    # The last one, 64 characters, the longest accepted.
    ["0.3.0", "0.2.4-dev.27+g1a2b3c4d5e6f", "0.2.4-dev+g1a2b3c4d5e6f.dirty", "0.2.4-dev", "0.2.4-dev+g" + "a" * 53],
)
def test_releases_and_development_builds_are_offered(tmp_path, version):
    apk = tmp_path / "app" / "scanmylib.apk"
    publish(apk, {**METADATA, "version_name": version})
    assert published_apk(apk)["version"] == version


def test_no_apk_or_no_metadata_offers_nothing(tmp_path):
    apk = tmp_path / "app" / "scanmylib.apk"
    assert published_apk(apk) is None
    publish(apk, METADATA)
    apk.unlink()
    assert published_apk(apk) is None
    publish(apk, METADATA)
    metadata_path(apk).unlink()
    assert published_apk(apk) is None


def test_metadata_of_another_apk_offers_nothing(tmp_path):
    # An APK published without its metadata (a build from before it, or cut short) leaves the
    # previous APK's: the app would download a file that fails its check.
    apk = tmp_path / "app" / "scanmylib.apk"
    publish(apk, METADATA)
    apk.write_bytes(APK + b" rebuilt")
    assert published_apk(apk) is None


@pytest.mark.parametrize(
    "metadata",
    [
        "not json",
        "[1, 2]",
        "\udcff",
        {**METADATA, "version_code": True},
        {**METADATA, "version_code": 0},
        {**METADATA, "version_code": 2**31},
        {**METADATA, "version_code": "10203"},
        {**METADATA, "version_name": "1.2"},
        {**METADATA, "version_name": "1.2.3<script>"},
        {**METADATA, "version_name": "1.2.3-dev\n"},
        {**METADATA, "version_name": "0.2.4-dev+g" + "a" * 54},  # 65 characters
        {**METADATA, "version_name": "1.2.3-dév"},
        {**METADATA, "version_name": '1.2.3-dev"x'},
        {**METADATA, "version_name": "1.2.3+"},
        {**METADATA, "application_id": "Fr.Scanmylib"},
        {**METADATA, "application_id": "scanmylib"},
        {**METADATA, "sha256": SHA256.upper()},
        {**METADATA, "size": -1},
        {key: value for key, value in METADATA.items() if key != "sha256"},
        {**METADATA, "padding": "x" * 5000},
        {**METADATA, "version_name": "\u0661.2.3"},
        "[" * 2000 + "]" * 2000,
    ],
)
def test_metadata_that_does_not_hold_up_offers_nothing(tmp_path, metadata):
    apk = tmp_path / "app" / "scanmylib.apk"
    if metadata == "\udcff":
        apk.parent.mkdir(parents=True)
        apk.write_bytes(b"PK")
        metadata_path(apk).write_bytes(b"\xff\xfe{")
    else:
        publish(apk, metadata)
    assert published_apk(apk) is None
