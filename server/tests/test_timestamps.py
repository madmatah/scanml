"""The timestamps: moments written as text, in ISO 8601 and in the names of page keys and folders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scanmylib.domain.timestamps import compact, iso

MOMENT = datetime(2026, 10, 12, 20, 15, 30, 123456, tzinfo=timezone(timedelta(hours=2)))


class TestTheTimestamps:
    class TestTheIsoFunction:
        class TestWhenTheMomentHasMicrosecondsAndAnOffset:
            @pytest.fixture
            def text(self) -> str:
                return iso(MOMENT)

            def test_should_write_it_to_the_second_with_its_offset(self, text: str) -> None:
                assert text == "2026-10-12T20:15:30+02:00"

    class TestTheCompactFunction:
        class TestWhenTheMomentHasAnOffset:
            @pytest.fixture
            def text(self) -> str:
                return compact(MOMENT)

            def test_should_write_its_date_and_time_in_its_own_offset(self, text: str) -> None:
                assert text == "20261012-201530"
