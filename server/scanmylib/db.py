"""SQLite state of the api (STATE_DIR/scanmylib.db): documents, pages, web sessions.

The connection is only used from the event loop thread (sqlite3 enforces
it), and no coroutine awaits inside a transaction, so every transaction is
atomic with respect to the other coroutines.

A database of an older schema version is upgraded in place when the api
starts, after a copy of it is saved next to it (``scanmylib.db.v<N>.bak``).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE documents (
    id          TEXT PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL CHECK (kind IN ('book', 'document')),
    notes       TEXT NOT NULL DEFAULT '',
    unwarp      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    updated_ts  REAL NOT NULL,
    -- computed from the pages by ordering.compute_layout (JSON):
    -- {"stats": {...}, "coverage": {...}, "cover_page_id": ..., "pages_in_document": n}
    layout      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE pages (
    id               TEXT PRIMARY KEY,
    document_id      TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    key              TEXT NOT NULL,
    scan_ext         TEXT NOT NULL,
    session_id       TEXT,
    seq              INTEGER,
    captured_at      TEXT NOT NULL,
    captured_ts      REAL NOT NULL,
    uploaded_at      TEXT NOT NULL,
    uploaded_ts      REAL NOT NULL,
    width            INTEGER NOT NULL,
    height           INTEGER NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'done', 'error')),
    error            TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0,
    -- bumped each time the page is queued again, so that a result computed
    -- for an outdated request (old rotation, deleted page...) is discarded
    generation       INTEGER NOT NULL DEFAULT 0,
    rotation         INTEGER NOT NULL DEFAULT 0 CHECK (rotation IN (0, 90, 180, 270)),
    excluded         INTEGER NOT NULL DEFAULT 0,
    hint_number      INTEGER,
    manual_number    INTEGER,
    detected_numbers TEXT NOT NULL DEFAULT '[]',
    ocr              TEXT,
    -- place on the number line chosen by the user (page n at n, roman front
    -- matter v at v - 10000), set by PUT /api/documents/{id}/order:
    position         REAL,
    -- computed by ordering.compute_layout:
    number           INTEGER,
    number_end       INTEGER,
    front_matter     INTEGER NOT NULL DEFAULT 0,
    number_source    TEXT,
    page_label       TEXT,
    duplicate_of     TEXT,
    in_document      INTEGER NOT NULL DEFAULT 0,
    placement        TEXT,
    rank             INTEGER NOT NULL DEFAULT 0,
    UNIQUE (document_id, key)
);

CREATE INDEX pages_by_document ON pages (document_id, rank);
CREATE INDEX pages_by_status ON pages (status, uploaded_ts);

CREATE TABLE sessions (
    id_hash            TEXT PRIMARY KEY,
    token_fingerprint  TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    expires_ts         REAL NOT NULL
);
"""

#: Upgrade from schema version N to N + 1 (computed columns are filled by
#: LibraryService.start, which recomputes the layout of every document).
_UPGRADES = {
    # Manual page order: "position" is now the place chosen by the user, and
    # the index of a page in its document's page list is called "rank".
    1: """
ALTER TABLE pages RENAME COLUMN position TO rank;
ALTER TABLE pages ADD COLUMN position REAL;
ALTER TABLE pages ADD COLUMN placement TEXT;
""",
}


class Database:
    """Thin wrapper around one sqlite3 connection."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._conn = sqlite3.connect(path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        try:
            self._migrate()
        except BaseException:
            self._conn.close()
            raise

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        backup: Path | None = None
        if version == 0:
            script = _SCHEMA
        elif 0 < version < SCHEMA_VERSION and all(step in _UPGRADES for step in range(version, SCHEMA_VERSION)):
            backup = self._backup(version)
            script = "".join(_UPGRADES[step] for step in range(version, SCHEMA_VERSION))
        else:
            raise RuntimeError(f"unsupported database schema version {version}")
        # DDL is transactional in SQLite: the schema is created or upgraded entirely or not at all.
        try:
            self._conn.executescript(f"BEGIN IMMEDIATE; {script} PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;")
        except BaseException:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        if backup is not None:
            log.info(
                "database upgraded from schema version %d to %d, previous version saved as %s",
                version,
                SCHEMA_VERSION,
                backup,
            )

    def _backup(self, version: int) -> Path:
        """Copy the database before upgrading it: the previous api version can still use the copy."""
        target = self._path.with_name(f"{self._path.name}.v{version}.bak")
        with closing(sqlite3.connect(target)) as copy:
            self._conn.backup(copy)
        return target

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """A write transaction; nested uses join the outer one."""
        if self._conn.in_transaction:
            yield
            return
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    def all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        self._conn.close()
