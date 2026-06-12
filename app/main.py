"""FastAPI application entry point."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from app.admin import router as admin_router
from app.auth import router as auth_router
from app.auth import seed_admins
from app.db import engine, run_migrations
from app.library import router as library_router
from app.lists import router as lists_router
from app.models import IconTrigger
from app.panel import router as panel_router
from app.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def _seed_icon_triggers() -> None:
    """Import IconTriggers2.json into DB if the table is empty."""
    path = Path(settings.lists_dir) / "internals" / "IconTriggers2.json"
    if not path.exists():
        return
    with Session(engine) as session:
        if session.exec(select(IconTrigger)).first() is not None:
            return
        data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        for word, url in data.items():
            session.add(
                IconTrigger(
                    trigger_word=word.strip(), icon_url=url.strip()
                )
            )
        session.commit()
    log.info("seeded %d icon triggers from IconTriggers2.json", len(data))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run startup tasks: create tables, seed admins, seed icon triggers."""
    log.info("starting soundlist (env=%s)", settings.app_env)
    run_migrations()
    seed_admins()
    _seed_icon_triggers()
    log.info("db migrations applied")
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

# Public board static files served from the project root. Restricted to an
# explicit allowlist so secrets (.env, soundlist.db, .git, source) stay
# private; serving the whole directory would expose them.
_ROOT = Path(__file__).parent.parent
_PUBLIC_FILES = frozenset(
    {"index.html", "styles.css", "app.js", "marquee.html"}
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key.get_secret_value(),
    session_cookie="soundlist_session",
    max_age=60 * 60 * 24 * 7,  # 7 days
    https_only=settings.is_production,
    same_site="lax",
)


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> JSONResponse:
    """Return 200 when the app is alive."""
    return JSONResponse({"status": "ok"})


@app.get("/{filename}", include_in_schema=False)
async def public_asset(filename: str) -> FileResponse:
    """Serve an allowlisted public board file from the project root."""
    if filename not in _PUBLIC_FILES:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(_ROOT / filename)


def main() -> None:
    """Start uvicorn; entry point for uv run soundlist and python -m app."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production,
        log_level="info",
    )
