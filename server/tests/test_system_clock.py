"""The system clock (adapters/system_clock.py): the moment the api reads."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

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

        class TestWhenTheTimeZoneIsAFormerAliasSuchAsUsEastern:
            former_zone_name = "US/Eastern"
            eastern_offsets = (timedelta(hours=-5), timedelta(hours=-4))

            @pytest.fixture
            def moment(self, request: pytest.FixtureRequest) -> datetime:
                request.addfinalizer(time.tzset)
                with pytest.MonkeyPatch.context() as environment:
                    environment.setenv("TZ", self.former_zone_name)
                    time.tzset()
                    return SystemClock().now()

            def test_should_give_the_offset_of_eastern_time_so_that_a_former_name_never_falls_back_to_utc(
                self, moment: datetime
            ) -> None:
                assert moment.utcoffset() in self.eastern_offsets
