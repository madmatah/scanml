"""Who may use the api: the holder of the token, or of a web session opened with it. The token is compared in constant
time, so that the time of an answer reveals nothing of it, and a session is stored as the hash of its id, so that a copy
of the database opens no session.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from ..domain.web_sessions import compute_session_expiry
from .clock import Clock
from .web_sessions import WebSessions


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Access:
    def __init__(self, token: str, web_sessions: WebSessions, clock: Clock) -> None:
        if not token:
            raise ValueError("empty API token")  # it would match an empty login
        self.token = token
        self._web_sessions = web_sessions
        self._token_fingerprint = _digest("scanmylib-token:" + token)
        self._clock = clock
        web_sessions.forget_ended(self._token_fingerprint, clock.now())

    def token_matches(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode("utf-8"), self.token.encode("utf-8"))

    def open_session(self) -> str:
        session_id = secrets.token_urlsafe(32)
        moment = self._clock.now()
        self._web_sessions.add(_digest(session_id), self._token_fingerprint, moment, compute_session_expiry(moment))
        return session_id

    def close_session(self, session_id: str) -> None:
        self._web_sessions.remove(_digest(session_id))

    def is_session_valid(self, session_id: str) -> bool:
        return self._web_sessions.is_valid(_digest(session_id), self._token_fingerprint, self._clock.now())
