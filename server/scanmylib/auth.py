"""Authentication (docs/API.md): bearer token, web session cookie, CSRF header.

* The phone sends ``Authorization: Bearer <token>``.
* The web UI exchanges the token for an HttpOnly, SameSite=Strict cookie
  holding a random session id. Sessions live in the database (only a hash of
  the id is stored); they end on logout, after a year, or when the token is
  regenerated.
* State-changing requests authenticated by cookie must carry ``X-ScanMyLib: 1``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, status

from .application.clock import Clock
from .application.web_sessions import WebSessions

SESSION_COOKIE = "scanmylib_session"
SESSION_MAX_AGE_S = 365 * 24 * 3600
CSRF_HEADER = "X-ScanMyLib"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Authenticator:
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
        """Create a web session; returns the cookie value."""
        session_id = secrets.token_urlsafe(32)
        moment = self._clock.now()
        self._web_sessions.add(
            _digest(session_id), self._token_fingerprint, moment, moment + timedelta(seconds=SESSION_MAX_AGE_S)
        )
        return session_id

    def close_session(self, session_id: str) -> None:
        self._web_sessions.remove(_digest(session_id))

    def session_valid(self, session_id: str) -> bool:
        return self._web_sessions.is_valid(_digest(session_id), self._token_fingerprint, self._clock.now())

    def check(self, request: Request) -> None:
        """Raise 401 unless the request carries a valid credential (403: CSRF header missing)."""
        scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and credentials.strip() and self.token_matches(credentials.strip()):
            return
        session_id = request.cookies.get(SESSION_COOKIE)
        if session_id and self.session_valid(session_id):
            if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER) != "1":
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing {CSRF_HEADER} header")
            return
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized", headers={"WWW-Authenticate": "Bearer"})
