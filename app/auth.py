"""Twitch OAuth routes and authentication dependencies."""

from __future__ import annotations

import logging

import httpx
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import engine, get_session
from app.models import Channel, User
from app.settings import settings

log = logging.getLogger(__name__)

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="twitch",
    client_id=settings.twitch_client_id,
    client_secret=settings.twitch_client_secret,
    authorize_url="https://id.twitch.tv/oauth2/authorize",
    access_token_url="https://id.twitch.tv/oauth2/token",
    client_kwargs={"scope": "user:read:email"},
)


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect browser to Twitch OAuth consent page."""
    return await oauth.twitch.authorize_redirect(
        request, settings.twitch_redirect_uri
    )


async def _fetch_twitch_user(access_token: str) -> dict:
    """Return the Twitch helix/users record for the given bearer token."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": settings.twitch_client_id,
            },
        )
    if resp.status_code != 200:
        log.error(
            "twitch helix/users returned %s: %s", resp.status_code, resp.text
        )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        raise ValueError("empty user data from Twitch API")
    return data[0]


def _upsert_user(session: Session, twitch_data: dict) -> User:
    """Create or update a User row from Twitch profile data."""
    twitch_id: str = twitch_data["id"]
    twitch_login: str = twitch_data["login"].lower()
    user = session.exec(
        select(User).where(User.twitch_id == twitch_id)
    ).first()
    if user is None:
        user = User(
            twitch_id=twitch_id,
            login=twitch_login,
            display_name=twitch_data["display_name"],
            avatar_url=twitch_data.get("profile_image_url", ""),
        )
        log.info("new user: %s", twitch_login)
    else:
        user.login = twitch_login
        user.display_name = twitch_data["display_name"]
        user.avatar_url = twitch_data.get("profile_image_url", "")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _claim_channels(session: Session, user: User) -> None:
    """Assign owner_id on unowned channels whose slug matches user login."""
    unclaimed = session.exec(
        select(Channel).where(
            Channel.owner_id.is_(None),  # type: ignore[union-attr]
            func.lower(Channel.slug) == user.login,
        )
    ).all()
    for channel in unclaimed:
        channel.owner_id = user.id
        session.add(channel)
        log.info("claimed channel %s for %s", channel.slug, user.login)
    if unclaimed:
        session.commit()


@router.get("/auth/callback")
async def auth_callback(
    request: Request, session: Session = Depends(get_session)
) -> RedirectResponse:
    """Handle Twitch OAuth callback, upsert user, and start session."""
    try:
        token = await oauth.twitch.authorize_access_token(request)
    except OAuthError as exc:
        log.warning("oauth error: %s", exc)
        raise HTTPException(status_code=400, detail="OAuth failed") from exc
    access_token = token.get("access_token")
    if not access_token:
        log.error("token dict missing access_token: %s", list(token.keys()))
        raise HTTPException(status_code=502, detail="No access token from Twitch")
    try:
        twitch_data = await _fetch_twitch_user(access_token)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.error("twitch user fetch failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Failed to fetch Twitch profile"
        ) from exc
    user = _upsert_user(session, twitch_data)
    _claim_channels(session, user)
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear session and redirect to home."""
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# ---------------------------------------------------------------------------
# Auth dependencies (server-side only)
# ---------------------------------------------------------------------------


def current_user(
    request: Request, session: Session = Depends(get_session)
) -> User | None:
    """Return the logged-in User, or None for anonymous sessions."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return session.get(User, user_id)


def require_user(
    user: User | None = Depends(current_user),
) -> User:
    """Raise 401 if no authenticated user is in the session."""
    if user is None:
        raise HTTPException(status_code=401, detail="Login required")
    return user


async def require_channel_access(
    slug: str,
    user: User = Depends(require_user),
    session: Session = Depends(get_session),
) -> Channel:
    """Return Channel if user is admin or owner; raise 403 otherwise."""
    channel = session.exec(
        select(Channel).where(Channel.slug == slug)
    ).first()
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if not user.is_admin and channel.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return channel


# ---------------------------------------------------------------------------
# Admin seeding (called from startup)
# ---------------------------------------------------------------------------


def seed_admins() -> None:
    """Grant is_admin to any existing User whose login is in ADMIN_LOGINS."""
    logins = settings.admin_login_list
    if not logins:
        return
    with Session(engine) as session:
        users = session.exec(
            select(User).where(  # type: ignore[attr-defined]
                User.login.in_(logins)
            )
        ).all()
        for user in users:
            if not user.is_admin:
                user.is_admin = True
                session.add(user)
                log.info("seeded admin: %s", user.login)
        session.commit()
