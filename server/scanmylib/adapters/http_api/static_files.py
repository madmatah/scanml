"""The web UI's static files, whose content-hashed files are cached for good."""

from __future__ import annotations

import os
from pathlib import PurePath

from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

# Only the web UI's build writes there, and each file it writes carries a hash of its content in its name: a new
# version of a file is a new name, so a browser may keep the old one for good.
_HASHED_FILES_DIRECTORY = "assets"
_ONE_YEAR_SECONDS = 365 * 24 * 60 * 60
_IMMUTABLE_CACHE_CONTROL = f"public, max-age={_ONE_YEAR_SECONDS}, immutable"


class WebUiStaticFiles(StaticFiles):
    """Marks only the files found, so that a missing one, which a later build may add, is never cached for good."""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        if PurePath(self.get_path(scope)).parts[:1] == (_HASHED_FILES_DIRECTORY,):
            response.headers["cache-control"] = _IMMUTABLE_CACHE_CONTROL
        return response
