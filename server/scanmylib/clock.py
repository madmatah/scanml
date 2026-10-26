"""The wall clock, in the server's local time zone (TZ), and the times that clients send."""

from __future__ import annotations

from datetime import datetime


def now() -> datetime:
    return datetime.now().astimezone()


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
