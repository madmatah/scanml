"""The status of the OCR, for each interface that shows it: its engine's, as the engine reports it, and how many pages
of its queue are in each status.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import QueueCounts
from .library import LibraryService
from .ocr_engine import EngineStatus, OcrEngineMonitor


@dataclass(frozen=True)
class OcrStatus:
    engine_status: EngineStatus
    queue_counts: QueueCounts


async def report_ocr_status(engine_monitor: OcrEngineMonitor, library: LibraryService) -> OcrStatus:
    engine_status = await engine_monitor.read_status()
    return OcrStatus(engine_status=engine_status, queue_counts=library.count_queue())
