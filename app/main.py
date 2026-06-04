"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.admin import router as admin_router
from app.auth import router as auth_router
from app.auth import seed_admins
from app.db import create_db_and_tables
from app.library import router as library_router
from app.lists import router as lists_router
from app.panel import router as panel_router
from app.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks: create tables and seed admins."""
    log.info("starting soundlist (env=%s)", settings.app_env)
    create_db_and_tables()
    seed_admins()
    log.info("db tables ready")
    yield


app = FastAPI(
    title="Soundlist",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(lists_router)
app.include_router(panel_router)
app.include_router(library_router)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="soundlist_session",
    max_age=60 * 60 * 24 * 7,  # 7 days
    https_only=settings.is_production,
    same_site="lax",
)


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> JSONResponse:
    """Return 200 when the app is alive."""
    return JSONResponse({"status": "ok"})


def main() -> None:
    """Start uvicorn; entry point for uv run soundlist and python -m app."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production,
        log_level="info",
    )
