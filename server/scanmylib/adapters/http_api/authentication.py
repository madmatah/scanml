"""The credential of a request (docs/API.md > Authentication): the bearer token, or the web session cookie.

* The phone sends ``Authorization: Bearer <token>``.
* The web UI exchanges the token for an HttpOnly, SameSite=Strict cookie
  holding a random session id.
* State-changing requests authenticated by cookie must carry ``X-ScanMyLib: 1``:
  a browser sends the cookie with every request to the api, but another page
  cannot add a header of its own to a request without the api's consent, which
  it never gives.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from ...application.access import Access

SESSION_COOKIE = "scanmylib_session"
CSRF_HEADER = "X-ScanMyLib"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def check_credential(request: Request, access: Access) -> None:
    """Raise 401 unless the request carries a valid credential (403: CSRF header missing)."""
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and credentials.strip() and access.token_matches(credentials.strip()):
        return
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id and access.is_session_valid(session_id):
        if request.method not in _SAFE_METHODS and request.headers.get(CSRF_HEADER) != "1":
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing {CSRF_HEADER} header")
        return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized", headers={"WWW-Authenticate": "Bearer"})
