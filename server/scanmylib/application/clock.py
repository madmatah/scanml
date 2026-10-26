"""A moment that a clock gives carries the server's UTC offset."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
