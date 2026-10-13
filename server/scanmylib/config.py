"""Runtime configuration, read from SCANMYLIB_* environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    """Everything the server needs to know about its environment."""

    library_dir: Path = Path("/library")
    #: Host path of the library, only used for display (the UI shows where files are).
    library_host_path: str = "/library"
    state_dir: Path = Path("/state")
    ocr_socket: Path = Path("/run/scanmylib/ocr.sock")
    #: URL the phone uses to reach this server; derived from the request when empty.
    public_url: str = ""
    apk_path: Path = Path("/app-dist/scanmylib.apk")
    web_dir: Path = PACKAGE_DIR / "web"
    #: Fixed API token (otherwise generated once and stored in state_dir/token).
    token: str | None = None
    host: str = "0.0.0.0"
    port: int = 8765
    #: Upper bound for one /v1/parse call (the first one includes the engine start).
    ocr_timeout_s: float = 900.0
    #: Longest side of the image sent to the sandbox (larger scans are downscaled).
    ocr_max_side: int = 4096
    #: Quiet period before document.md / INDEX.md are rewritten after a change.
    assemble_delay_s: float = 2.0
    #: Longest wait between two retries while the sandbox is unavailable.
    ocr_retry_max_s: float = 30.0

    @property
    def db_path(self) -> Path:
        return self.state_dir / "scanmylib.db"

    @property
    def token_path(self) -> Path:
        return self.state_dir / "token"

    @property
    def thumbs_dir(self) -> Path:
        return self.state_dir / "thumbs"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        defaults = cls()

        def text(name: str, default: str) -> str:
            value = env.get(f"SCANMYLIB_{name}", "").strip()
            return value or default

        def path(name: str, default: Path) -> Path:
            return Path(text(name, str(default)))

        def number(name: str, default: float) -> float:
            raw = text(name, "")
            if not raw:
                return default
            try:
                value = float(raw)
            except ValueError:
                raise ValueError(f"SCANMYLIB_{name} must be a number, got {raw!r}") from None
            if value <= 0:
                raise ValueError(f"SCANMYLIB_{name} must be positive, got {raw!r}")
            return value

        library_dir = path("LIBRARY_DIR", defaults.library_dir)
        return cls(
            library_dir=library_dir,
            library_host_path=text("LIBRARY_HOST_PATH", str(library_dir)),
            state_dir=path("STATE_DIR", defaults.state_dir),
            ocr_socket=path("OCR_SOCKET", defaults.ocr_socket),
            public_url=text("PUBLIC_URL", "").rstrip("/"),
            apk_path=path("APK_PATH", defaults.apk_path),
            web_dir=path("WEB_DIR", defaults.web_dir),
            token=text("TOKEN", "") or None,
            host=text("HOST", defaults.host),
            port=int(number("PORT", defaults.port)),
            ocr_timeout_s=number("OCR_TIMEOUT_S", defaults.ocr_timeout_s),
            ocr_max_side=int(number("OCR_MAX_SIDE", defaults.ocr_max_side)),
            assemble_delay_s=number("ASSEMBLE_DELAY_S", defaults.assemble_delay_s),
            ocr_retry_max_s=number("OCR_RETRY_MAX_S", defaults.ocr_retry_max_s),
        )
