"""Panel views: dashboard and channel sound editor."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.auth import current_user, require_channel_access, require_user
from app.csrf import csrf_token, require_csrf
from app.db import get_session
from app.flash import flash, get_flashes
from app.models import Channel, ChannelSound, Sound, SoundClip, User
from app.serializer import channel_to_dict

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates")
)


_ADD_FORM_KEY = "add_form"


def _stash_form(request: Request, **fields: str | int) -> None:
    """Save add-trigger form values in session for redirect repopulation."""
    request.session[_ADD_FORM_KEY] = {k: str(v) for k, v in fields.items()}


def _pop_form(request: Request) -> dict[str, str]:
    """Return and clear any stashed add-trigger form values."""
    return request.session.pop(_ADD_FORM_KEY, {})


def _parse_volume(raw: str) -> float | None:
    """Return float for non-empty string, None for blank/invalid."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _resolve_sound(
    session: Session,
    mode: str,
    name: str,
    url: str,
    trigger_word: str,
    user: User,
) -> Sound | str:
    """Return resolved Sound or an error message string."""
    if mode == "existing":
        name = name.strip()
        if not name:
            return "Enter a sound name."
        found = session.exec(
            select(Sound).where(Sound.name == name)
        ).first()
        return found if found else f"Sound '{name}' not found in library."
    name = name.strip() or trigger_word
    url = url.strip()
    if not url:
        return "Sound URL is required for a new sound."
    found = session.exec(select(Sound).where(Sound.name == name)).first()
    if found is None:
        found = Sound(
            name=name, url=url, is_random=False, created_by=user.id
        )
        session.add(found)
        session.flush()
        return found
    if found.url != url:
        return (
            f"Sound name '{name}' is already taken. "
            "Use a different name or select from library."
        )
    return found


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
                session.exec(
                    select(Channel).order_by(func.lower(Channel.slug))
                ).all()
            )
        else:
            channels = list(
                session.exec(
                    select(Channel)
                    .where(Channel.owner_id == user.id)
                    .order_by(func.lower(Channel.slug))
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
    sounds_json = json.dumps(
        {s.name: {"volume": s.default_volume} for s in sounds}
    )
    trigger_hints = sorted(set(
        session.exec(
            select(ChannelSound.trigger_word)
            .where(ChannelSound.channel_id != channel.id)
            .distinct()
        ).all()
    ))
    return templates.TemplateResponse(
        request,
        "channel.html",
        {
            "user": user,
            "channel": channel,
            "channel_sounds": channel_sounds,
            "sounds": sounds,
            "sounds_json": sounds_json,
            "trigger_hints": trigger_hints,
            "add_form": _pop_form(request),
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
    sound_name: str = Form(""),
    sound_url: str = Form(""),
    volume: str = Form(""),
    chance: str = Form("100%"),
    trigger_cooldown: int = Form(0),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Add a new trigger to the channel, creating or linking a Sound."""
    require_csrf(request, csrf)

    def _err(msg: str) -> RedirectResponse:
        _stash_form(
            request,
            trigger_word=trigger_word,
            sound_mode=sound_mode,
            sound_name=sound_name,
            sound_url=sound_url,
            volume=volume,
            chance=chance,
            trigger_cooldown=trigger_cooldown,
        )
        flash(request, msg, "error")
        return RedirectResponse(f"/c/{slug}", status_code=303)

    trigger_word = trigger_word.strip()
    if not trigger_word:
        return _err("Trigger word is required.")
    dup = session.exec(
        select(ChannelSound).where(
            ChannelSound.channel_id == channel.id,
            ChannelSound.trigger_word == trigger_word,
        )
    ).first()
    if dup:
        return _err(f"Trigger '{trigger_word}' already exists.")
    result = _resolve_sound(
        session, sound_mode, sound_name, sound_url, trigger_word, user
    )
    if isinstance(result, str):
        return _err(result)
    sound = result
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


# ---------------------------------------------------------------------------
# Test / audition view (T5.1, T5.2)
# ---------------------------------------------------------------------------


@router.get("/c/{slug}/test", response_class=HTMLResponse)
async def channel_test(
    slug: str,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    channel: Channel = Depends(require_channel_access),
) -> HTMLResponse:
    """Render in-browser audio test page with live JSON preview."""
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
    test_items: list[dict] = []
    for cs in channel_sounds:
        sound = cs.sound
        if sound is None:
            continue
        effective_vol = (
            cs.volume if cs.volume is not None else sound.default_volume
        )
        item: dict = {
            "id": cs.id,
            "trigger_word": cs.trigger_word,
            "sound_name": sound.name,
            "volume": effective_vol,
            "chance": cs.chance,
            "enabled": cs.enabled,
            "is_random": sound.is_random,
        }
        if sound.is_random:
            clips = list(
                session.exec(
                    select(SoundClip)
                    .where(SoundClip.sound_id == sound.id)
                    .order_by(SoundClip.id)
                ).all()
            )
            item["clips"] = [
                {"url": c.url, "volume": c.volume, "chance": c.chance}
                for c in clips
            ]
        else:
            item["url"] = sound.url or ""
        test_items.append(item)

    channel_json = json.dumps(channel_to_dict(channel, session), indent=2)
    return templates.TemplateResponse(
        request,
        "test.html",
        {
            "user": user,
            "channel": channel,
            "test_items_json": json.dumps(test_items),
            "channel_json": channel_json,
            "flashes": get_flashes(request),
        },
    )


@router.get("/c/{slug}/validate", response_class=JSONResponse)
async def validate_trigger(
    slug: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    channel: Channel = Depends(require_channel_access),
    url: str = Query(default=""),
    trigger_word: str = Query(default=""),
    exclude_id: int = Query(default=0),
) -> JSONResponse:
    """Check URL reachability and trigger-word uniqueness for a channel."""
    result: dict = {}
    if url:
        try:
            async with httpx.AsyncClient(
                timeout=5, follow_redirects=True
            ) as client:
                r = await client.head(url)
                result["url_ok"] = r.status_code < 400
                result["url_status"] = r.status_code
        except httpx.RequestError as exc:
            result["url_ok"] = False
            result["url_error"] = str(exc)
    if trigger_word:
        q = select(ChannelSound).where(
            ChannelSound.channel_id == channel.id,
            ChannelSound.trigger_word == trigger_word.strip(),
        )
        if exclude_id:
            q = q.where(ChannelSound.id != exclude_id)
        existing = session.exec(q).first()
        result["trigger_unique"] = existing is None
    return JSONResponse(result)


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
