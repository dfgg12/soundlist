"""Shared sound library: browse, create, edit, and delete assets."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlmodel import Session, select

from app.auth import require_user
from app.csrf import csrf_token, require_csrf
from app.db import get_session
from app.flash import flash, get_flashes
from app.models import Channel, ChannelSound, Sound, SoundClip, User

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates")
)


def _parse_float(raw: str, default: float) -> float:
    """Return float for a non-empty numeric string, else the default."""
    stripped = raw.strip()
    if not stripped:
        return default
    try:
        return float(stripped)
    except ValueError:
        return default


def _usage_counts(
    session: Session, sound_ids: list[int]
) -> dict[int, int]:
    """Return {sound_id: trigger count} for the given sound ids."""
    if not sound_ids:
        return {}
    rows = session.exec(
        select(ChannelSound.sound_id, func.count(ChannelSound.id))
        .where(ChannelSound.sound_id.in_(sound_ids))  # type: ignore[attr-defined]
        .group_by(ChannelSound.sound_id)
    ).all()
    return dict(rows)


def _using_channels(session: Session, sound_id: int) -> list[str]:
    """Return distinct slugs of channels wired to the given sound."""
    rows = session.exec(
        select(Channel.slug)
        .join(ChannelSound, ChannelSound.channel_id == Channel.id)  # type: ignore[arg-type]
        .where(ChannelSound.sound_id == sound_id)
        .distinct()
        .order_by(Channel.slug)
    ).all()
    return list(rows)


def _replace_clips(
    session: Session,
    sound: Sound,
    urls: list[str],
    volumes: list[str],
    chances: list[str],
    default_volume: float,
) -> int:
    """Drop a random Sound's clips and rebuild from parallel form lists."""
    for clip in session.exec(
        select(SoundClip).where(SoundClip.sound_id == sound.id)
    ).all():
        session.delete(clip)
    added = 0
    for idx, raw_url in enumerate(urls):
        url = raw_url.strip()
        if not url:
            continue
        volume = volumes[idx] if idx < len(volumes) else ""
        chance = chances[idx] if idx < len(chances) else ""
        session.add(
            SoundClip(
                sound_id=sound.id,
                url=url,
                volume=_parse_float(volume, default_volume),
                chance=chance.strip() or "100%",
            )
        )
        added += 1
    return added


# ---------------------------------------------------------------------------
# Browse / search (T4.1)
# ---------------------------------------------------------------------------


@router.get("/library", response_class=HTMLResponse)
async def library_index(
    request: Request,
    q: str = "",
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
) -> HTMLResponse:
    """List library assets with optional name/URL search and usage counts."""
    term = q.strip()
    stmt = select(Sound).order_by(Sound.name)
    if term:
        like = f"%{term}%"
        stmt = stmt.where(Sound.name.ilike(like))  # type: ignore[attr-defined]
    sounds = list(session.exec(stmt).all())
    counts = _usage_counts(session, [s.id for s in sounds if s.id])
    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "user": user,
            "sounds": sounds,
            "counts": counts,
            "q": term,
            "csrf": csrf_token(request),
            "flashes": get_flashes(request),
        },
    )


# ---------------------------------------------------------------------------
# Create asset (T4.2)
# ---------------------------------------------------------------------------


@router.post("/library")
async def create_asset(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    name: str = Form(...),
    is_random: str | None = Form(None),
    default_volume: str = Form(""),
    url: str = Form(""),
    clip_url: list[str] = Form([]),
    clip_volume: list[str] = Form([]),
    clip_chance: list[str] = Form([]),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Create a single or random multi-clip library asset."""
    require_csrf(request, csrf)
    name = name.strip()
    if not name:
        flash(request, "Asset name is required.", "error")
        return RedirectResponse("/library", status_code=303)
    if session.exec(select(Sound).where(Sound.name == name)).first():
        flash(request, f"Asset name '{name}' is already taken.", "error")
        return RedirectResponse("/library", status_code=303)
    dvol = _parse_float(default_volume, 0.5)
    random = is_random is not None
    if not random and not url.strip():
        flash(request, "URL is required for a single asset.", "error")
        return RedirectResponse("/library", status_code=303)
    sound = Sound(
        name=name,
        default_volume=dvol,
        is_random=random,
        url=None if random else url.strip(),
        created_by=user.id,
    )
    session.add(sound)
    session.flush()
    if random:
        added = _replace_clips(
            session, sound, clip_url, clip_volume, clip_chance, dvol
        )
        if not added:
            session.rollback()
            flash(request, "A random asset needs at least one clip.", "error")
            return RedirectResponse("/library", status_code=303)
    session.commit()
    flash(request, f"Created asset '{name}'.", "success")
    return RedirectResponse("/library", status_code=303)


# ---------------------------------------------------------------------------
# Edit asset (T4.4) - propagates to all linked channels
# ---------------------------------------------------------------------------


@router.post("/library/{sound_id}")
async def edit_asset(
    sound_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    name: str = Form(...),
    default_volume: str = Form(""),
    url: str = Form(""),
    clip_url: list[str] = Form([]),
    clip_volume: list[str] = Form([]),
    clip_chance: list[str] = Form([]),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Update an asset; changes apply to every channel linked to it."""
    require_csrf(request, csrf)
    sound = session.get(Sound, sound_id)
    if not sound:
        raise HTTPException(status_code=404, detail="Asset not found")
    name = name.strip()
    if not name:
        flash(request, "Asset name is required.", "error")
        return RedirectResponse("/library", status_code=303)
    clash = session.exec(
        select(Sound).where(Sound.name == name, Sound.id != sound_id)
    ).first()
    if clash:
        flash(request, f"Asset name '{name}' is already taken.", "error")
        return RedirectResponse("/library", status_code=303)
    dvol = _parse_float(default_volume, sound.default_volume)
    sound.name = name
    sound.default_volume = dvol
    if sound.is_random:
        added = _replace_clips(
            session, sound, clip_url, clip_volume, clip_chance, dvol
        )
        if not added:
            session.rollback()
            flash(request, "A random asset needs at least one clip.", "error")
            return RedirectResponse("/library", status_code=303)
    else:
        if not url.strip():
            flash(request, "URL is required for a single asset.", "error")
            return RedirectResponse("/library", status_code=303)
        sound.url = url.strip()
    session.add(sound)
    session.commit()
    flash(request, f"Saved asset '{name}'.", "success")
    return RedirectResponse("/library", status_code=303)


# ---------------------------------------------------------------------------
# Delete asset (T4.5) - blocked while in use
# ---------------------------------------------------------------------------


@router.post("/library/{sound_id}/delete")
async def delete_asset(
    sound_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Delete an unused asset; refuse and list channels if still linked."""
    require_csrf(request, csrf)
    sound = session.get(Sound, sound_id)
    if not sound:
        raise HTTPException(status_code=404, detail="Asset not found")
    users = _using_channels(session, sound_id)
    if users:
        flash(
            request,
            f"Cannot delete '{sound.name}': used by {', '.join(users)}.",
            "error",
        )
        return RedirectResponse("/library", status_code=303)
    for clip in session.exec(
        select(SoundClip).where(SoundClip.sound_id == sound_id)
    ).all():
        session.delete(clip)
    name = sound.name
    session.delete(sound)
    session.commit()
    flash(request, f"Deleted asset '{name}'.", "success")
    return RedirectResponse("/library", status_code=303)
