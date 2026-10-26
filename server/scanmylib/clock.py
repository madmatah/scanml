"""The wall clock, in the server's local time zone (TZ)."""

from __future__ import annotations

from datetime import datetime


def now() -> datetime:
    return datetime.now().astimezone()
