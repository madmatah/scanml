"""The web sessions in SQLite (adapters/sqlite/web_sessions.py): when a stored session is valid, which one a removal
ends, and which sessions are forgotten as ended."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scanmylib.adapters.sqlite.database import Database
from scanmylib.adapters.sqlite.web_sessions import SqliteWebSessions

SESSION_ID_HASH = "hash-of-a-session-id"
OTHER_SESSION_ID_HASH = "hash-of-another-session-id"
TOKEN_FINGERPRINT = "fingerprint-of-the-token"
OTHER_TOKEN_FINGERPRINT = "fingerprint-of-another-token"
OPENED_AT = datetime.fromisoformat("2026-10-12T20:00:00+02:00")
EXPIRES_AT = OPENED_AT + timedelta(days=365)
ONE_SECOND = timedelta(seconds=1)
FORGOTTEN_AT = OPENED_AT + timedelta(days=30)
CURRENT_SESSION_ID_HASH = "hash-of-a-current-session-id"
EXPIRED_SESSION_ID_HASH = "hash-of-an-expired-session-id"
OTHER_TOKEN_SESSION_ID_HASH = "hash-of-the-session-id-of-another-token"


@dataclass(frozen=True)
class SessionsAfterRemoval:
    is_removed_session_valid: bool
    is_other_session_valid: bool


@dataclass(frozen=True)
class SessionsAfterForgetting:
    is_current_session_valid: bool
    is_expired_session_valid: bool
    is_other_token_session_valid: bool


class TestTheSqliteWebSessions:
    class TestTheIsValidMethod:
        class TestWhenItsSessionWasAddedUnderTheTokenAndExpiresLater:
            @pytest.fixture
            def is_valid(self, tmp_path: Path) -> bool:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    web_sessions = SqliteWebSessions(database)
                    web_sessions.add(SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT, EXPIRES_AT)
                    return web_sessions.is_valid(SESSION_ID_HASH, TOKEN_FINGERPRINT, EXPIRES_AT - ONE_SECOND)

            def test_should_say_it_is(self, is_valid: bool) -> None:
                assert is_valid is True

        class TestWhenItIsAskedUnderAnotherToken:
            @pytest.fixture
            def is_valid(self, tmp_path: Path) -> bool:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    web_sessions = SqliteWebSessions(database)
                    web_sessions.add(SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT, EXPIRES_AT)
                    return web_sessions.is_valid(SESSION_ID_HASH, OTHER_TOKEN_FINGERPRINT, EXPIRES_AT - ONE_SECOND)

            def test_should_say_it_is_not_since_a_session_holds_under_its_own_token_only(self, is_valid: bool) -> None:
                assert is_valid is False

        class TestWhenItIsAskedAtTheMomentItsSessionExpires:
            @pytest.fixture
            def is_valid(self, tmp_path: Path) -> bool:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    web_sessions = SqliteWebSessions(database)
                    web_sessions.add(SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT, EXPIRES_AT)
                    return web_sessions.is_valid(SESSION_ID_HASH, TOKEN_FINGERPRINT, EXPIRES_AT)

            def test_should_say_it_is_not(self, is_valid: bool) -> None:
                assert is_valid is False

        class TestWhenAnotherIdHashIsAskedWhileASessionIsStored:
            @pytest.fixture
            def is_valid(self, tmp_path: Path) -> bool:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    web_sessions = SqliteWebSessions(database)
                    web_sessions.add(SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT, EXPIRES_AT)
                    return web_sessions.is_valid(OTHER_SESSION_ID_HASH, TOKEN_FINGERPRINT, EXPIRES_AT - ONE_SECOND)

            def test_should_say_it_is_not_since_a_session_holds_for_its_own_id_only(self, is_valid: bool) -> None:
                assert is_valid is False

    class TestTheRemoveMethod:
        class TestWhenOneOfTwoSessionsIsRemoved:
            @pytest.fixture
            def sessions_after_removal(self, tmp_path: Path) -> SessionsAfterRemoval:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    web_sessions = SqliteWebSessions(database)
                    web_sessions.add(SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT, EXPIRES_AT)
                    web_sessions.add(OTHER_SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT, EXPIRES_AT)
                    web_sessions.remove(SESSION_ID_HASH)
                    return SessionsAfterRemoval(
                        is_removed_session_valid=web_sessions.is_valid(
                            SESSION_ID_HASH, TOKEN_FINGERPRINT, EXPIRES_AT - ONE_SECOND
                        ),
                        is_other_session_valid=web_sessions.is_valid(
                            OTHER_SESSION_ID_HASH, TOKEN_FINGERPRINT, EXPIRES_AT - ONE_SECOND
                        ),
                    )

            def test_should_end_the_removed_one(self, sessions_after_removal: SessionsAfterRemoval) -> None:
                assert sessions_after_removal.is_removed_session_valid is False

            def test_should_keep_the_other(self, sessions_after_removal: SessionsAfterRemoval) -> None:
                assert sessions_after_removal.is_other_session_valid is True

    class TestTheForgetEndedMethod:
        class TestWhenSessionsExpiredOrBelongToAnotherToken:
            @pytest.fixture
            def sessions_after_forgetting(self, tmp_path: Path) -> SessionsAfterForgetting:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    web_sessions = SqliteWebSessions(database)
                    web_sessions.add(CURRENT_SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT, EXPIRES_AT)
                    web_sessions.add(EXPIRED_SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT, FORGOTTEN_AT - ONE_SECOND)
                    web_sessions.add(OTHER_TOKEN_SESSION_ID_HASH, OTHER_TOKEN_FINGERPRINT, OPENED_AT, EXPIRES_AT)
                    web_sessions.forget_ended(TOKEN_FINGERPRINT, FORGOTTEN_AT)
                    return SessionsAfterForgetting(
                        is_current_session_valid=web_sessions.is_valid(
                            CURRENT_SESSION_ID_HASH, TOKEN_FINGERPRINT, FORGOTTEN_AT
                        ),
                        is_expired_session_valid=web_sessions.is_valid(
                            EXPIRED_SESSION_ID_HASH, TOKEN_FINGERPRINT, OPENED_AT
                        ),
                        is_other_token_session_valid=web_sessions.is_valid(
                            OTHER_TOKEN_SESSION_ID_HASH, OTHER_TOKEN_FINGERPRINT, FORGOTTEN_AT
                        ),
                    )

            def test_should_keep_a_session_of_the_token_that_expires_later(
                self, sessions_after_forgetting: SessionsAfterForgetting
            ) -> None:
                assert sessions_after_forgetting.is_current_session_valid is True

            def test_should_forget_one_that_expired_before_the_moment(
                self, sessions_after_forgetting: SessionsAfterForgetting
            ) -> None:
                assert sessions_after_forgetting.is_expired_session_valid is False

            def test_should_forget_one_of_another_token(
                self, sessions_after_forgetting: SessionsAfterForgetting
            ) -> None:
                assert sessions_after_forgetting.is_other_token_session_valid is False
