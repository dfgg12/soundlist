"""Panel views: dashboard and channel sound editor."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.auth import current_user, require_channel_access, require_user
from app.csrf import csrf_token, require_csrf
from app.db import get_session
from app.flash import flash, get_flashes
from app.models import Channel, ChannelSound, Sound, User

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates")
)


def _parse_volume(raw: str) -> float | None:
    """Return float for non-empty string, None for blank/invalid."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _next_position(session: Session, channel_id: int) -> int:
    """Return position value for a new ChannelSound (append to end)."""
    rows = session.exec(
        select(ChannelSound).where(ChannelSound.channel_id == channel_id)
    ).all()
    return len(rows)


# ---------------------------------------------------------------------------
# Dashboard (T3.2)
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: Session = Depends(get_session),
    user: User | None = Depends(current_user),
) -> HTMLResponse:
    """Render dashboard with channels the user may manage."""
    channels: list[Channel] = []
    if user:
        if user.is_admin:
            channels = list(
                session.exec(select(Channel).order_by(Channel.slug)).all()
            )
        else:
            channels = list(
                session.exec(
                    select(Channel)
                    .where(Channel.owner_id == user.id)
                    .order_by(Channel.slug)
                ).all()
            )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "channels": channels,
            "flashes": get_flashes(request),
        },
    )


# ---------------------------------------------------------------------------
# Channel editor (T3.3)
# ---------------------------------------------------------------------------


@router.get("/c/{slug}", response_class=HTMLResponse)
async def channel_editor(
    slug: str,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    channel: Channel = Depends(require_channel_access),
) -> HTMLResponse:
    """Render the trigger table editor for a channel."""
    channel_sounds = list(
        session.exec(
            select(ChannelSound)
            .where(ChannelSound.channel_id == channel.id)
            .options(
                selectinload(ChannelSound.sound)  # type: ignore[arg-type]
            )
            .order_by(ChannelSound.position, ChannelSound.id)
        ).all()
    )
    sounds = list(session.exec(select(Sound).order_by(Sound.name)).all())
    return templates.TemplateResponse(
        request,
        "channel.html",
        {
            "user": user,
            "channel": channel,
            "channel_sounds": channel_sounds,
            "sounds": sounds,
            "csrf": csrf_token(request),
            "flashes": get_flashes(request),
        },
    )


# ---------------------------------------------------------------------------
# Add trigger (T3.4)
# ---------------------------------------------------------------------------


@router.post("/c/{slug}/sound")
async def add_sound(
    slug: str,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    channel: Channel = Depends(require_channel_access),
    trigger_word: str = Form(...),
    sound_mode: str = Form("new"),
    sound_id: int | None = Form(None),
    sound_name: str = Form(""),
    sound_url: str = Form(""),
    volume: str = Form(""),
    chance: str = Form("100%"),
    trigger_cooldown: int = Form(0),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Add a new trigger to the channel, creating or linking a Sound."""
    require_csrf(request, csrf)
    trigger_word = trigger_word.strip()
    if not trigger_word:
        flash(request, "Trigger word is required.", "error")
        return RedirectResponse(f"/c/{slug}", status_code=303)
    dup = session.exec(
        select(ChannelSound).where(
            ChannelSound.channel_id == channel.id,
            ChannelSound.trigger_word == trigger_word,
        )
    ).first()
    if dup:
        flash(request, f"Trigger '{trigger_word}' already exists.", "error")
        return RedirectResponse(f"/c/{slug}", status_code=303)
    sound: Sound | None = None
    if sound_mode == "existing":
        if not sound_id:
            flash(request, "Select a sound from the library.", "error")
            return RedirectResponse(f"/c/{slug}", status_code=303)
        sound = session.get(Sound, sound_id)
        if not sound:
            flash(request, "Sound not found.", "error")
            return RedirectResponse(f"/c/{slug}", status_code=303)
    else:
        sound_name = sound_name.strip() or trigger_word
        sound_url = sound_url.strip()
        if not sound_url:
            flash(request, "Sound URL is required for a new sound.", "error")
            return RedirectResponse(f"/c/{slug}", status_code=303)
        sound = session.exec(
            select(Sound).where(Sound.name == sound_name)
        ).first()
        if sound is None:
            sound = Sound(
                name=sound_name,
                url=sound_url,
                is_random=False,
                created_by=user.id,
            )
            session.add(sound)
            session.flush()
        elif sound.url != sound_url:
            flash(
                request,
                f"Sound name '{sound_name}' is already taken. "
                "Use a different name or select from library.",
                "error",
            )
            return RedirectResponse(f"/c/{slug}", status_code=303)
    cs = ChannelSound(
        channel_id=channel.id,
        sound_id=sound.id,
        trigger_word=trigger_word,
        volume=_parse_volume(volume),
        chance=chance.strip() or "100%",
        trigger_cooldown=trigger_cooldown,
        enabled=True,
        position=_next_position(session, channel.id),
    )
    session.add(cs)
    session.commit()
    flash(request, f"Added trigger '{trigger_word}'.", "success")
    return RedirectResponse(f"/c/{slug}", status_code=303)


# ---------------------------------------------------------------------------
# Edit trigger (T3.5)
# ---------------------------------------------------------------------------


@router.post("/c/{slug}/sound/{cs_id}")
async def edit_sound(
    slug: str,
    cs_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    channel: Channel = Depends(require_channel_access),
    trigger_word: str = Form(...),
    volume: str = Form(""),
    chance: str = Form("100%"),
    trigger_cooldown: int = Form(0),
    enabled: str | None = Form(None),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Update trigger word and settings for an existing trigger."""
    require_csrf(request, csrf)
    cs = session.get(ChannelSound, cs_id)
    if not cs or cs.channel_id != channel.id:
        raise HTTPException(status_code=404, detail="Trigger not found")
    trigger_word = trigger_word.strip()
    if not trigger_word:
        flash(request, "Trigger word cannot be empty.", "error")
        return RedirectResponse(f"/c/{slug}", status_code=303)
    if trigger_word != cs.trigger_word:
        dup = session.exec(
            select(ChannelSound).where(
                ChannelSound.channel_id == channel.id,
                ChannelSound.trigger_word == trigger_word,
                ChannelSound.id != cs_id,
            )
        ).first()
        if dup:
            flash(
                request,
                f"Trigger '{trigger_word}' already exists.",
                "error",
            )
            return RedirectResponse(f"/c/{slug}", status_code=303)
    cs.trigger_word = trigger_word
    cs.volume = _parse_volume(volume)
    cs.chance = chance.strip() or "100%"
    cs.trigger_cooldown = trigger_cooldown
    cs.enabled = enabled is not None
    session.add(cs)
    session.commit()
    flash(request, f"Saved '{trigger_word}'.", "success")
    return RedirectResponse(f"/c/{slug}", status_code=303)


# ---------------------------------------------------------------------------
# Delete trigger (T3.5)
# ---------------------------------------------------------------------------


@router.post("/c/{slug}/sound/{cs_id}/delete")
async def delete_sound(
    slug: str,
    cs_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    channel: Channel = Depends(require_channel_access),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Remove a trigger from the channel."""
    require_csrf(request, csrf)
    cs = session.get(ChannelSound, cs_id)
    if not cs or cs.channel_id != channel.id:
        raise HTTPException(status_code=404, detail="Trigger not found")
    word = cs.trigger_word
    session.delete(cs)
    session.commit()
    flash(request, f"Deleted trigger '{word}'.", "success")
    return RedirectResponse(f"/c/{slug}", status_code=303)


# ---------------------------------------------------------------------------
# Toggle enabled (T3.5)
# ---------------------------------------------------------------------------


@router.post("/c/{slug}/sound/{cs_id}/toggle")
async def toggle_sound(
    slug: str,
    cs_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    channel: Channel = Depends(require_channel_access),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Flip the enabled flag on a trigger."""
    require_csrf(request, csrf)
    cs = session.get(ChannelSound, cs_id)
    if not cs or cs.channel_id != channel.id:
        raise HTTPException(status_code=404, detail="Trigger not found")
    cs.enabled = not cs.enabled
    session.add(cs)
    session.commit()
    state = "enabled" if cs.enabled else "disabled"
    flash(request, f"Trigger '{cs.trigger_word}' {state}.", "success")
    return RedirectResponse(f"/c/{slug}", status_code=303)
