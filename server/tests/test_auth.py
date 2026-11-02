"""The authenticator (auth.py): the token it requires, and the web sessions it opens, stores and ends."""

from __future__ import annotations

import contextlib
import functools
import hashlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scanmylib.adapters.sqlite.database import Database
from scanmylib.auth import Authenticator
from support import TOKEN, FixedClock

OPENED_AT = datetime.fromisoformat("2026-10-12T20:00:00+02:00")
ONE_YEAR = timedelta(days=365)
ONE_DAY = timedelta(days=1)
ONE_SECOND = timedelta(seconds=1)
#: At least 43 characters, as a token of 32 random bytes in URL-safe base64.
SHORTEST_SESSION_ID_LENGTH = 43
TOKEN_FINGERPRINT_PREFIX = "scanmylib-token:"
FORGED_SESSION_ID = "forged-session-id-0123456789abcdefghijklmnopq"


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_stored_sessions(database: Database) -> list[tuple[str, str]]:
    rows = database.all("SELECT id_hash, token_fingerprint FROM sessions")
    return [(row["id_hash"], row["token_fingerprint"]) for row in rows]


@dataclass(frozen=True)
class OpenedSession:
    session_id: str
    stored_sessions: list[tuple[str, str]]


@dataclass(frozen=True)
class SessionsAfterClosing:
    is_closed_session_open: bool
    is_other_session_open: bool


class AdjustableClock:
    _moment: datetime

    def __init__(self, moment: datetime) -> None:
        self.move_to(moment)

    def now(self) -> datetime:
        return self._moment

    def move_to(self, moment: datetime) -> None:
        if moment.utcoffset() is None:
            raise ValueError("an adjustable clock needs a moment with its offset")
        self._moment = moment


class TestTheAuthenticator:
    class TestTheConstructor:
        class TestWhenItIsGivenAnEmptyToken:
            @pytest.fixture
            def create_authenticator(self, tmp_path: Path) -> Iterator[Callable[[], Authenticator]]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    yield functools.partial(Authenticator, "", database, FixedClock(OPENED_AT))

            def test_should_refuse_it_so_that_an_empty_login_never_opens_a_session(
                self, create_authenticator: Callable[[], Authenticator]
            ) -> None:
                with pytest.raises(ValueError, match="empty API token"):
                    create_authenticator()

    class TestTheOpenSessionMethod:
        class TestWhenASessionIsOpened:
            @pytest.fixture
            def opened_session(self, tmp_path: Path) -> OpenedSession:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    session_id = Authenticator(TOKEN, database, FixedClock(OPENED_AT)).open_session()
                    return OpenedSession(session_id, read_stored_sessions(database))

            def test_should_give_it_an_id_of_at_least_43_characters_as_hard_to_guess_as_the_token(
                self, opened_session: OpenedSession
            ) -> None:
                assert len(opened_session.session_id) >= SHORTEST_SESSION_ID_LENGTH

            def test_should_store_the_hash_of_its_id_and_never_the_id(self, opened_session: OpenedSession) -> None:
                assert [id_hash for id_hash, _ in opened_session.stored_sessions] == [
                    compute_sha256(opened_session.session_id)
                ]

            def test_should_store_the_fingerprint_of_the_token_in_the_form_of_the_sessions_already_stored(
                self, opened_session: OpenedSession
            ) -> None:
                assert [token_fingerprint for _, token_fingerprint in opened_session.stored_sessions] == [
                    compute_sha256(TOKEN_FINGERPRINT_PREFIX + TOKEN)
                ]

    class TestTheCloseSessionMethod:
        class TestWhenOneOfTwoSessionsIsClosed:
            @pytest.fixture
            def sessions_after_closing(self, tmp_path: Path) -> SessionsAfterClosing:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    authenticator = Authenticator(TOKEN, database, FixedClock(OPENED_AT))
                    closed_session_id = authenticator.open_session()
                    other_session_id = authenticator.open_session()
                    authenticator.close_session(closed_session_id)
                    return SessionsAfterClosing(
                        is_closed_session_open=authenticator.session_valid(closed_session_id),
                        is_other_session_open=authenticator.session_valid(other_session_id),
                    )

            def test_should_end_it(self, sessions_after_closing: SessionsAfterClosing) -> None:
                assert sessions_after_closing.is_closed_session_open is False

            def test_should_keep_the_other_open(self, sessions_after_closing: SessionsAfterClosing) -> None:
                assert sessions_after_closing.is_other_session_open is True

    class TestTheSessionValidMethod:
        class TestWhenItsSessionOpenedJustUnderAYearAgo:
            @pytest.fixture
            def is_open(self, tmp_path: Path) -> bool:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    clock = AdjustableClock(OPENED_AT)
                    authenticator = Authenticator(TOKEN, database, clock)
                    session_id = authenticator.open_session()
                    clock.move_to(OPENED_AT + ONE_YEAR - ONE_SECOND)
                    return authenticator.session_valid(session_id)

            def test_should_hold_it_open(self, is_open: bool) -> None:
                assert is_open is True

        class TestWhenItsSessionOpenedAYearAgo:
            @pytest.fixture
            def is_open(self, tmp_path: Path) -> bool:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    clock = AdjustableClock(OPENED_AT)
                    authenticator = Authenticator(TOKEN, database, clock)
                    session_id = authenticator.open_session()
                    clock.move_to(OPENED_AT + ONE_YEAR)
                    return authenticator.session_valid(session_id)

            def test_should_end_it_a_year_after_it_opened(self, is_open: bool) -> None:
                assert is_open is False

        class TestWhenAnotherIdIsGivenWhileASessionIsOpen:
            @pytest.fixture
            def is_open(self, tmp_path: Path) -> bool:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    authenticator = Authenticator(TOKEN, database, FixedClock(OPENED_AT))
                    authenticator.open_session()
                    return authenticator.session_valid(FORGED_SESSION_ID)

            def test_should_refuse_it_so_that_a_forged_cookie_opens_no_session(self, is_open: bool) -> None:
                assert is_open is False

    class TestWhenTheApiStartsAgain:
        class TestWhenASessionOpenedADayBefore:
            @pytest.fixture
            def is_open(self, tmp_path: Path) -> bool:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    session_id = Authenticator(TOKEN, database, FixedClock(OPENED_AT)).open_session()
                    second = Authenticator(TOKEN, database, FixedClock(OPENED_AT + ONE_DAY))
                    return second.session_valid(session_id)

            def test_should_keep_it_open_so_that_a_restart_logs_no_one_out(self, is_open: bool) -> None:
                assert is_open is True

        class TestWhenASessionExpiredBefore:
            @pytest.fixture
            def stored_sessions(self, tmp_path: Path) -> list[tuple[str, str]]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    Authenticator(TOKEN, database, FixedClock(OPENED_AT)).open_session()
                    Authenticator(TOKEN, database, FixedClock(OPENED_AT + ONE_YEAR + ONE_DAY))
                    return read_stored_sessions(database)

            def test_should_forget_it(self, stored_sessions: list[tuple[str, str]]) -> None:
                assert stored_sessions == []
