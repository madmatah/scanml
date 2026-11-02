"""A web session is known by the hash of its id, never by the id itself, and is stored with the fingerprint of the token
it was opened under and the moment it expires. It is valid at a moment before it expires, under that token only, until
it is removed. Removing a session leaves the others. Forgetting the ended sessions removes those that expired before the
moment given and those of another token than the one given. The web sessions are called from the event loop's thread
only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class WebSessions(Protocol):
    def add(self, id_hash: str, token_fingerprint: str, created_at: datetime, expires_at: datetime) -> None: ...
    def remove(self, id_hash: str) -> None: ...
    def is_valid(self, id_hash: str, token_fingerprint: str, moment: datetime) -> bool: ...
    def forget_ended(self, current_token_fingerprint: str, moment: datetime) -> None: ...
