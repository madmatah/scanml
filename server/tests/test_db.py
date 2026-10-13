"""Database schema: creation, and in-place upgrade of a database made by an older api."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support import AUTH

from scanmylib import db as db_module
from scanmylib.app import create_app
from scanmylib.db import SCHEMA_VERSION, Database

# The schema of version 1, as created by the api before manual page order (verbatim).
V1_SCHEMA = """
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
    -- computed by ordering.compute_layout:
    number           INTEGER,
    number_end       INTEGER,
    front_matter     INTEGER NOT NULL DEFAULT 0,
    number_source    TEXT,
    page_label       TEXT,
    duplicate_of     TEXT,
    in_document      INTEGER NOT NULL DEFAULT 0,
    position         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (document_id, key)
);

CREATE INDEX pages_by_document ON pages (document_id, position);
CREATE INDEX pages_by_status ON pages (status, uploaded_ts);

CREATE TABLE sessions (
    id_hash            TEXT PRIMARY KEY,
    token_fingerprint  TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    expires_ts         REAL NOT NULL
);
"""

DOCUMENT_ID = "6f1c0000-0000-4000-8000-000000000001"
SESSION_ID = "5e550000-0000-4000-8000-000000000001"
# (id, seq, detected numbers, manual number, number, in_document, position) as the version 1 api stored them:
# the title page, scanned before page 1, had no number and came last.
V1_PAGES = [
    ("0a000000-0000-4000-8000-000000000000", 0, [], None, None, 1, 3),
    ("0a000000-0000-4000-8000-000000000001", 1, ["1"], None, 1, 1, 0),
    ("0a000000-0000-4000-8000-000000000002", 2, ["2"], None, 2, 1, 1),
    ("0a000000-0000-4000-8000-000000000003", 3, [], 3, 3, 1, 2),
]


def key(seq: int, page_id: str) -> str:
    return f"20261012-20000{seq}_{page_id[:8]}"


def make_v1_database(path: Path) -> None:
    """A database as the version 1 api left it: one book of four pages."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(f"BEGIN IMMEDIATE; {V1_SCHEMA} PRAGMA user_version = 1; COMMIT;")
        layout = {"stats": {"pages": 4, "done": 4}, "coverage": {"ranges": [[1, 3]], "unnumbered": 1},
                  "cover_page_id": V1_PAGES[1][0], "pages_in_document": 4}
        conn.execute(
            "INSERT INTO documents (id, slug, title, author, kind, notes, unwarp, created_at, updated_at,"
            " updated_ts, layout) VALUES (?, 'sample-cafe-guide', 'Sample Café Guide', 'Jane Doe', 'book',"
            " '', 1, '2026-10-12T20:00:00+02:00', '2026-10-12T20:10:00+02:00', 1792000000.0, ?)",
            (DOCUMENT_ID, json.dumps(layout)),
        )
        ocr = {"engine": "paddleocr-vl-1.6", "model": "PaddleOCR-VL-1.6", "duration_s": 2.1,
               "at": "2026-10-12T20:05:00+02:00", "images": 0, "chars": 1200}
        for page_id, seq, detected, manual, number, in_document, position in V1_PAGES:
            conn.execute(
                "INSERT INTO pages (id, document_id, key, scan_ext, session_id, seq, captured_at, captured_ts,"
                " uploaded_at, uploaded_ts, width, height, status, manual_number, detected_numbers, ocr,"
                " number, number_source, page_label, in_document, position)"
                " VALUES (?, ?, ?, 'jpg', ?, ?, ?, ?, ?, ?, 1200, 1600, 'done', ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    page_id, DOCUMENT_ID, key(seq, page_id), SESSION_ID, seq,
                    f"2026-10-12T20:00:0{seq}+02:00", 1792000000.0 + seq, "2026-10-12T20:01:00+02:00",
                    1792000060.0 + seq, manual, json.dumps(detected), json.dumps(ocr), number,
                    None if number is None else ("manual" if manual else "detected"),
                    None if number is None else str(number), in_document, position,
                ),
            )


def user_version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def schema(path: Path) -> dict:
    """Columns (without their order) and indexes of every table."""
    with closing(sqlite3.connect(path)) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {
            table: (
                {row[1:] for row in conn.execute(f"PRAGMA table_info({table})")},
                {
                    (index[1], index[2], tuple(column[2] for column in conn.execute(f"PRAGMA index_info({index[1]})")))
                    for index in conn.execute(f"PRAGMA index_list({table})")
                },
            )
            for table in tables
        }


def test_a_version_1_database_is_upgraded_in_place(tmp_path):
    path = tmp_path / "scanmylib.db"
    make_v1_database(path)
    Database(path).close()

    assert user_version(path) == SCHEMA_VERSION == 2
    Database(tmp_path / "fresh.db").close()
    assert schema(path) == schema(tmp_path / "fresh.db")
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute(
            "SELECT id, seq, detected_numbers, manual_number, number, in_document, rank, position, placement"
            " FROM pages ORDER BY id"
        ).fetchall()
        title = conn.execute("SELECT title FROM documents").fetchone()[0]
    assert rows == [
        (page_id, seq, json.dumps(detected), manual, number, in_document, rank, None, None)
        for page_id, seq, detected, manual, number, in_document, rank in V1_PAGES
    ]
    assert title == "Sample Café Guide"

    # The version 1 database is kept as it was, for the previous api version.
    backup = tmp_path / "scanmylib.db.v1.bak"
    assert user_version(backup) == 1
    with closing(sqlite3.connect(backup)) as conn:
        assert conn.execute("SELECT id, position FROM pages ORDER BY id").fetchall() == [
            (page[0], page[6]) for page in V1_PAGES
        ]
    backup.unlink()
    Database(path).close()  # already up to date: nothing to do
    assert not backup.exists()


def test_the_api_runs_on_an_upgraded_database(settings, fake_ocr):
    make_v1_database(settings.db_path)
    title, p1, p2, p3 = (page[0] for page in V1_PAGES)
    with TestClient(create_app(settings)) as client:
        document = client.get(f"/api/documents/{DOCUMENT_ID}", headers=AUTH).json()
        # The title page, scanned just before page 1, now opens the book.
        assert [p["id"] for p in document["pages"]] == [title, p1, p2, p3]
        assert [p["placement"] for p in document["pages"]] == ["session", "number", "number", "number"]
        assert [p["position"] for p in document["pages"]] == [None] * 4
        assert [p["page_label"] for p in document["pages"]] == [None, "1", "2", "3"]
        assert document["coverage"]["label"] == "1–3" and document["cover_thumb_url"] == f"/api/pages/{title}/thumb"

        moved = client.put(f"/api/documents/{DOCUMENT_ID}/order", json={"page_ids": [p1, title, p2, p3]}, headers=AUTH)
        assert moved.status_code == 200, moved.text
        assert [(p["id"], p["position"]) for p in moved.json()["pages"]] == [(p1, None), (title, 1.5), (p2, None), (p3, None)]
        markdown = client.get(f"/api/documents/{DOCUMENT_ID}/markdown", headers=AUTH).text
        keys = [key(seq, page_id) for page_id, seq, *_ in V1_PAGES]
        assert re.findall(r"scan (\S+) -->", markdown) == [keys[1], keys[0], keys[2], keys[3]]
    assert user_version(settings.db_path) == SCHEMA_VERSION


def test_a_failed_upgrade_changes_nothing(tmp_path, monkeypatch):
    path = tmp_path / "scanmylib.db"
    make_v1_database(path)
    monkeypatch.setitem(
        db_module._UPGRADES, 1, "ALTER TABLE pages RENAME COLUMN position TO rank; ALTER TABLE nothing ADD COLUMN x;"
    )
    with pytest.raises(sqlite3.OperationalError):
        Database(path)
    assert user_version(path) == 1
    with closing(sqlite3.connect(path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(pages)")}
    assert "position" in columns and "rank" not in columns


@pytest.mark.parametrize("version", [SCHEMA_VERSION + 1, -1])
def test_unknown_schema_versions_are_refused(tmp_path, version):
    path = tmp_path / "scanmylib.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(f"PRAGMA user_version = {version}")
    with pytest.raises(RuntimeError, match=f"unsupported database schema version {version}"):
        Database(path)
    assert user_version(path) == version
    assert not list(tmp_path.glob("*.bak"))
