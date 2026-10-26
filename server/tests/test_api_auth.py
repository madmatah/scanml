"""Authentication, CSRF guard, security headers, body limits, public routes."""

from __future__ import annotations

import contextlib
import dataclasses
import errno
import functools
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Never, Self

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartParser
from starlette.routing import BaseRoute, Mount

from scanmylib import __version__
from scanmylib.app import create_app
from scanmylib.auth import load_or_create_token
from scanmylib.images import MAX_UPLOAD_BYTES
from scanmylib.middleware import CONTENT_SECURITY_POLICY
from support import (
    AUTH,
    TOKEN,
    Answer,
    build_client,
    capture_answer,
    create_document,
    jpeg,
    preparing_settings,
    running_api,
    serving_fake_ocr,
    upload,
)

DOCUMENT_ID = "6f1c0000-0000-4000-8000-000000000001"
PAGE_ID = "6f1c0000-0000-4000-8000-000000000002"
QR_CODE_PATHS = ["/api/pairing/qr.svg", "/api/pairing/apk-qr.svg"]
APK = b"PK\x03\x04 fake apk"
JSON_CONTENT = {"Content-Type": "application/json"}
CSRF_HEADER = {"X-ScanMyLib": "1"}
OPEN_FILE_DESCRIPTOR = os.fdopen


class FullDiskFile:
    def __init__(self, file_descriptor: int, mode: str, encoding: str) -> None:
        self._stream = OPEN_FILE_DESCRIPTOR(file_descriptor, mode, encoding=encoding)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stream.close()

    def write(self, text: str) -> Never:
        raise OSError(errno.ENOSPC, "No space left on device")


def locate_token_file(directory: Path) -> Path:
    return directory / "state" / "token"


def build_bearer_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_cookie_header(session_id: str) -> dict[str, str]:
    return {"Cookie": f"scanmylib_session={session_id}"}


@dataclass(frozen=True)
class WebSession:
    wrong_login_status: int
    login_status: int
    cookie: str
    read_status: int
    change_without_header: Answer
    change_with_header_status: int
    logout_status: int
    is_cookie_kept_after_logout: bool
    read_after_logout_status: int
    replayed_cookie_status: int


@dataclass(frozen=True)
class GeneratedToken:
    token: str
    bearer_status: int
    file_mode: int
    token_after_restart: str


@dataclass(frozen=True)
class ReplacedEmptyToken:
    empty_login_status: int
    file_content_login_status: int
    token: str
    bearer_status: int
    file_mode: int


@dataclass(frozen=True)
class CreatedToken:
    token: str
    file_content: str


@dataclass(frozen=True)
class GuardedUploads:
    without_credential_status: int
    wrong_bearer_status: int
    cookie_without_header_status: int
    bodies_read_after_refusals: int
    accepted_status: int
    bodies_read_after_acceptance: int


@dataclass(frozen=True)
class BearerAnswers:
    listing: dict[str, Any]
    change_status: int


@dataclass(frozen=True)
class WebUi:
    placeholder: Answer
    page: str
    script_status: int
    script_type: str
    escape_statuses: dict[str, int]


@dataclass(frozen=True)
class QrCode:
    content_type: str
    content: bytes


@dataclass(frozen=True)
class PairingAcrossTheBuild:
    apk_status_before_build: int
    pairing_before_build: dict[str, Any]
    apk_status_after_build: int
    apk_content: bytes
    apk_type: str
    pairing_after_build: dict[str, Any]
    qr_codes: dict[str, QrCode]


@dataclass(frozen=True)
class OversizedUpload:
    status: int
    content_security_policy: str


@dataclass(frozen=True)
class AnswersToUnencodableInput:
    login: Answer
    field_statuses: dict[str, int]


@dataclass(frozen=True)
class RouteRequest:
    route: str
    method: str
    url: str


@dataclass(frozen=True)
class RouteRequests:
    protected: tuple[RouteRequest, ...]
    public: tuple[RouteRequest, ...]
    unchecked_routes: tuple[str, ...]
    route_count: int


@dataclass(frozen=True)
class RouteAnswers:
    protected: dict[str, Answer]
    public: dict[str, int]
    unchecked_routes: list[str]
    route_count: int


def plan_route_requests(
    routes: Sequence[BaseRoute],
    public_routes: frozenset[str],
    samples: Mapping[str, str],
    mounted_file_name: str,
) -> RouteRequests:
    requests: list[RouteRequest] = []
    unchecked_routes: list[str] = []
    # FastAPI keeps each included router as one entry of app.routes: iter_route_contexts lists the routes it serves,
    # as FastAPI's own OpenAPI schema reads them.
    served_routes = list(iter_route_contexts(routes))
    for route in served_routes:
        if isinstance(route.original_route, APIRoute):
            parameters = {name: samples[name] for name in route.param_convertors}
            url = str(route.url_path_for(route.name, **parameters))
            requests.extend(
                RouteRequest(f"{method} {route.path}", method, url) for method in sorted(route.methods or ())
            )
        elif isinstance(route.original_route, Mount):
            requests.append(RouteRequest(f"GET {route.path}/{{path:path}}", "GET", f"{route.path}/{mounted_file_name}"))
        else:
            unchecked_routes.append(repr(route.original_route))
    return RouteRequests(
        protected=tuple(request for request in requests if request.route not in public_routes),
        public=tuple(request for request in requests if request.route in public_routes),
        unchecked_routes=tuple(unchecked_routes),
        route_count=len(served_routes),
    )


def read_json_or_none(body: str) -> object:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


@pytest.fixture(scope="module")
def web_session(tmp_path_factory: pytest.TempPathFactory) -> WebSession:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        wrong_login_status = client.post("/api/session", json={"token": "wrong"}).status_code
        login = client.post("/api/session", json={"token": TOKEN})
        session_id = client.cookies["scanmylib_session"]
        read_status = client.get("/api/documents").status_code
        change_without_header = client.put(f"/api/documents/{DOCUMENT_ID}", json={"title": "No header"})
        change_with_header_status = client.put(
            f"/api/documents/{DOCUMENT_ID}", json={"title": "With header"}, headers=CSRF_HEADER
        ).status_code
        logout_status = client.delete("/api/session").status_code
        return WebSession(
            wrong_login_status=wrong_login_status,
            login_status=login.status_code,
            cookie=login.headers["set-cookie"],
            read_status=read_status,
            change_without_header=capture_answer(change_without_header),
            change_with_header_status=change_with_header_status,
            logout_status=logout_status,
            is_cookie_kept_after_logout="scanmylib_session" in client.cookies,
            read_after_logout_status=client.get("/api/documents").status_code,
            replayed_cookie_status=client.get("/api/documents", headers=build_cookie_header(session_id)).status_code,
        )


@pytest.fixture(scope="module")
def generated_token(tmp_path_factory: pytest.TempPathFactory) -> GeneratedToken:
    with (
        preparing_settings(tmp_path_factory.mktemp("api"), token=None) as settings,
        serving_fake_ocr(settings.ocr_socket),
    ):
        with build_client(settings) as client:
            token = settings.token_path.read_text().strip()
            bearer_status = client.get("/api/documents", headers=build_bearer_header(token)).status_code
        file_mode = settings.token_path.stat().st_mode & 0o777
        with build_client(settings):
            token_after_restart = settings.token_path.read_text().strip()
    return GeneratedToken(token, bearer_status, file_mode, token_after_restart)


@pytest.fixture(scope="module")
def guarded_uploads(tmp_path_factory: pytest.TempPathFactory) -> GuardedUploads:
    parsers: list[MultiPartParser] = []
    parse = MultiPartParser.parse

    async def recording_parse(self: MultiPartParser) -> FormData:
        parsers.append(self)
        return await parse(self)

    with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
        patch.setattr(MultiPartParser, "parse", recording_parse)
        document_id = create_document(api.client)
        without_credential_status = upload(api.client, document_id, jpeg(), headers={}).status_code
        wrong_bearer_status = upload(api.client, document_id, jpeg(), headers=build_bearer_header("wrong")).status_code
        api.client.post("/api/session", json={"token": TOKEN}).raise_for_status()
        cookie_without_header_status = upload(api.client, document_id, jpeg(), headers={}).status_code
        bodies_read_after_refusals = len(parsers)
        accepted_status = upload(api.client, document_id, jpeg(), headers=CSRF_HEADER).status_code
        return GuardedUploads(
            without_credential_status=without_credential_status,
            wrong_bearer_status=wrong_bearer_status,
            cookie_without_header_status=cookie_without_header_status,
            bodies_read_after_refusals=bodies_read_after_refusals,
            accepted_status=accepted_status,
            bodies_read_after_acceptance=len(parsers),
        )


@pytest.fixture(scope="module")
def web_ui(tmp_path_factory: pytest.TempPathFactory) -> WebUi:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        placeholder = api.client.get("/")
        static = api.settings.web_dir / "static"
        static.mkdir(parents=True)
        (api.settings.web_dir / "index.html").write_text("<!doctype html><title>ScanMyLib UI</title>")
        (static / "app.js").write_text("console.log('ok')")
        page = api.client.get("/").text
        script = api.client.get("/static/app.js")
        escapes = ["/static/../index.html", "/static/%2e%2e/index.html"]
        return WebUi(
            placeholder=Answer(placeholder.status_code, placeholder.text),
            page=page,
            script_status=script.status_code,
            script_type=script.headers["content-type"],
            escape_statuses={path: api.client.get(path).status_code for path in escapes},
        )


@pytest.fixture(scope="module")
def pairing_across_the_build(tmp_path_factory: pytest.TempPathFactory) -> PairingAcrossTheBuild:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        apk_status_before_build = api.client.get("/download/scanmylib.apk").status_code
        pairing_before_build = api.client.get("/api/pairing", headers=AUTH).json()
        api.settings.apk_path.parent.mkdir(parents=True)
        api.settings.apk_path.write_bytes(APK)
        apk = api.client.get("/download/scanmylib.apk")
        qr_codes = {path: api.client.get(path, headers=AUTH) for path in QR_CODE_PATHS}
        return PairingAcrossTheBuild(
            apk_status_before_build=apk_status_before_build,
            pairing_before_build=pairing_before_build,
            apk_status_after_build=apk.status_code,
            apk_content=apk.content,
            apk_type=apk.headers["content-type"],
            pairing_after_build=api.client.get("/api/pairing", headers=AUTH).json(),
            qr_codes={
                path: QrCode(qr_code.headers["content-type"], qr_code.content) for path, qr_code in qr_codes.items()
            },
        )


class TestTheAuthentication:
    #: At least 43 characters, as a token of 32 random bytes in URL-safe base64.
    SHORTEST_TOKEN_LENGTH = 43
    OWNER_ONLY_MODE = 0o600

    class TestWhenTheHealthIsReadWithoutACredential:
        @pytest.fixture(scope="class")
        @classmethod
        def health(cls, tmp_path_factory: pytest.TempPathFactory) -> Answer:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                return capture_answer(api.client.get("/api/health"))

        def test_should_answer_it(self, health: Answer) -> None:
            assert health.status == 200

        def test_should_name_the_api_with_its_version_and_level(self, health: Answer) -> None:
            assert health.body == {"name": "ScanMyLib", "version": __version__, "api": 1, "apk": None}

    class TestWhenARequestCarriesNoValidCredential:
        PROTECTED_ROUTES: tuple[tuple[str, str, dict[str, str] | None], ...] = (
            ("GET", "/api/status", None),
            ("GET", "/api/pairing", None),
            ("GET", "/api/pairing/qr.svg", None),
            ("GET", "/api/pairing/apk-qr.svg", None),
            ("GET", "/api/documents", None),
            ("PUT", f"/api/documents/{DOCUMENT_ID}", {"title": "x"}),
            ("PUT", f"/api/documents/{DOCUMENT_ID}/order", {"title": "x"}),
            ("DELETE", f"/api/documents/{DOCUMENT_ID}/order", {"title": "x"}),
            ("GET", f"/api/documents/{DOCUMENT_ID}/markdown", None),
            ("GET", f"/api/documents/{DOCUMENT_ID}/files/document.md", None),
            ("POST", f"/api/documents/{DOCUMENT_ID}/pages", {"title": "x"}),
            ("GET", f"/api/pages/{PAGE_ID}", None),
            ("PATCH", f"/api/pages/{PAGE_ID}", {"title": "x"}),
            ("POST", f"/api/pages/{PAGE_ID}/reprocess", {"title": "x"}),
            ("DELETE", f"/api/pages/{PAGE_ID}", {"title": "x"}),
            ("GET", f"/api/pages/{PAGE_ID}/thumb", None),
        )

        @pytest.fixture(
            scope="class",
            params=[{}, build_bearer_header("wrong"), {"Authorization": TOKEN}, build_cookie_header("forged")],
            ids=["no-credential", "a-wrong-bearer-token", "the-token-without-its-bearer-scheme", "a-forged-cookie"],
        )
        @classmethod
        def answers(cls, request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Answer]:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                return {
                    f"{method} {path}": capture_answer(
                        api.client.request(method, path, headers=request.param, json=body)
                    )
                    for method, path, body in cls.PROTECTED_ROUTES
                }

        def test_should_refuse_every_protected_route(self, answers: dict[str, Answer]) -> None:
            granted_routes = [route for route, answer in answers.items() if answer.status != 401]
            assert len(answers) == 16
            assert granted_routes == []

        def test_should_say_that_the_request_is_unauthorized(self, answers: dict[str, Answer]) -> None:
            unexplained_routes = [
                route for route, answer in answers.items() if answer.body != {"detail": "unauthorized"}
            ]
            assert len(answers) == 16
            assert unexplained_routes == []

    class TestWhenAnyRouteIsRequestedWithoutACredential:
        #: The routes that answer without a credential, as docs/SECURITY.md > On the local network lists them.
        PUBLIC_ROUTES = frozenset(
            {
                "GET /",
                "GET /api/health",
                "POST /api/session",
                "DELETE /api/session",
                "GET /download/scanmylib.apk",
                "GET /static/{path:path}",
            }
        )
        PATH_PARAMETER_SAMPLES = MappingProxyType(
            {"document_id": DOCUMENT_ID, "page_id": PAGE_ID, "path": "document.md"}
        )
        MOUNTED_FILE_NAME = "app.js"

        @pytest.fixture(scope="class")
        @classmethod
        def answers(cls, tmp_path_factory: pytest.TempPathFactory) -> RouteAnswers:
            with (
                preparing_settings(tmp_path_factory.mktemp("api")) as settings,
                serving_fake_ocr(settings.ocr_socket),
            ):
                static = settings.web_dir / "static"
                static.mkdir(parents=True)
                (static / cls.MOUNTED_FILE_NAME).write_text("console.log('ok')")
                app = create_app(settings)
                requests = plan_route_requests(
                    app.routes, cls.PUBLIC_ROUTES, cls.PATH_PARAMETER_SAMPLES, cls.MOUNTED_FILE_NAME
                )
                with TestClient(app) as client:
                    protected = {
                        request.route: client.request(request.method, request.url) for request in requests.protected
                    }
                    public = {request.route: client.request(request.method, request.url) for request in requests.public}
                return RouteAnswers(
                    protected={
                        route: Answer(response.status_code, response.text) for route, response in protected.items()
                    },
                    public={route: response.status_code for route, response in public.items()},
                    unchecked_routes=list(requests.unchecked_routes),
                    route_count=requests.route_count,
                )

        def test_should_refuse_every_route_but_the_public_ones(self, answers: RouteAnswers) -> None:
            granted_routes = [route for route, answer in answers.protected.items() if answer.status != 401]
            assert len(answers.protected) == 23
            assert granted_routes == []

        def test_should_say_that_the_request_is_unauthorized(self, answers: RouteAnswers) -> None:
            unexplained_routes = [
                route
                for route, answer in answers.protected.items()
                if read_json_or_none(answer.body) != {"detail": "unauthorized"}
            ]
            assert len(answers.protected) == 23
            assert unexplained_routes == []

        def test_should_find_each_public_route_among_the_routes_of_the_api(self, answers: RouteAnswers) -> None:
            assert sorted(answers.public) == sorted(self.PUBLIC_ROUTES)

        def test_should_not_refuse_the_public_routes_for_want_of_a_credential(self, answers: RouteAnswers) -> None:
            refused_routes = [route for route, status in answers.public.items() if status == 401]
            assert len(answers.public) == 6
            assert refused_routes == []

        def test_should_know_the_kind_of_every_route_so_that_none_escapes_the_check(
            self, answers: RouteAnswers
        ) -> None:
            assert answers.unchecked_routes == []
            assert answers.route_count == 29

    class TestWhenARequestCarriesTheBearerToken:
        @pytest.fixture(scope="class")
        @classmethod
        def answers(cls, tmp_path_factory: pytest.TempPathFactory) -> BearerAnswers:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                listing = api.client.get("/api/documents", headers=AUTH).json()
                change = api.client.put(f"/api/documents/{DOCUMENT_ID}", json={"title": "From the phone"}, headers=AUTH)
                return BearerAnswers(listing, change.status_code)

        def test_should_grant_access(self, answers: BearerAnswers) -> None:
            assert answers.listing == {"documents": []}

        def test_should_accept_a_change_from_the_phone_without_the_csrf_header(self, answers: BearerAnswers) -> None:
            assert answers.change_status == 201

    class TestWhenTheWebUiLogsInWithAWrongToken:
        def test_should_refuse_it(self, web_session: WebSession) -> None:
            assert web_session.wrong_login_status == 401

    class TestWhenTheWebUiLogsInWithTheToken:
        def test_should_open_a_session(self, web_session: WebSession) -> None:
            assert web_session.login_status == 204

        def test_should_set_the_session_cookie(self, web_session: WebSession) -> None:
            assert "scanmylib_session=" in web_session.cookie

        def test_should_hide_the_cookie_from_scripts(self, web_session: WebSession) -> None:
            assert "HttpOnly" in web_session.cookie

        def test_should_keep_the_session_for_a_year(self, web_session: WebSession) -> None:
            assert "Max-Age=31536000" in web_session.cookie

        def test_should_send_the_cookie_with_every_path(self, web_session: WebSession) -> None:
            assert "Path=/" in web_session.cookie

        def test_should_send_the_cookie_with_the_requests_of_its_own_site_only(self, web_session: WebSession) -> None:
            assert "SameSite=strict" in web_session.cookie

        def test_should_not_mark_the_cookie_secure_since_the_lan_serves_plain_http(
            self, web_session: WebSession
        ) -> None:
            assert "Secure" not in web_session.cookie

        class TestWhenAReadCarriesItsCookie:
            def test_should_grant_access(self, web_session: WebSession) -> None:
                assert web_session.read_status == 200

        class TestWhenAChangeCarriesItsCookieWithoutTheCsrfHeader:
            def test_should_refuse_it(self, web_session: WebSession) -> None:
                assert web_session.change_without_header.status == 403

            def test_should_say_that_the_header_is_missing(self, web_session: WebSession) -> None:
                assert web_session.change_without_header.body == {"detail": "missing X-ScanMyLib header"}

        class TestWhenAChangeCarriesItsCookieAndTheCsrfHeader:
            def test_should_accept_it(self, web_session: WebSession) -> None:
                assert web_session.change_with_header_status == 201

        class TestWhenTheWebUiLogsOut:
            def test_should_close_the_session(self, web_session: WebSession) -> None:
                assert web_session.logout_status == 204

            def test_should_clear_the_cookie(self, web_session: WebSession) -> None:
                assert web_session.is_cookie_kept_after_logout is False

            def test_should_refuse_a_read_without_the_cookie(self, web_session: WebSession) -> None:
                assert web_session.read_after_logout_status == 401

            class TestWhenTheOldCookieIsReplayed:
                def test_should_refuse_it_since_the_api_forgot_the_session(self, web_session: WebSession) -> None:
                    assert web_session.replayed_cookie_status == 401

    class TestWhenTheTokenIsRegenerated:
        @pytest.fixture(scope="class")
        @classmethod
        def replayed_cookie_status(cls, tmp_path_factory: pytest.TempPathFactory) -> int:
            with preparing_settings(tmp_path_factory.mktemp("api")) as settings, serving_fake_ocr(settings.ocr_socket):
                with build_client(settings) as first:
                    first.post("/api/session", json={"token": TOKEN}).raise_for_status()
                    session_id = first.cookies["scanmylib_session"]
                with build_client(dataclasses.replace(settings, token="another-token-1234567890")) as second:
                    return second.get("/api/documents", headers=build_cookie_header(session_id)).status_code

        def test_should_end_the_open_sessions(self, replayed_cookie_status: int) -> None:
            assert replayed_cookie_status == 401

    class TestWhenNoTokenIsConfigured:
        def test_should_generate_a_token_of_at_least_43_characters(self, generated_token: GeneratedToken) -> None:
            assert len(generated_token.token) >= TestTheAuthentication.SHORTEST_TOKEN_LENGTH

        def test_should_accept_it_as_the_bearer_token(self, generated_token: GeneratedToken) -> None:
            assert generated_token.bearer_status == 200

        def test_should_keep_its_file_readable_by_its_owner_only(self, generated_token: GeneratedToken) -> None:
            assert generated_token.file_mode == TestTheAuthentication.OWNER_ONLY_MODE

        class TestWhenTheApiStartsAgain:
            def test_should_keep_the_token(self, generated_token: GeneratedToken) -> None:
                assert generated_token.token_after_restart == generated_token.token

    class TestWhenTheTokenFileIsEmpty:
        @pytest.fixture(scope="class", params=["", "\n", "  \n"], ids=["empty", "a-line-end", "spaces-and-a-line-end"])
        @classmethod
        def replaced_token(
            cls, request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
        ) -> ReplacedEmptyToken:
            # Left by a crash or a full disk during the first start, such a file used to become the token.
            with preparing_settings(tmp_path_factory.mktemp("api"), token=None) as settings:
                settings.state_dir.mkdir(parents=True)
                settings.token_path.write_text(request.param)
                with serving_fake_ocr(settings.ocr_socket), build_client(settings) as client:
                    empty_login_status = client.post("/api/session", json={"token": ""}).status_code
                    file_content_login_status = client.post("/api/session", json={"token": request.param}).status_code
                    token = settings.token_path.read_text().strip()
                    bearer_status = client.get("/api/documents", headers=build_bearer_header(token)).status_code
                return ReplacedEmptyToken(
                    empty_login_status=empty_login_status,
                    file_content_login_status=file_content_login_status,
                    token=token,
                    bearer_status=bearer_status,
                    file_mode=settings.token_path.stat().st_mode & 0o777,
                )

        def test_should_refuse_an_empty_login_so_that_no_one_opens_a_session_without_the_token(
            self, replaced_token: ReplacedEmptyToken
        ) -> None:
            assert replaced_token.empty_login_status == 401

        def test_should_refuse_the_content_of_the_file_as_a_login(self, replaced_token: ReplacedEmptyToken) -> None:
            assert replaced_token.file_content_login_status == 401

        def test_should_generate_a_new_token_of_at_least_43_characters(
            self, replaced_token: ReplacedEmptyToken
        ) -> None:
            assert len(replaced_token.token) >= TestTheAuthentication.SHORTEST_TOKEN_LENGTH

        def test_should_accept_the_new_token_as_the_bearer_token(self, replaced_token: ReplacedEmptyToken) -> None:
            assert replaced_token.bearer_status == 200

        def test_should_keep_its_file_readable_by_its_owner_only(self, replaced_token: ReplacedEmptyToken) -> None:
            assert replaced_token.file_mode == TestTheAuthentication.OWNER_ONLY_MODE

    class TestTheLoadOrCreateTokenFunction:
        class TestWhenTheDiskIsFull:
            @pytest.fixture
            def create_token(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[], str]:
                monkeypatch.setattr(os, "fdopen", FullDiskFile)
                return functools.partial(load_or_create_token, locate_token_file(tmp_path))

            def test_should_fail_with_the_error_of_the_disk(self, create_token: Callable[[], str]) -> None:
                with pytest.raises(OSError, match="No space left on device"):
                    create_token()

            class TestWhenItHasFailed:
                @pytest.fixture
                def left_files(self, create_token: Callable[[], str], tmp_path: Path) -> list[str]:
                    with contextlib.suppress(OSError):
                        create_token()
                    return sorted(path.name for path in locate_token_file(tmp_path).parent.iterdir())

                def test_should_leave_no_token_file_and_no_temporary_file(self, left_files: list[str]) -> None:
                    assert left_files == []

                class TestWhenTheDiskHasRoomAgain:
                    @pytest.fixture
                    def created_token(
                        self, left_files: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
                    ) -> CreatedToken:
                        monkeypatch.undo()
                        token = load_or_create_token(locate_token_file(tmp_path))
                        return CreatedToken(token, locate_token_file(tmp_path).read_text().strip())

                    def test_should_create_a_token_of_at_least_43_characters(self, created_token: CreatedToken) -> None:
                        assert len(created_token.token) >= TestTheAuthentication.SHORTEST_TOKEN_LENGTH

                    def test_should_write_it_to_its_file(self, created_token: CreatedToken) -> None:
                        assert created_token.file_content == created_token.token

    class TestWhenUploadsAreRefusedForTheirCredentials:
        def test_should_refuse_one_without_a_credential(self, guarded_uploads: GuardedUploads) -> None:
            assert guarded_uploads.without_credential_status == 401

        def test_should_refuse_one_with_a_wrong_bearer_token(self, guarded_uploads: GuardedUploads) -> None:
            assert guarded_uploads.wrong_bearer_status == 401

        def test_should_refuse_one_with_the_cookie_but_without_the_csrf_header(
            self, guarded_uploads: GuardedUploads
        ) -> None:
            assert guarded_uploads.cookie_without_header_status == 403

        def test_should_refuse_them_before_reading_their_bodies_so_that_none_is_spooled_for_nothing(
            self, guarded_uploads: GuardedUploads
        ) -> None:
            assert guarded_uploads.bodies_read_after_refusals == 0

        class TestWhenAnUploadCarriesTheCookieAndTheCsrfHeader:
            def test_should_accept_it(self, guarded_uploads: GuardedUploads) -> None:
                assert guarded_uploads.accepted_status == 201

            def test_should_read_its_body_once(self, guarded_uploads: GuardedUploads) -> None:
                assert guarded_uploads.bodies_read_after_acceptance == 1


class TestTheSecurityHeaders:
    class TestWhenTheWebUiTheHealthOrTheDocumentsAreRead:
        READ_PATHS = ("/", "/api/health", "/api/documents")

        @pytest.fixture(scope="class")
        @classmethod
        def headers_by_path(cls, tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, str]]:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                return {path: dict(api.client.get(path, headers=AUTH).headers) for path in cls.READ_PATHS}

        def test_should_allow_content_from_the_api_s_own_origin_only(
            self, headers_by_path: dict[str, dict[str, str]]
        ) -> None:
            open_paths = [
                path
                for path, headers in headers_by_path.items()
                if not headers["content-security-policy"].startswith("default-src 'self'")
            ]
            assert len(headers_by_path) == 3
            assert open_paths == []

        def test_should_forbid_any_page_to_frame_them(self, headers_by_path: dict[str, dict[str, str]]) -> None:
            framable_paths = [
                path
                for path, headers in headers_by_path.items()
                if "frame-ancestors 'none'" not in headers["content-security-policy"]
            ]
            assert len(headers_by_path) == 3
            assert framable_paths == []

        def test_should_forbid_browsers_to_guess_their_type(self, headers_by_path: dict[str, dict[str, str]]) -> None:
            sniffable_paths = [
                path for path, headers in headers_by_path.items() if headers["x-content-type-options"] != "nosniff"
            ]
            assert len(headers_by_path) == 3
            assert sniffable_paths == []

        def test_should_forbid_framing_them_by_the_older_header_too(
            self, headers_by_path: dict[str, dict[str, str]]
        ) -> None:
            framable_paths = [path for path, headers in headers_by_path.items() if headers["x-frame-options"] != "DENY"]
            assert len(headers_by_path) == 3
            assert framable_paths == []

        def test_should_send_no_referrer(self, headers_by_path: dict[str, dict[str, str]]) -> None:
            referring_paths = [
                path for path, headers in headers_by_path.items() if headers["referrer-policy"] != "no-referrer"
            ]
            assert len(headers_by_path) == 3
            assert referring_paths == []

        def test_should_forbid_caching_the_documents(self, headers_by_path: dict[str, dict[str, str]]) -> None:
            assert headers_by_path["/api/documents"]["cache-control"] == "no-store"


class TestThePublicRoutes:
    class TestWhenTheWebUiIsNotInstalled:
        def test_should_answer_its_page(self, web_ui: WebUi) -> None:
            assert web_ui.placeholder.status == 200

        def test_should_say_that_it_is_not_installed(self, web_ui: WebUi) -> None:
            assert "the web UI is not installed" in web_ui.placeholder.body

        class TestWhenItIsInstalled:
            def test_should_serve_its_page(self, web_ui: WebUi) -> None:
                assert "ScanMyLib UI" in web_ui.page

            def test_should_serve_its_scripts(self, web_ui: WebUi) -> None:
                assert web_ui.script_status == 200

            def test_should_serve_its_scripts_as_javascript(self, web_ui: WebUi) -> None:
                assert web_ui.script_type.startswith("text/javascript")

            def test_should_refuse_a_path_out_of_its_static_folder(self, web_ui: WebUi) -> None:
                served_paths = [path for path, status in web_ui.escape_statuses.items() if status != 404]
                assert len(web_ui.escape_statuses) == 2
                assert served_paths == []

    class TestWhenTheApiDocumentationIsRequested:
        @pytest.fixture(scope="class")
        @classmethod
        def statuses(cls, tmp_path_factory: pytest.TempPathFactory) -> dict[str, int]:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                return {path: api.client.get(path).status_code for path in ("/docs", "/redoc", "/openapi.json")}

        def test_should_not_expose_it(self, statuses: dict[str, int]) -> None:
            exposed_paths = [path for path, status in statuses.items() if status != 404]
            assert len(statuses) == 3
            assert exposed_paths == []


class TestThePairing:
    class TestWhenNoApkIsBuilt:
        def test_should_offer_no_apk_to_download(self, pairing_across_the_build: PairingAcrossTheBuild) -> None:
            assert pairing_across_the_build.apk_status_before_build == 404

        def test_should_give_the_url_and_the_token_of_the_api_with_their_pairing_link(
            self, pairing_across_the_build: PairingAcrossTheBuild
        ) -> None:
            assert pairing_across_the_build.pairing_before_build == {
                "url": "http://192.168.1.10:8765",
                "token": TOKEN,
                "pair_uri": f"scanmylib://pair?url=http%3A%2F%2F192.168.1.10%3A8765&token={TOKEN}",
                "apk_available": False,
                "apk_url": "http://192.168.1.10:8765/download/scanmylib.apk",
            }

        class TestWhenTheApkIsBuilt:
            def test_should_offer_it_to_download(self, pairing_across_the_build: PairingAcrossTheBuild) -> None:
                assert pairing_across_the_build.apk_status_after_build == 200

            def test_should_serve_the_built_file(self, pairing_across_the_build: PairingAcrossTheBuild) -> None:
                assert pairing_across_the_build.apk_content == APK

            def test_should_serve_it_as_an_android_package(
                self, pairing_across_the_build: PairingAcrossTheBuild
            ) -> None:
                assert pairing_across_the_build.apk_type == "application/vnd.android.package-archive"

            def test_should_say_that_it_is_available(self, pairing_across_the_build: PairingAcrossTheBuild) -> None:
                assert pairing_across_the_build.pairing_after_build["apk_available"] is True

            def test_should_serve_the_qr_codes_as_scalable_vector_graphics(
                self, pairing_across_the_build: PairingAcrossTheBuild
            ) -> None:
                qr_codes = pairing_across_the_build.qr_codes
                other_paths = [path for path, qr_code in qr_codes.items() if qr_code.content_type != "image/svg+xml"]
                assert len(qr_codes) == 2
                assert other_paths == []

            def test_should_draw_the_qr_codes_in_a_vector_graphics_element(
                self, pairing_across_the_build: PairingAcrossTheBuild
            ) -> None:
                qr_codes = pairing_across_the_build.qr_codes
                undrawn_paths = [path for path, qr_code in qr_codes.items() if b"<svg" not in qr_code.content]
                assert len(qr_codes) == 2
                assert undrawn_paths == []

            def test_should_put_no_script_in_the_qr_codes(
                self, pairing_across_the_build: PairingAcrossTheBuild
            ) -> None:
                qr_codes = pairing_across_the_build.qr_codes
                scripted_paths = [path for path, qr_code in qr_codes.items() if b"<script" in qr_code.content]
                assert len(qr_codes) == 2
                assert scripted_paths == []


class TestTheBodySizeLimits:
    class TestWhenAJsonBodyIsLargerThanItsLimit:
        BODY_SIZE_BYTES = 2 * 1024 * 1024

        @pytest.fixture(scope="class")
        @classmethod
        def status(cls, tmp_path_factory: pytest.TempPathFactory) -> int:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                body = b"{" + b" " * cls.BODY_SIZE_BYTES + b"}"
                return api.client.post("/api/session", content=body, headers=JSON_CONTENT).status_code

        def test_should_refuse_it_as_too_large(self, status: int) -> None:
            assert status == 413

    class TestWhenAnUploadIsLargerThanItsLimit:
        BYTES_BEYOND_THE_LARGEST_IMAGE = 2 * 1024 * 1024

        @pytest.fixture(scope="class")
        @classmethod
        def oversized_upload(cls, tmp_path_factory: pytest.TempPathFactory) -> OversizedUpload:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                image = b"\xff\xd8" + b"\x00" * (MAX_UPLOAD_BYTES + cls.BYTES_BEYOND_THE_LARGEST_IMAGE)
                response = upload(api.client, document_id, image)
                return OversizedUpload(response.status_code, response.headers["content-security-policy"])

        def test_should_refuse_it_as_too_large(self, oversized_upload: OversizedUpload) -> None:
            assert oversized_upload.status == 413

        def test_should_keep_the_content_security_policy_on_the_refusal(
            self, oversized_upload: OversizedUpload
        ) -> None:
            assert oversized_upload.content_security_policy == CONTENT_SECURITY_POLICY


class TestTheValidationErrors:
    class TestWhenTheJsonOfARequestCannotBeEncodedBack:
        @pytest.fixture(scope="class")
        @classmethod
        def answers_to_unencodable_input(cls, tmp_path_factory: pytest.TempPathFactory) -> AnswersToUnencodableInput:
            # The 422 response used to echo the invalid input, which failed to encode: a 500.
            with running_api(tmp_path_factory.mktemp("api")) as api:
                login = api.client.post("/api/session", content=b'{"token": "\\ud800"}', headers=JSON_CONTENT)
                document_id = create_document(api.client)
                patches = {
                    "a-title-with-a-lone-surrogate": (f"/api/documents/{document_id}", b'{"title": "x\\udfff"}'),
                    "a-title-that-is-not-a-number": (f"/api/documents/{document_id}", b'{"title": NaN}'),
                    "a-page-number-that-is-infinite": (f"/api/pages/{PAGE_ID}", b'{"manual_number": Infinity}'),
                    "a-rotation-beyond-any-float": (f"/api/pages/{PAGE_ID}", b'{"rotation": 1e999}'),
                }
                return AnswersToUnencodableInput(
                    login=capture_answer(login),
                    field_statuses={
                        name: api.client.patch(path, content=body, headers={**AUTH, **JSON_CONTENT}).status_code
                        for name, (path, body) in patches.items()
                    },
                )

        def test_should_refuse_a_login_holding_a_lone_surrogate_as_invalid(
            self, answers_to_unencodable_input: AnswersToUnencodableInput
        ) -> None:
            assert answers_to_unencodable_input.login.status == 422

        def test_should_locate_the_error_in_the_token(
            self, answers_to_unencodable_input: AnswersToUnencodableInput
        ) -> None:
            assert answers_to_unencodable_input.login.body["detail"][0]["loc"] == ["body", "token"]

        def test_should_not_echo_the_input_back(self, answers_to_unencodable_input: AnswersToUnencodableInput) -> None:
            assert "input" not in answers_to_unencodable_input.login.body["detail"][0]

        def test_should_refuse_as_invalid_a_field_holding_a_lone_surrogate_an_infinity_or_a_not_a_number_value(
            self, answers_to_unencodable_input: AnswersToUnencodableInput
        ) -> None:
            field_statuses = answers_to_unencodable_input.field_statuses
            accepted_fields = [field for field, status in field_statuses.items() if status != 422]
            assert len(field_statuses) == 4
            assert accepted_fields == []

    class TestWhenTheJsonOfALoginHoldsAnAccentedLetter:
        @pytest.fixture(scope="class")
        @classmethod
        def status(cls, tmp_path_factory: pytest.TempPathFactory) -> int:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                body = '{"token": "é"}'.encode()
                return api.client.post("/api/session", content=body, headers=JSON_CONTENT).status_code

        def test_should_read_it_and_refuse_it_only_as_a_wrong_token(self, status: int) -> None:
            assert status == 401
