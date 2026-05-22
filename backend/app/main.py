"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.routes import rspamd_security
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.middleware.security_headers import SecurityHeadersMiddleware

setup_logging()
log = get_logger("app")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app.startup", env=settings.app_env, app=settings.app_name)
    yield
    log.info("app.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/api/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    _origin = settings.platform_public_origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_origin] if _origin else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(api_router, prefix="/api")
    # Rspamd: /security/... (URL en multimap) y /api/security/... (si NPM solo enruta /api al backend)
    app.include_router(rspamd_security.router)
    app.include_router(rspamd_security.router, prefix="/api")

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
        index_html = static_dir / "index.html"

        # Starlette does not match `GET /` against `/{full_path:path}` (empty path);
        # without this, the site root returns FastAPI's 404 JSON.
        @app.get("/", include_in_schema=False)
        async def spa_root():
            if index_html.exists():
                return FileResponse(index_html)
            return {"detail": "frontend not built"}

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):  # noqa: ARG001
            # No devolver el SPA en rutas de API públicas (evita HTML confuso si falta rebuild)
            if full_path == "security" or full_path.startswith("security/"):
                raise HTTPException(status_code=404, detail="not_found")
            if index_html.exists():
                return FileResponse(index_html)
            return {"detail": "frontend not built"}

    return app


app = create_app()
