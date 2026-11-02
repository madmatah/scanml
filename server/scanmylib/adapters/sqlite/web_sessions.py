"""The web sessions, in the SQLite database."""

from __future__ import annotations

from datetime import datetime

from ...domain import timestamps
from .database import Database


class SqliteWebSessions:
    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, id_hash: str, token_fingerprint: str, created_at: datetime, expires_at: datetime) -> None:
        with self._database.transaction():
            self._database.execute(
                "INSERT INTO sessions (id_hash, token_fingerprint, created_at, expires_ts) VALUES (?, ?, ?, ?)",
                (
                    id_hash,
                    token_fingerprint,
                    timestamps.iso(created_at),
                    expires_at.timestamp(),
                ),
            )

    def remove(self, id_hash: str) -> None:
        with self._database.transaction():
            self._database.execute("DELETE FROM sessions WHERE id_hash = ?", (id_hash,))

    def is_valid(self, id_hash: str, token_fingerprint: str, moment: datetime) -> bool:
        row = self._database.one(
            "SELECT 1 FROM sessions WHERE id_hash = ? AND token_fingerprint = ? AND expires_ts > ?",
            (id_hash, token_fingerprint, moment.timestamp()),
        )
        return row is not None

    def forget_ended(self, current_token_fingerprint: str, moment: datetime) -> None:
        with self._database.transaction():
            self._database.execute(
                "DELETE FROM sessions WHERE expires_ts < ? OR token_fingerprint != ?",
                (moment.timestamp(), current_token_fingerprint),
            )
