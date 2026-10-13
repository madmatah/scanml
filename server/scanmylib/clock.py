"""Timestamps: ISO-8601 with offset in the API, in the server's local time zone (TZ)."""

from __future__ import annotations

from datetime import datetime


def now() -> datetime:
    return datetime.now().astimezone()


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def parse_client_time(text: str) -> datetime:
    """Parse an ISO-8601 time sent by a client; without offset it is server-local.

    Raises ValueError for anything that is not a plausible capture time.
    """
    moment = datetime.fromisoformat(text.strip())
    if moment.tzinfo is None:
        moment = moment.astimezone()
    if not 2000 <= moment.year <= 2200:
        raise ValueError("year out of range")
    return moment


def compact(moment: datetime) -> str:
    """``YYYYMMDD-HHMMSS`` in the moment's own offset (page keys, trash folders)."""
    return moment.strftime("%Y%m%d-%H%M%S")
