"""Moments written as text: ISO 8601 with their offset, and the compact form of page keys and folder names."""

from __future__ import annotations

from datetime import datetime


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def compact(moment: datetime) -> str:
    """``YYYYMMDD-HHMMSS`` in the moment's own offset (page keys, trash folders)."""
    return moment.strftime("%Y%m%d-%H%M%S")
