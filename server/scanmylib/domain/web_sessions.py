"""A web session's rules: how long it lasts."""

from __future__ import annotations

from datetime import datetime, timedelta

SESSION_LIFETIME = timedelta(days=365)


def compute_session_expiry(opened_at: datetime) -> datetime:
    return opened_at + SESSION_LIFETIME
