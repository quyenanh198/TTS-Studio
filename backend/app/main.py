"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import errlog
from .config import FRONTEND_DIST
from .jobs import jobs

APP_VERSION = "1.2.2"
log = logging.getLogger("tts_studio")


@asynccontextmanager
async def lifespan(app: FastAPI):
    jobs.bind_loop(asyncio.get_running_loop())
    from .db import db

    n = db.fail_orphaned_jobs("Ứng dụng đã khởi động lại khi job đang chạy — hãy chạy lại")
    if n:
        log.warning("marked %d orphaned job(s) as failed", n)
    log.info("TTS Studio backend ready")
    yield


def _install_error_logging(app: FastAPI) -> None:
    """Every failed request lands in the session error log (with traceback for unhandled ones)."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        if exc.status_code >= 400 and exc.status_code != 404:
            errlog.log_http_error(request.method, request.url.path, exc.status_code, exc.detail)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError):
        errlog.log_http_error(request.method, request.url.path, 422, exc.errors())
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def _unhandled_exc(request: Request, exc: Exception):
        log.exception("unhandled error in %s %s", request.method, request.url.path)
        return JSONResponse({"detail": f"Lỗi nội bộ: {exc}"}, status_code=500)


def create_app() -> FastAPI:
    errlog.setup(APP_VERSION)
    app = FastAPI(title="TTS Studio", version=APP_VERSION, lifespan=lifespan)
    _install_error_logging(app)
    # Loopback-only API: reject foreign Host headers (DNS-rebinding) and cross-origin browsers.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .api import core

    app.include_router(core.router, prefix="/api")

    # Optional feature routers — imported lazily so missing heavy deps don't break startup.
    for mod_name in ("tts", "inputs", "transcript", "clone"):
        try:
            mod = __import__(f"app.api.{mod_name}", fromlist=["router"])
            app.include_router(mod.router, prefix="/api")
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith("app.api"):
                continue  # router not implemented yet
            log.warning("router %s unavailable: %s", mod_name, exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("router %s failed to load: %s", mod_name, exc)

    if FRONTEND_DIST.exists():
        dist_root = FRONTEND_DIST.resolve()
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):  # noqa: ARG001
            if full_path:
                try:
                    candidate = (dist_root / full_path).resolve()
                except (OSError, ValueError):
                    candidate = None
                if candidate and candidate.is_relative_to(dist_root) and candidate.is_file():
                    return FileResponse(str(candidate))
            return FileResponse(str(dist_root / "index.html"))

    return app


app = create_app()
