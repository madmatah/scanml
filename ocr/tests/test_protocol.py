"""The channel of the protocol between the supervisor and the worker (ocr/scanmylib_ocr/protocol.py).

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import functools
import os
import select
import unittest
from contextlib import suppress
from unittest import mock

from scanmylib_ocr import protocol
from scanmylib_ocr.protocol import Channel

LIMIT_BYTES = 1024
OVERSIZED_MESSAGE = {"result": "x" * 4096}


def has_bytes_waiting(read_end: int) -> bool:
    readable_ends, _, _ = select.select([read_end], [], [], 0)
    return readable_ends == [read_end]


class _TheSendMethodWhenTheMessageIsLargerThanTheLimit(unittest.TestCase):
    def setUp(self) -> None:
        to_worker_read_end, to_worker_write_end = os.pipe()
        self.from_worker_read_end, from_worker_write_end = os.pipe()
        worker_channel = Channel(to_worker_read_end, from_worker_write_end)
        self.addCleanup(worker_channel.close)
        supervisor_channel = Channel(self.from_worker_read_end, to_worker_write_end)
        self.addCleanup(supervisor_channel.close)
        limit_patcher = mock.patch.object(protocol, "MAX_MESSAGE_BYTES", LIMIT_BYTES)
        limit_patcher.start()
        self.addCleanup(limit_patcher.stop)
        self.send_oversized_message = functools.partial(worker_channel.send, OVERSIZED_MESSAGE)


class TheSendMethodWhenTheMessageIsLargerThanTheLimit(_TheSendMethodWhenTheMessageIsLargerThanTheLimit):
    def test_should_refuse_it(self) -> None:
        self.assertRaisesRegex(ValueError, f"larger than {LIMIT_BYTES}", self.send_oversized_message)


class TheSendMethodWhenTheMessageIsLargerThanTheLimitWhenItIsRefused(_TheSendMethodWhenTheMessageIsLargerThanTheLimit):
    def setUp(self) -> None:
        super().setUp()
        with suppress(ValueError):
            self.send_oversized_message()
        self.has_bytes_for_the_supervisor = has_bytes_waiting(self.from_worker_read_end)

    def test_should_write_nothing_so_that_the_supervisor_never_reads_part_of_a_message(self) -> None:
        self.assertFalse(self.has_bytes_for_the_supervisor)


if __name__ == "__main__":
    unittest.main()
