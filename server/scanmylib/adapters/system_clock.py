"""The offset of a moment is that of the server's local time zone, which TZ sets."""

from __future__ import annotations

from datetime import datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now().astimezone()
