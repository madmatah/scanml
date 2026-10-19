"""Database schema: creation, and in-place upgrade of a database made by an older api."""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from fastapi.testclient import TestClient

from scanmylib import db as db_module
from scanmylib.app import create_app
from scanmylib.config import Settings
from scanmylib.db import SCHEMA_VERSION, Database
from scanmylib.devtools.fake_ocr import FakeOcrServer
from support import AUTH, TOKEN

# The schema of version 1, as created by the api before manual page order (verbatim).
VERSION_1_SCHEMA = """
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


class Version1Page(NamedTuple):
    id: str
    seq: int
    detected_numbers: list[str]
    manual_number: int | None
    number: int | None
    in_document: int
    position: int


VERSION_1_PAGES = [
    Version1Page("0a000000-0000-4000-8000-000000000000", 0, [], None, None, 1, 3),
    Version1Page("0a000000-0000-4000-8000-000000000001", 1, ["1"], None, 1, 1, 0),
    Version1Page("0a000000-0000-4000-8000-000000000002", 2, ["2"], None, 2, 1, 1),
    Version1Page("0a000000-0000-4000-8000-000000000003", 3, [], 3, 3, 1, 2),
]
TITLE_PAGE, PAGE_1, PAGE_2, PAGE_3 = (page.id for page in VERSION_1_PAGES)


def make_key(seq: int, page_id: str) -> str:
    return f"20261012-20000{seq}_{page_id[:8]}"


def make_version_1_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(f"BEGIN IMMEDIATE; {VERSION_1_SCHEMA} PRAGMA user_version = 1; COMMIT;")
        layout = {
            "stats": {"pages": 4, "done": 4},
            "coverage": {"ranges": [[1, 3]], "unnumbered": 1},
            "cover_page_id": PAGE_1,
            "pages_in_document": 4,
        }
        connection.execute(
            "INSERT INTO documents (id, slug, title, author, kind, notes, unwarp, created_at, updated_at,"
            " updated_ts, layout) VALUES (?, 'sample-cafe-guide', 'Sample Café Guide', 'Jane Doe', 'book',"
            " '', 1, '2026-10-12T20:00:00+02:00', '2026-10-12T20:10:00+02:00', 1792000000.0, ?)",
            (DOCUMENT_ID, json.dumps(layout)),
        )
        ocr = {
            "engine": "paddleocr-vl-1.6",
            "model": "PaddleOCR-VL-1.6",
            "duration_s": 2.1,
            "at": "2026-10-12T20:05:00+02:00",
            "images": 0,
            "chars": 1200,
        }
        for page_id, seq, detected, manual, number, in_document, position in VERSION_1_PAGES:
            connection.execute(
                "INSERT INTO pages (id, document_id, key, scan_ext, session_id, seq, captured_at, captured_ts,"
                " uploaded_at, uploaded_ts, width, height, status, manual_number, detected_numbers, ocr,"
                " number, number_source, page_label, in_document, position)"
                " VALUES (?, ?, ?, 'jpg', ?, ?, ?, ?, ?, ?, 1200, 1600, 'done', ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    page_id,
                    DOCUMENT_ID,
                    make_key(seq, page_id),
                    SESSION_ID,
                    seq,
                    f"2026-10-12T20:00:0{seq}+02:00",
                    1792000000.0 + seq,
                    "2026-10-12T20:01:00+02:00",
                    1792000060.0 + seq,
                    manual,
                    json.dumps(detected),
                    json.dumps(ocr),
                    number,
                    None if number is None else ("manual" if manual else "detected"),
                    None if number is None else str(number),
                    in_document,
                    position,
                ),
            )


def read_user_version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as connection:
        version: int = connection.execute("PRAGMA user_version").fetchone()[0]
        return version


def read_columns_and_indexes(path: Path) -> dict[str, tuple[set[tuple[object, ...]], set[tuple[object, ...]]]]:
    with closing(sqlite3.connect(path)) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {
            table: (
                {row[1:] for row in connection.execute(f"PRAGMA table_info({table})")},
                {
                    (
                        index[1],
                        index[2],
                        tuple(column[2] for column in connection.execute(f"PRAGMA index_info({index[1]})")),
                    )
                    for index in connection.execute(f"PRAGMA index_list({table})")
                },
            )
            for table in tables
        }


class UpgradedDatabase(NamedTuple):
    path: Path
    fresh_path: Path
    backup_path: Path


class Opening(NamedTuple):
    path: Path
    schema_version: int
    open_the_database: Callable[[], object]


def read_page_rows(path: Path) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(
            "SELECT id, seq, detected_numbers, manual_number, number, in_document, rank, position, placement"
            " FROM pages ORDER BY id"
        ).fetchall()


def read_document_titles(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as connection:
        return [row[0] for row in connection.execute("SELECT title FROM documents")]


def read_page_ids_and_positions(path: Path) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT id, position FROM pages ORDER BY id").fetchall()


def read_page_columns(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        return {row[1] for row in connection.execute("PRAGMA table_info(pages)")}


def write_schema_version(path: Path, version: int) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(f"PRAGMA user_version = {version}")


class Reordered(NamedTuple):
    status_code: int
    text: str


class ApiRun(NamedTuple):
    document: dict[str, Any]
    reordered: Reordered
    markdown: str
    schema_version: int


@pytest.fixture(scope="module")
def api_on_a_version_1_database(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> ApiRun:
    # The settings of conftest.py, whose fixtures serve a single test. Unix socket paths are limited to ~107 bytes,
    # which pytest's temporary paths can exceed.
    socket_dir = Path(tempfile.mkdtemp(prefix="sml-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(socket_dir, ignore_errors=True))
    state_root = tmp_path_factory.mktemp("api")
    settings = Settings(
        library_dir=state_root / "library",
        library_host_path="/home/user/Documents/ScanMyLib",
        state_dir=state_root / "state",
        ocr_socket=socket_dir / "ocr.sock",
        public_url="http://192.168.1.10:8765",
        apk_path=state_root / "app" / "scanmylib.apk",
        web_dir=state_root / "web",
        token=TOKEN,
        assemble_delay_s=0.05,
        ocr_retry_max_s=0.2,
    )
    fake_ocr = FakeOcrServer(settings.ocr_socket)
    request.addfinalizer(fake_ocr.stop)
    fake_ocr.start()
    make_version_1_database(settings.db_path)
    with TestClient(create_app(settings)) as client:
        document: dict[str, Any] = client.get(f"/api/documents/{DOCUMENT_ID}", headers=AUTH).json()
        order = {"page_ids": [PAGE_1, TITLE_PAGE, PAGE_2, PAGE_3]}
        response = client.put(f"/api/documents/{DOCUMENT_ID}/order", json=order, headers=AUTH)
        reordered = Reordered(status_code=response.status_code, text=response.text)
        markdown = client.get(f"/api/documents/{DOCUMENT_ID}/markdown", headers=AUTH).text
    return ApiRun(
        document=document, reordered=reordered, markdown=markdown, schema_version=read_user_version(settings.db_path)
    )


class TestTheDatabase:
    class TestTheDatabaseConstructor:
        class TestWhenTheFileHoldsAVersion1Database:
            @pytest.fixture
            def upgraded_database(self, tmp_path: Path) -> UpgradedDatabase:
                path = tmp_path / "scanmylib.db"
                make_version_1_database(path)
                Database(path).close()
                fresh_path = tmp_path / "fresh.db"
                Database(fresh_path).close()
                return UpgradedDatabase(path=path, fresh_path=fresh_path, backup_path=tmp_path / "scanmylib.db.v1.bak")

            def test_should_bring_it_to_the_current_schema_version_2(self, upgraded_database: UpgradedDatabase) -> None:
                assert read_user_version(upgraded_database.path) == SCHEMA_VERSION == 2

            def test_should_give_it_the_schema_of_a_new_database(self, upgraded_database: UpgradedDatabase) -> None:
                assert read_columns_and_indexes(upgraded_database.path) == read_columns_and_indexes(
                    upgraded_database.fresh_path
                )

            def test_should_keep_the_pages_with_their_position_as_their_rank_and_no_place_chosen_by_the_user(
                self, upgraded_database: UpgradedDatabase
            ) -> None:
                assert read_page_rows(upgraded_database.path) == [
                    (page_id, seq, json.dumps(detected), manual, number, in_document, rank, None, None)
                    for page_id, seq, detected, manual, number, in_document, rank in VERSION_1_PAGES
                ]

            def test_should_keep_the_documents(self, upgraded_database: UpgradedDatabase) -> None:
                assert read_document_titles(upgraded_database.path) == ["Sample Café Guide"]

            def test_should_keep_a_copy_of_the_version_1_database_for_the_previous_api_version(
                self, upgraded_database: UpgradedDatabase
            ) -> None:
                assert read_user_version(upgraded_database.backup_path) == 1

            def test_should_keep_the_pages_of_the_copy_as_they_were(self, upgraded_database: UpgradedDatabase) -> None:
                positions = read_page_ids_and_positions(upgraded_database.backup_path)
                assert positions == [(page.id, page.position) for page in VERSION_1_PAGES]

            class TestWhenTheUpgradedDatabaseIsOpenedAgain:
                @pytest.fixture(autouse=True)
                def reopen(self, upgraded_database: UpgradedDatabase) -> None:
                    upgraded_database.backup_path.unlink()
                    Database(upgraded_database.path).close()

                def test_should_make_no_copy_since_it_is_up_to_date(self, upgraded_database: UpgradedDatabase) -> None:
                    assert not upgraded_database.backup_path.exists()

        class TestWhenTheUpgradeFails:
            @pytest.fixture
            def opening(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Opening:
                path = tmp_path / "scanmylib.db"
                make_version_1_database(path)
                failing_upgrade = "ALTER TABLE pages RENAME COLUMN position TO rank; ALTER TABLE nothing ADD COLUMN x;"
                monkeypatch.setitem(db_module._UPGRADES, 1, failing_upgrade)
                return Opening(path=path, schema_version=1, open_the_database=lambda: Database(path))

            def test_should_raise_the_error_of_sqlite(self, opening: Opening) -> None:
                with pytest.raises(sqlite3.OperationalError, match="nothing"):
                    opening.open_the_database()

            class TestWhenTheFailedUpgradeIsOver:
                @pytest.fixture(autouse=True)
                def fail_to_open(self, opening: Opening) -> None:
                    with contextlib.suppress(sqlite3.OperationalError):
                        opening.open_the_database()

                def test_should_leave_the_schema_version_at_1(self, opening: Opening) -> None:
                    assert read_user_version(opening.path) == 1

                def test_should_leave_the_columns_as_they_were_since_the_upgrade_is_one_transaction(
                    self, opening: Opening
                ) -> None:
                    columns = read_page_columns(opening.path)
                    assert ("position" in columns, "rank" in columns) == (True, False)

        class TestWhenTheFileHoldsAnUnknownSchemaVersion:
            @pytest.fixture(params=[SCHEMA_VERSION + 1, -1], ids=["a newer version", "a negative version"])
            def opening(self, request: pytest.FixtureRequest, tmp_path: Path) -> Opening:
                path = tmp_path / "scanmylib.db"
                version: int = request.param
                write_schema_version(path, version)
                return Opening(path=path, schema_version=version, open_the_database=lambda: Database(path))

            def test_should_refuse_it(self, opening: Opening) -> None:
                with pytest.raises(RuntimeError, match=f"unsupported database schema version {opening.schema_version}"):
                    opening.open_the_database()

            class TestWhenTheRefusalIsOver:
                @pytest.fixture(autouse=True)
                def fail_to_open(self, opening: Opening) -> None:
                    with contextlib.suppress(RuntimeError):
                        opening.open_the_database()

                def test_should_leave_the_schema_version_as_it_was(self, opening: Opening) -> None:
                    assert read_user_version(opening.path) == opening.schema_version

                def test_should_make_no_copy(self, opening: Opening) -> None:
                    assert list(opening.path.parent.glob("*.bak")) == []

    class TestWhenTheApiStartsOnAVersion1Database:
        def test_should_open_the_book_with_the_title_page_scanned_just_before_page_1(
            self, api_on_a_version_1_database: ApiRun
        ) -> None:
            document = api_on_a_version_1_database.document
            assert [page["id"] for page in document["pages"]] == [TITLE_PAGE, PAGE_1, PAGE_2, PAGE_3]

        def test_should_place_the_title_page_by_its_session_and_the_others_by_their_number(
            self, api_on_a_version_1_database: ApiRun
        ) -> None:
            document = api_on_a_version_1_database.document
            assert [page["placement"] for page in document["pages"]] == ["session", "number", "number", "number"]

        def test_should_give_no_page_a_place_chosen_by_the_user(self, api_on_a_version_1_database: ApiRun) -> None:
            document = api_on_a_version_1_database.document
            assert [page["position"] for page in document["pages"]] == [None] * 4

        def test_should_keep_the_labels_of_the_pages(self, api_on_a_version_1_database: ApiRun) -> None:
            document = api_on_a_version_1_database.document
            assert [page["page_label"] for page in document["pages"]] == [None, "1", "2", "3"]

        def test_should_keep_the_coverage(self, api_on_a_version_1_database: ApiRun) -> None:
            assert api_on_a_version_1_database.document["coverage"]["label"] == "1–3"

        def test_should_take_the_first_page_as_the_cover(self, api_on_a_version_1_database: ApiRun) -> None:
            assert api_on_a_version_1_database.document["cover_thumb_url"] == f"/api/pages/{TITLE_PAGE}/thumb"

        class TestWhenTheUserMovesTheTitlePageAfterPage1:
            def test_should_accept_the_order(self, api_on_a_version_1_database: ApiRun) -> None:
                reordered = api_on_a_version_1_database.reordered
                assert reordered.status_code == 200, reordered.text

            def test_should_give_a_position_to_the_title_page_only(self, api_on_a_version_1_database: ApiRun) -> None:
                pages = json.loads(api_on_a_version_1_database.reordered.text)["pages"]
                assert [(page["id"], page["position"]) for page in pages] == [
                    (PAGE_1, None),
                    (TITLE_PAGE, 1.5),
                    (PAGE_2, None),
                    (PAGE_3, None),
                ]

            class TestWhenTheDocumentMarkdownIsRead:
                def test_should_write_the_pages_in_the_new_order(self, api_on_a_version_1_database: ApiRun) -> None:
                    keys = {page_id: make_key(seq, page_id) for page_id, seq, *_ in VERSION_1_PAGES}
                    assert re.findall(r"scan (\S+) -->", api_on_a_version_1_database.markdown) == [
                        keys[PAGE_1],
                        keys[TITLE_PAGE],
                        keys[PAGE_2],
                        keys[PAGE_3],
                    ]

                class TestWhenTheApiStops:
                    def test_should_leave_the_database_at_the_current_schema_version(
                        self, api_on_a_version_1_database: ApiRun
                    ) -> None:
                        assert api_on_a_version_1_database.schema_version == SCHEMA_VERSION
