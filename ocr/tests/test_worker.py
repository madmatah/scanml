"""The worker that parses pages for the supervisor (ocr/scanmylib_ocr/worker.py), with an engine of the tests.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import contextlib
import logging
import os
import unittest
from collections.abc import Iterator
from typing import Any
from unittest import mock

from scanmylib_ocr import protocol, worker
from scanmylib_ocr.engines.base import PageEngine, PageOptions, PageResult
from scanmylib_ocr.protocol import Channel

JOB_ID = "job-1"
LIMIT_BYTES = 1024


class HugeResultEngine(PageEngine):
    def load(self) -> None:
        pass

    def parse(self, image_path: str, options: PageOptions) -> PageResult:
        return {
            "width": 1000,
            "height": 1400,
            "markdown": "x" * 4 * LIMIT_BYTES,
            "images": [],
            "blocks": [],
            "page_numbers": [],
            "page_continuation": None,
            "preprocess": {},
        }


class LogRecorder(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextlib.contextmanager
def record_logs(logger_name: str, level: int) -> Iterator[list[logging.LogRecord]]:
    logger = logging.getLogger(logger_name)
    recorder = LogRecorder()
    previous_handlers, previous_level, previous_propagate = logger.handlers, logger.level, logger.propagate
    logger.handlers = [recorder]
    logger.setLevel(level)
    logger.propagate = False
    try:
        yield recorder.records
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def receive_reply(channel: Channel) -> dict[str, Any]:
    reply = channel.receive()
    if reply is None:
        raise EOFError("the worker closed the protocol pipe without a reply")
    return reply


class TheServeFunctionWhenAResultIsLargerThanTheProtocolLimit(unittest.TestCase):
    def setUp(self) -> None:
        to_worker_read_end, to_worker_write_end = os.pipe()
        from_worker_read_end, from_worker_write_end = os.pipe()
        worker_channel = Channel(to_worker_read_end, from_worker_write_end)
        self.addCleanup(worker_channel.close)
        supervisor_channel = Channel(from_worker_read_end, to_worker_write_end)
        self.addCleanup(supervisor_channel.close)
        limit_patcher = mock.patch.object(protocol, "MAX_MESSAGE_BYTES", LIMIT_BYTES)
        limit_patcher.start()
        self.addCleanup(limit_patcher.stop)
        supervisor_channel.send({"op": "parse", "id": JOB_ID, "image_path": "page.jpg"})
        supervisor_channel.send({"op": "shutdown"})
        with record_logs("scanmylib_ocr.worker", logging.ERROR) as records:
            worker.serve(worker_channel, HugeResultEngine())
        self.error_messages = [record.getMessage() for record in records]
        worker_channel.close()
        self.reply = receive_reply(supervisor_channel)

    def test_should_answer_the_page_with_a_processing_failure_so_that_the_supervisor_never_waits_for_it(self) -> None:
        self.assertEqual(
            (self.reply["id"], self.reply["ok"], self.reply["error"]), (JOB_ID, False, protocol.PROCESSING_FAILED)
        )

    def test_should_say_that_the_result_is_larger_than_the_limit(self) -> None:
        self.assertIn(f"larger than {LIMIT_BYTES}", self.reply["detail"])

    def test_should_log_that_it_cannot_send_the_result(self) -> None:
        self.assertIn(f"cannot send the result of page {JOB_ID}", self.error_messages)


if __name__ == "__main__":
    unittest.main()
