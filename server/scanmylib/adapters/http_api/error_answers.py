"""The answers of the HTTP API to errors: a domain error or a refused image as its status, with its message as
FastAPI's `{"detail": …}`, and an invalid request without the input it holds."""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ...application.scan_images import ImageRejected, ImageTooLarge
from ...domain.records import Conflict, InvalidRequest, NotFound

# Domain errors → HTTP status (FastAPI's {"detail": "..."} shape).
_ERROR_STATUS: dict[type[Exception], int] = {
    NotFound: 404,
    Conflict: 409,
    InvalidRequest: 422,
    ImageTooLarge: 413,
    ImageRejected: 415,
}


class _AsciiJSONResponse(JSONResponse):
    """JSON with non-ASCII characters escaped: lone surrogates cannot be encoded in UTF-8."""

    def render(self, content: object) -> bytes:
        return json.dumps(content, allow_nan=False, separators=(",", ":")).encode("ascii")


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    # FastAPI's default handler, without echoing the invalid input back: it may
    # be what JSON cannot carry (NaN, Infinity, a lone surrogate "\ud800"...),
    # which turned the 422 into a 500.
    assert isinstance(exc, RequestValidationError)
    errors = [{key: value for key, value in error.items() if key != "input"} for error in exc.errors()]
    return _AsciiJSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)


def add_error_answers(app: FastAPI) -> None:
    async def domain_error(request: Request, exc: Exception) -> JSONResponse:
        status = next(code for kind, code in _ERROR_STATUS.items() if isinstance(exc, kind))
        return JSONResponse({"detail": str(exc)}, status_code=status)

    for kind in _ERROR_STATUS:
        app.add_exception_handler(kind, domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
