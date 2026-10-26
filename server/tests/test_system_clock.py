"""The system clock (adapters/system_clock.py): the moment the api reads."""

from __future__ import annotations

from datetime import datetime

import pytest

from scanmylib.adapters.system_clock import SystemClock


class TestTheSystemClock:
    class TestTheNowMethod:
        class TestWhenItIsRead:
            @pytest.fixture
            def moment(self) -> datetime:
                return SystemClock().now()

            def test_should_give_the_moment_with_its_offset_so_that_every_time_the_api_writes_names_its_zone(
                self, moment: datetime
            ) -> None:
                assert moment.utcoffset() is not None
