"""Streaming zip archives (a document folder can weigh gigabytes with its scans)."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Buffer, Iterator, Sequence
from pathlib import Path

_ALREADY_COMPRESSED = {".jpg", ".png", ".webp"}
_CHUNK = 1024 * 1024


class _Sink(io.RawIOBase):
    """Write-only, non-seekable stream: zipfile then writes in streaming mode."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, data: Buffer) -> int:
        chunk = bytes(data)
        self._chunks.append(chunk)
        return len(chunk)

    def take(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def iter_zip(entries: Sequence[tuple[str, Path]]) -> Iterator[bytes]:
    """Yield a zip archive of (archive name, file) entries, chunk by chunk.

    Files that vanish while the archive is built (page deleted meanwhile) are skipped.
    """
    sink = _Sink()
    with zipfile.ZipFile(sink, "w") as archive:
        for name, path in entries:
            try:
                info = zipfile.ZipInfo.from_file(path, name)
                source = path.open("rb")
            except FileNotFoundError:
                continue
            info.compress_type = zipfile.ZIP_STORED if path.suffix in _ALREADY_COMPRESSED else zipfile.ZIP_DEFLATED
            with source, archive.open(info, "w") as target:
                while chunk := source.read(_CHUNK):
                    target.write(chunk)
                    if data := sink.take():
                        yield data
            if data := sink.take():
                yield data
    yield sink.take()
