"""The routes of the api: the method and the path of every route it serves (docs/API.md)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from starlette.routing import BaseRoute, Mount

from scanmylib.app import create_app
from scanmylib.config import Settings


def list_served_routes(routes: Sequence[BaseRoute]) -> list[str]:
    served_routes: list[str] = []
    # FastAPI keeps each included router as one entry of app.routes: iter_route_contexts lists the routes it serves.
    for route in iter_route_contexts(routes):
        if isinstance(route.original_route, APIRoute):
            served_routes.extend(f"{method} {route.path}" for method in sorted(route.methods or ()))
        elif isinstance(route.original_route, Mount):
            served_routes.append(f"GET {route.path}/{{path:path}}")
        else:
            served_routes.append(repr(route.original_route))
    return served_routes


class TestTheRoutesOfTheApi:
    class TestWhenTheApiIsCreated:
        ROUTES = (
            "GET /api/health",
            "GET /download/scanmylib.apk",
            "GET /",
            "GET /static/{path:path}",
            "POST /api/session",
            "DELETE /api/session",
            "GET /api/status",
            "GET /api/pairing",
            "GET /api/pairing/qr.svg",
            "GET /api/pairing/apk-qr.svg",
            "GET /api/documents",
            "PUT /api/documents/{document_id}",
            "GET /api/documents/{document_id}",
            "PATCH /api/documents/{document_id}",
            "DELETE /api/documents/{document_id}",
            "PUT /api/documents/{document_id}/order",
            "DELETE /api/documents/{document_id}/order",
            "GET /api/documents/{document_id}/markdown",
            "GET /api/documents/{document_id}/html",
            "GET /api/documents/{document_id}/export.zip",
            "GET /api/documents/{document_id}/files/{path:path}",
            "POST /api/documents/{document_id}/pages",
            "GET /api/pages/{page_id}",
            "GET /api/pages/{page_id}/html",
            "PATCH /api/pages/{page_id}",
            "POST /api/pages/{page_id}/reprocess",
            "DELETE /api/pages/{page_id}",
            "GET /api/pages/{page_id}/image",
            "GET /api/pages/{page_id}/thumb",
        )

        @pytest.fixture
        def served_routes(self, settings: Settings) -> list[str]:
            return list_served_routes(create_app(settings).routes)

        def test_should_serve_each_route_by_its_method_and_path_and_no_other_so_that_none_is_lost_unseen(
            self, served_routes: list[str]
        ) -> None:
            assert sorted(served_routes) == sorted(self.ROUTES)
