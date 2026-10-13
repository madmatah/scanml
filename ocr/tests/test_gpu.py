"""GPU monitor freshness rules (nvidia-smi is replaced by a counter)."""

from __future__ import annotations

import itertools
import time
import unittest
from unittest import mock

from scanmylib_ocr import gpu


class GpuMonitorTest(unittest.TestCase):
    def setUp(self) -> None:
        counter = itertools.count(1)
        patcher = mock.patch.object(gpu, "query_gpu", side_effect=lambda: {"memory_used_mb": next(counter)})
        self.query = patcher.start()
        self.addCleanup(patcher.stop)
        self.monitor = gpu.GpuMonitor(max_age_s=5.0, sync_after_s=30.0)

    def age(self, seconds: float) -> None:
        """Pretend the last reading was taken ``seconds`` ago."""
        self.monitor._taken_at = time.monotonic() - seconds

    def test_first_call_reads_on_the_spot_then_reuses_the_reading(self) -> None:
        self.assertEqual(self.monitor.current(), {"memory_used_mb": 1})
        self.assertEqual(self.monitor.current(), {"memory_used_mb": 1})
        self.assertEqual(self.query.call_count, 1)

    def test_a_slightly_old_reading_is_served_while_refreshed_in_the_background(self) -> None:
        self.monitor.refresh()
        self.age(10)
        self.assertEqual(self.monitor.current(), {"memory_used_mb": 1})
        # The background refresh stores its reading shortly after the query returns.
        deadline = time.monotonic() + 10
        while self.monitor.current() != {"memory_used_mb": 2} and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.monitor.current(), {"memory_used_mb": 2})

    def test_after_a_long_pause_the_reading_is_taken_on_the_spot(self) -> None:
        self.monitor.refresh()
        self.age(60)
        self.assertEqual(self.monitor.current(), {"memory_used_mb": 2})

    def test_a_reading_older_than_an_engine_state_change_is_replaced(self) -> None:
        self.monitor.refresh()
        self.age(1)
        self.assertEqual(self.monitor.current(changed_at=time.monotonic() - 2), {"memory_used_mb": 1})
        self.assertEqual(self.monitor.current(changed_at=time.monotonic()), {"memory_used_mb": 2})


if __name__ == "__main__":
    unittest.main()
