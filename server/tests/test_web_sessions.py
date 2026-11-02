"""A web session's rules, on plain values."""

from __future__ import annotations

from datetime import datetime

import pytest

from scanmylib.domain.web_sessions import compute_session_expiry

OPENED_AT = datetime.fromisoformat("2026-10-12T20:00:00+02:00")
A_YEAR_LATER = datetime.fromisoformat("2027-10-12T20:00:00+02:00")


class TestTheWebSessions:
    class TestTheComputeSessionExpiryFunction:
        class TestWhenASessionOpens:
            @pytest.fixture
            def expiry(self) -> datetime:
                return compute_session_expiry(OPENED_AT)

            def test_should_end_it_365_days_after_it_opened(self, expiry: datetime) -> None:
                assert expiry == A_YEAR_LATER
