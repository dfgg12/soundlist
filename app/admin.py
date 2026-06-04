"""Admin panel: manage users, channels, and ownership."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.auth import require_user
from app.csrf import csrf_token, require_csrf
from app.db import get_session
from app.flash import flash, get_flashes
from app.models import Channel, User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin")
templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates")
)


def _require_admin(user: User = Depends(require_user)) -> User:
    """Raise 403 if the authenticated user is not an admin."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    return user


@router.get("", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    session: Session = Depends(get_session),
    admin: User = Depends(_require_admin),
) -> HTMLResponse:
    """Render admin panel with user and channel tables."""
    users = list(session.exec(select(User).order_by(User.login)).all())
    channels = list(
        session.exec(select(Channel).order_by(Channel.slug)).all()
    )
    owner_map: dict[int, str] = {}
    for ch in channels:
        if ch.owner_id is not None:
            owner = session.get(User, ch.owner_id)
            if owner:
                owner_map[ch.id] = owner.login
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": admin,
            "users": users,
            "channels": channels,
            "owner_map": owner_map,
            "csrf": csrf_token(request),
            "flashes": get_flashes(request),
        },
    )


@router.post("/channel/create")
async def create_channel(
    request: Request,
    session: Session = Depends(get_session),
    admin: User = Depends(_require_admin),
    slug: str = Form(...),
    display_name: str = Form(""),
    owner_login: str = Form(""),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Create a new channel, optionally assigned to a user by login."""
    require_csrf(request, csrf)
    slug = slug.strip().lower()
    if not slug:
        flash(request, "Slug is required.", "error")
        return RedirectResponse("/admin", status_code=303)
    existing = session.exec(
        select(Channel).where(Channel.slug == slug)
    ).first()
    if existing:
        flash(request, f"Channel '{slug}' already exists.", "error")
        return RedirectResponse("/admin", status_code=303)
    owner_id: int | None = None
    owner_login = owner_login.strip().lower()
    if owner_login:
        owner = session.exec(
            select(User).where(User.login == owner_login)
        ).first()
        if not owner:
            flash(request, f"User '{owner_login}' not found.", "error")
            return RedirectResponse("/admin", status_code=303)
        owner_id = owner.id
    channel = Channel(
        slug=slug,
        display_name=display_name.strip() or slug,
        owner_id=owner_id,
    )
    session.add(channel)
    session.commit()
    log.info("admin %s created channel %s", admin.login, slug)
    flash(request, f"Channel '{slug}' created.", "success")
    return RedirectResponse("/admin", status_code=303)


@router.post("/channel/{slug}/assign")
async def assign_channel(
    slug: str,
    request: Request,
    session: Session = Depends(get_session),
    admin: User = Depends(_require_admin),
    owner_login: str = Form(""),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Assign (or unassign) a channel owner by Twitch login."""
    require_csrf(request, csrf)
    channel = session.exec(
        select(Channel).where(Channel.slug == slug)
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    owner_login = owner_login.strip().lower()
    if owner_login:
        owner = session.exec(
            select(User).where(User.login == owner_login)
        ).first()
        if not owner:
            flash(request, f"User '{owner_login}' not found.", "error")
            return RedirectResponse("/admin", status_code=303)
        channel.owner_id = owner.id
        msg = f"Channel '{slug}' assigned to {owner_login}."
    else:
        channel.owner_id = None
        msg = f"Channel '{slug}' unassigned."
    session.add(channel)
    session.commit()
    log.info("admin %s: %s", admin.login, msg)
    flash(request, msg, "success")
    return RedirectResponse("/admin", status_code=303)


@router.post("/user/{login}/toggle-admin")
async def toggle_admin(
    login: str,
    request: Request,
    session: Session = Depends(get_session),
    admin: User = Depends(_require_admin),
    csrf: str = Form(...),
) -> RedirectResponse:
    """Toggle is_admin for a user; admin cannot demote themselves."""
    require_csrf(request, csrf)
    if login == admin.login:
        flash(request, "Cannot change your own admin status.", "error")
        return RedirectResponse("/admin", status_code=303)
    target = session.exec(select(User).where(User.login == login)).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.is_admin = not target.is_admin
    session.add(target)
    session.commit()
    state = "granted" if target.is_admin else "revoked"
    flash(request, f"Admin {state} for {login}.", "success")
    return RedirectResponse("/admin", status_code=303)
