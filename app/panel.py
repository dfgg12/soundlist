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
from sqlmodel import Session, col, select

from app.auth import current_user, require_channel_access, require_user
from app.csrf import csrf_token, require_csrf
from app.db import get_session
from app.flash import flash, get_flashes
from app.models import Channel, ChannelSound, Sound, SoundClip, User
from app.serializer import channel_to_dict
from app.settings import settings

log = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates")
)


_ADD_FORM_KEY = "add_form"


class _AddSoundForm:
    """Bundled form fields for the add-trigger endpoint."""

    def __init__(
        self,
        trigger_word: str = Form(...),
        sound_mode: str = Form("new"),
        sound_name: str = Form(""),
        sound_url: str = Form(""),
        volume: str = Form(""),
        chance: str = Form("100%"),
        trigger_cooldown: int = Form(0),
        csrf: str = Form(...),
    ) -> None:
        self.trigger_word = trigger_word
        self.sound_mode = sound_mode
        self.sound_name = sound_name
        self.sound_url = sound_url
        self.volume = volume
        self.chance = chance
        self.trigger_cooldown = trigger_cooldown
        self.csrf = csrf


class _EditSoundForm:
    """Bundled form fields for the edit-trigger endpoint."""

    def __init__(
        self,
        trigger_word: str = Form(...),
        volume: str = Form(""),
        chance: str = Form("100%"),
        trigger_cooldown: int = Form(0),
        enabled: str | None = Form(None),
        csrf: str = Form(...),
    ) -> None:
        self.trigger_word = trigger_word
        self.volume = volume
        self.chance = chance
        self.trigger_cooldown = trigger_cooldown
        self.enabled = enabled
        self.csrf = csrf


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
    can_self_register = False
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
            if settings.allow_self_register and not channels:
                slug_taken = session.exec(
                    select(Channel).where(Channel.slug == user.login)
                ).first()
                can_self_register = slug_taken is None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "channels": channels,
            "can_self_register": can_self_register,
            "csrf": csrf_token(request),
            "flashes": get_flashes(request),
        },
    )


@router.post("/self-register")
async def self_register(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Create a channel for the current user using their login as slug."""
    require_csrf(request, csrf)
    if not settings.allow_self_register:
        raise HTTPException(
            status_code=403, detail="Self-registration disabled"
        )
    existing = session.exec(
        select(Channel).where(Channel.slug == user.login)
    ).first()
    if existing:
        flash(request, f"Channel '{user.login}' already exists.", "error")
        return RedirectResponse("/", status_code=303)
    channel = Channel(
        slug=user.login,
        display_name=user.display_name,
        owner_id=user.id,
        avatar_url=user.avatar_url,
    )
    session.add(channel)
    session.commit()
    log.info("self-registered channel %s for user %s", user.login, user.login)
    flash(request, f"Channel '{user.login}' created.", "success")
    return RedirectResponse("/", status_code=303)


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
    # Load clips (with volume+chance) for random sounds used in this channel
    random_sound_ids = [
        cs.sound_id
        for cs in channel_sounds
        if cs.sound and cs.sound.is_random
    ]
    sound_clips: dict[int, list[dict]] = {}
    if random_sound_ids:
        clip_rows = session.exec(
            select(SoundClip).where(
                col(SoundClip.sound_id).in_(random_sound_ids)
            )
        ).all()
        for clip in clip_rows:
            sound_clips.setdefault(clip.sound_id, []).append(
                {"url": clip.url, "volume": clip.volume, "chance": clip.chance}
            )
    # Build preview data keyed by ChannelSound.id for JS
    preview_items: dict[int, dict] = {}
    for cs in channel_sounds:
        if cs.sound is None:
            continue
        effective_vol = (
            cs.volume if cs.volume is not None else cs.sound.default_volume
        )
        if cs.sound.is_random:
            clips = sound_clips.get(cs.sound_id, [])
            if not clips:
                continue
            preview_items[cs.id] = {
                "trigger_word": cs.trigger_word,
                "vol": effective_vol,
                "is_random": True,
                "clips": clips,
            }
        elif cs.sound.url:
            preview_items[cs.id] = {
                "trigger_word": cs.trigger_word,
                "vol": effective_vol,
                "is_random": False,
                "url": cs.sound.url,
            }
    trigger_hints = sorted(set(
        session.exec(
            select(ChannelSound.trigger_word)
            .where(ChannelSound.channel_id != channel.id)
            .distinct()
        ).all()
    ))
    channel_json = json.dumps(channel_to_dict(channel, session), indent=2)
    return templates.TemplateResponse(
        request,
        "channel.html",
        {
            "user": user,
            "channel": channel,
            "channel_sounds": channel_sounds,
            "sounds": sounds,
            "sounds_json": sounds_json,
            "sound_clips": sound_clips,
            "preview_items": preview_items,
            "preview_items_json": json.dumps(preview_items),
            "channel_json": channel_json,
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
    form: _AddSoundForm = Depends(),
) -> RedirectResponse:
    """Add a new trigger to the channel, creating or linking a Sound."""
    require_csrf(request, form.csrf)

    def _err(msg: str) -> RedirectResponse:
        _stash_form(
            request,
            trigger_word=form.trigger_word,
            sound_mode=form.sound_mode,
            sound_name=form.sound_name,
            sound_url=form.sound_url,
            volume=form.volume,
            chance=form.chance,
            trigger_cooldown=form.trigger_cooldown,
        )
        flash(request, msg, "error")
        return RedirectResponse(f"/c/{slug}", status_code=303)

    trigger_word = form.trigger_word.strip()
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
        session, form.sound_mode, form.sound_name, form.sound_url,
        trigger_word, user,
    )
    if isinstance(result, str):
        return _err(result)
    sound = result
    cs = ChannelSound(
        channel_id=channel.id,
        sound_id=sound.id,
        trigger_word=trigger_word,
        volume=_parse_volume(form.volume),
        chance=form.chance.strip() or "100%",
        trigger_cooldown=form.trigger_cooldown,
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
    form: _EditSoundForm = Depends(),
) -> RedirectResponse:
    """Update trigger word and settings for an existing trigger."""
    require_csrf(request, form.csrf)
    cs = session.get(ChannelSound, cs_id)
    if not cs or cs.channel_id != channel.id:
        raise HTTPException(status_code=404, detail="Trigger not found")
    trigger_word = form.trigger_word.strip()
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
    cs.volume = _parse_volume(form.volume)
    cs.chance = form.chance.strip() or "100%"
    cs.trigger_cooldown = form.trigger_cooldown
    cs.enabled = form.enabled is not None
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
