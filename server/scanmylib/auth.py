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
import os
import secrets
import tempfile
from pathlib import Path

from fastapi import HTTPException, Request, status

from .adapters.sqlite.database import Database
from .application.clock import Clock
from .domain import timestamps

SESSION_COOKIE = "scanmylib_session"
SESSION_MAX_AGE_S = 365 * 24 * 3600
CSRF_HEADER = "X-ScanMyLib"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def load_or_create_token(path: Path, override: str | None = None) -> str:
    """The API token: `override` if set, else the content of `path`, created on first use.

    A missing or empty file gets a new token, written to a temporary file then
    renamed: a crash or a full disk never leaves an empty token file behind
    (an empty token would let anyone open a session with an empty token).
    """
    if override:
        return override
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        existing = ""
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")  # mode 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(token + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return token


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Authenticator:
    def __init__(self, token: str, db: Database, clock: Clock) -> None:
        if not token:
            raise ValueError("empty API token")  # it would match an empty login
        self.token = token
        self._db = db
        self._token_fingerprint = _digest("scanmylib-token:" + token)
        self._clock = clock
        with db.transaction():
            db.execute(
                "DELETE FROM sessions WHERE expires_ts < ? OR token_fingerprint != ?",
                (self._clock.now().timestamp(), self._token_fingerprint),
            )

    def token_matches(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode("utf-8"), self.token.encode("utf-8"))

    def open_session(self) -> str:
        """Create a web session; returns the cookie value."""
        session_id = secrets.token_urlsafe(32)
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO sessions (id_hash, token_fingerprint, created_at, expires_ts) VALUES (?, ?, ?, ?)",
                (
                    _digest(session_id),
                    self._token_fingerprint,
                    timestamps.iso(self._clock.now()),
                    self._clock.now().timestamp() + SESSION_MAX_AGE_S,
                ),
            )
        return session_id

    def close_session(self, session_id: str) -> None:
        with self._db.transaction():
            self._db.execute("DELETE FROM sessions WHERE id_hash = ?", (_digest(session_id),))

    def session_valid(self, session_id: str) -> bool:
        row = self._db.one(
            "SELECT 1 FROM sessions WHERE id_hash = ? AND token_fingerprint = ? AND expires_ts > ?",
            (_digest(session_id), self._token_fingerprint, self._clock.now().timestamp()),
        )
        return row is not None

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
