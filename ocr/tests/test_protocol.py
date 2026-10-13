"""Protocol channel and worker loop tests (stdlib only, no GPU)."""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest import mock

from scanmylib_ocr import protocol, worker
from scanmylib_ocr.engines.base import PageEngine, PageOptions
from scanmylib_ocr.protocol import Channel


class HugeResultEngine(PageEngine):
    def load(self) -> None:
        pass

    def parse(self, image_path: str, options: PageOptions) -> Any:
        return {"markdown": "x" * 4096}


class ChannelSizeTest(unittest.TestCase):
    def setUp(self) -> None:
        to_worker_read, self.to_worker_write = os.pipe()
        self.from_worker_read, from_worker_write = os.pipe()
        self.worker_side = Channel(to_worker_read, from_worker_write)
        self.supervisor_side = Channel(self.from_worker_read, self.to_worker_write)
        self.addCleanup(self.worker_side.close)
        self.addCleanup(self.supervisor_side.close)
        patcher = mock.patch.object(protocol, "MAX_MESSAGE_BYTES", 1024)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_oversized_message_is_refused_before_anything_is_written(self) -> None:
        with self.assertRaisesRegex(ValueError, "larger than"):
            self.worker_side.send({"result": "x" * 4096})
        os.set_blocking(self.from_worker_read, False)
        with self.assertRaises(BlockingIOError):
            os.read(self.from_worker_read, 1)

    def test_an_oversized_result_becomes_an_error_reply(self) -> None:
        self.supervisor_side.send({"op": "parse", "id": "job-1", "image_path": "page.jpg"})
        self.supervisor_side.send({"op": "shutdown"})
        with self.assertLogs("scanmylib_ocr.worker", "ERROR"):
            worker.serve(self.worker_side, HugeResultEngine())
        reply = self.supervisor_side.receive()
        self.assertEqual((reply["id"], reply["ok"], reply["error"]), ("job-1", False, protocol.PROCESSING_FAILED))
        self.assertIn("larger than", reply["detail"])


if __name__ == "__main__":
    unittest.main()
