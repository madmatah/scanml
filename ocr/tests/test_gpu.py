"""The GPU monitor (ocr/scanmylib_ocr/gpu.py), with nvidia-smi replaced by a counter of its queries, and the clock by
one that the tests set.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import itertools
import time
import unittest
from dataclasses import dataclass
from typing import Any
from unittest import mock

from scanmylib_ocr import gpu

MAX_AGE_SECONDS = 5.0
SYNC_AFTER_SECONDS = 30.0
FIRST_READING = {"memory_used_mb": 1}
SECOND_READING = {"memory_used_mb": 2}
RECENT_AGE_SECONDS = 1.0
SLIGHTLY_OLD_AGE_SECONDS = 10.0
LONG_PAUSE_SECONDS = 60.0
# The background refresh stores its reading in a thread of its own, shortly after the query returns.
BACKGROUND_REFRESH_TIMEOUT_SECONDS = 10.0


class ManualClock:
    def __init__(self) -> None:
        self.now_seconds = 0.0

    def monotonic(self) -> float:
        return self.now_seconds


@dataclass(frozen=True)
class MonitoredGpu:
    monitor: gpu.GpuMonitor
    clock: ManualClock
    query: mock.MagicMock


def start_monitoring(test: unittest.TestCase) -> MonitoredGpu:
    query_numbers = itertools.count(1)
    query_patcher = mock.patch.object(gpu, "query_gpu", side_effect=lambda: {"memory_used_mb": next(query_numbers)})
    query = query_patcher.start()
    test.addCleanup(query_patcher.stop)
    clock = ManualClock()
    clock_patcher = mock.patch.object(gpu, "time", clock)
    clock_patcher.start()
    test.addCleanup(clock_patcher.stop)
    monitor = gpu.GpuMonitor(max_age_s=MAX_AGE_SECONDS, sync_after_s=SYNC_AFTER_SECONDS)
    return MonitoredGpu(monitor, clock, query)


def wait_for_another_reading(monitor: gpu.GpuMonitor, served_reading: dict[str, Any] | None) -> dict[str, Any] | None:
    deadline_seconds = time.monotonic() + BACKGROUND_REFRESH_TIMEOUT_SECONDS
    reading = monitor.current()
    while reading == served_reading and time.monotonic() < deadline_seconds:
        time.sleep(0.01)
        reading = monitor.current()
    return reading


class TheCurrentMethodWhenNoReadingWasTakenYet(unittest.TestCase):
    def setUp(self) -> None:
        monitored_gpu = start_monitoring(self)
        self.reading = monitored_gpu.monitor.current()

    def test_should_take_a_reading_on_the_spot(self) -> None:
        self.assertEqual(self.reading, FIRST_READING)


class TheCurrentMethodWhenTheReadingIsRecent(unittest.TestCase):
    def setUp(self) -> None:
        monitored_gpu = start_monitoring(self)
        monitored_gpu.monitor.current()
        self.reading = monitored_gpu.monitor.current()
        self.query_count = monitored_gpu.query.call_count

    def test_should_return_the_same_reading(self) -> None:
        self.assertEqual(self.reading, FIRST_READING)

    def test_should_not_query_the_gpu_again_so_that_frequent_pollers_never_wait_for_nvidia_smi(self) -> None:
        self.assertEqual(self.query_count, 1)


class TheCurrentMethodWhenTheReadingIsSlightlyOld(unittest.TestCase):
    def setUp(self) -> None:
        monitored_gpu = start_monitoring(self)
        monitored_gpu.monitor.refresh()
        monitored_gpu.clock.now_seconds = SLIGHTLY_OLD_AGE_SECONDS
        self.served_reading = monitored_gpu.monitor.current()
        self.refreshed_reading = wait_for_another_reading(monitored_gpu.monitor, self.served_reading)

    def test_should_serve_it_without_waiting_for_a_new_one(self) -> None:
        self.assertEqual(self.served_reading, FIRST_READING)

    def test_should_replace_it_with_a_reading_taken_in_the_background(self) -> None:
        self.assertEqual(self.refreshed_reading, SECOND_READING)


class TheCurrentMethodWhenTheReadingIsFromBeforeALongPause(unittest.TestCase):
    def setUp(self) -> None:
        monitored_gpu = start_monitoring(self)
        monitored_gpu.monitor.refresh()
        monitored_gpu.clock.now_seconds = LONG_PAUSE_SECONDS
        self.reading = monitored_gpu.monitor.current()

    def test_should_take_a_new_reading_on_the_spot_rather_than_serve_one_that_old(self) -> None:
        self.assertEqual(self.reading, SECOND_READING)


class TheCurrentMethodWhenTheEngineChangedStateBeforeTheReading(unittest.TestCase):
    def setUp(self) -> None:
        monitored_gpu = start_monitoring(self)
        monitored_gpu.monitor.refresh()
        monitored_gpu.clock.now_seconds = RECENT_AGE_SECONDS
        state_changed_at_seconds = -RECENT_AGE_SECONDS
        self.reading = monitored_gpu.monitor.current(changed_at=state_changed_at_seconds)

    def test_should_return_the_reading_since_it_already_shows_the_engine_s_use_of_the_gpu(self) -> None:
        self.assertEqual(self.reading, FIRST_READING)


class TheCurrentMethodWhenTheEngineChangedStateAfterTheReading(unittest.TestCase):
    def setUp(self) -> None:
        monitored_gpu = start_monitoring(self)
        monitored_gpu.monitor.refresh()
        monitored_gpu.clock.now_seconds = RECENT_AGE_SECONDS
        state_changed_at_seconds = RECENT_AGE_SECONDS
        self.reading = monitored_gpu.monitor.current(changed_at=state_changed_at_seconds)

    def test_should_take_a_new_reading_on_the_spot_since_starting_or_stopping_the_engine_changes_the_gpu_memory_used(
        self,
    ) -> None:
        self.assertEqual(self.reading, SECOND_READING)


if __name__ == "__main__":
    unittest.main()
