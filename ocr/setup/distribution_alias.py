"""An alias distribution: a wheel that installs no code, under the name of one distribution, and requires another.

PaddleX requires OpenCV's GUI build by its distribution name, and checks it by that name, whatever imports: the alias
lets the engine's environment hold OpenCV's headless build instead, without editing PaddleX or its metadata. The
version comes from the exact pin of the target in our own requirements file, so the resolver refuses an alias that
does not meet PaddleX's pin, and no version read from an installed distribution ever reaches a file name.

Standard library only: `ocr/setup/install.sh` runs it by its path with the image's ``python3``, before the environment
exists. It lives with the installer, so that the image the sandbox runs does not carry it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

#: PEP 508's distribution names.
_DISTRIBUTION_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
#: PEP 440's canonical public versions, without an epoch: nothing else may reach a file name.
_CANONICAL_VERSION = re.compile(
    r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?"
    r"(?:\.post(?:0|[1-9][0-9]*))?(?:\.dev(?:0|[1-9][0-9]*))?"
)
#: pip's requirements file format: a comment starts a line, or follows a blank.
_COMMENT = re.compile(r"(?:^|\s)#.*$")
_EXACT_PIN = re.compile(r"==\s*(?P<version>\S+)\s*")
#: The wheel's timestamps, the earliest a zip file holds, so that the same alias is the same file.
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class AliasRefused(ValueError):
    pass


@dataclass(frozen=True)
class WheelFile:
    path: str
    content: bytes


@dataclass(frozen=True)
class AliasWheel:
    file_name: str
    files: tuple[WheelFile, ...]


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_exact_pin(requirements_text: str, distribution: str) -> str:
    pins = []
    for line in requirements_text.splitlines():
        requirement = _COMMENT.sub("", line).strip()
        name = _DISTRIBUTION_NAME.match(requirement)
        if name is None or normalize_name(name.group()) != normalize_name(distribution):
            continue
        pin = _EXACT_PIN.fullmatch(requirement[name.end() :].lstrip())
        if pin is None:
            raise AliasRefused(f"{distribution} is not pinned to one version with ==: {requirement}")
        pins.append(pin.group("version"))
    if len(pins) != 1:
        raise AliasRefused(f"{distribution} must be pinned once in the requirements, found {len(pins)} pins")
    version = pins[0]
    if not _CANONICAL_VERSION.fullmatch(version):
        raise AliasRefused(f"{distribution}=={version} is not a canonical public version (PEP 440)")
    return version


def build_alias_wheel(alias: str, target: str, version: str) -> AliasWheel:
    for name in (alias, target):
        if not _DISTRIBUTION_NAME.fullmatch(name):
            raise AliasRefused(f"{name!r} is not a distribution name (PEP 508)")
    if not _CANONICAL_VERSION.fullmatch(version):
        raise AliasRefused(f"{version!r} is not a canonical public version (PEP 440)")
    stem = f"{normalize_name(alias).replace('-', '_')}-{version}"
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {normalize_name(alias)}\n"
        f"Version: {version}\n"
        f"Summary: {normalize_name(target)} {version}, installed under the name {normalize_name(alias)}\n"
        f"Requires-Dist: {normalize_name(target)}=={version}\n"
    )
    wheel = "Wheel-Version: 1.0\nGenerator: scanmylib distribution_alias\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    files = (
        WheelFile(f"{stem}.dist-info/METADATA", metadata.encode()),
        WheelFile(f"{stem}.dist-info/WHEEL", wheel.encode()),
    )
    record_path = f"{stem}.dist-info/RECORD"
    record = "".join(f"{file.path},{_compute_record_hash(file.content)},{len(file.content)}\n" for file in files)
    record += f"{record_path},,\n"
    return AliasWheel(file_name=f"{stem}-py3-none-any.whl", files=(*files, WheelFile(record_path, record.encode())))


def write_wheel(wheel: AliasWheel, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / wheel.file_name
    with zipfile.ZipFile(path, "w") as archive:
        for file in wheel.files:
            archive.writestr(zipfile.ZipInfo(file.path, date_time=_ZIP_TIMESTAMP), file.content)
    return path


def _compute_record_hash(content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
    return f"sha256={digest}"


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 distribution_alias.py",
        description="Write a wheel named ALIAS that requires TARGET at its pin in REQUIREMENTS, and print its path",
    )
    parser.add_argument("--requirements", type=Path, required=True, help="the requirements file that pins TARGET")
    parser.add_argument("--alias", required=True, help="the distribution name the wheel installs")
    parser.add_argument("--target", required=True, help="the distribution the wheel requires")
    parser.add_argument("--output", type=Path, required=True, help="the directory the wheel is written to")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    try:
        version = read_exact_pin(arguments.requirements.read_text(), arguments.target)
        wheel_path = write_wheel(build_alias_wheel(arguments.alias, arguments.target, version), arguments.output)
    except (AliasRefused, OSError) as exc:
        print(f"distribution_alias: {exc}", file=sys.stderr)
        return 1
    print(wheel_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
