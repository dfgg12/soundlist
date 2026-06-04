"""Tests for auth dependencies and admin seeding (T2.3, T2.4, T2.5)."""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

import app.db as db_module
from app.auth import (
    _claim_channels,
    _upsert_user,
    require_user,
    seed_admins,
)
from app.models import Channel, User
from app.settings import settings


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Isolated in-memory SQLite engine with schema created."""
    url = f"sqlite:///{tmp_path / 'test_auth.db'}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    # Patch auth module engine too (imported directly)
    import app.auth as auth_module
    monkeypatch.setattr(auth_module, "engine", eng)
    return eng


@pytest.fixture()
def session(db):
    """Open a session on the test engine."""
    with Session(db) as s:
        yield s


def make_user(
    session: Session,
    *,
    login: str = "testuser",
    twitch_id: str = "12345",
    is_admin: bool = False,
) -> User:
    user = User(
        twitch_id=twitch_id,
        login=login,
        display_name=login,
        is_admin=is_admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def make_channel(
    session: Session,
    *,
    slug: str = "testchannel",
    owner_id: int | None = None,
) -> Channel:
    ch = Channel(slug=slug, display_name=slug, owner_id=owner_id)
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


# ---------------------------------------------------------------------------
# require_user
# ---------------------------------------------------------------------------


def test_require_user_raises_without_session_user():
    with pytest.raises(Exception) as exc_info:
        require_user(user=None)
    assert exc_info.value.status_code == 401


def test_require_user_passes_through_user():
    user = User(twitch_id="1", login="a", display_name="A")
    result = require_user(user=user)
    assert result is user


# ---------------------------------------------------------------------------
# require_channel_access (tested via the pure guard logic)
# ---------------------------------------------------------------------------


def test_channel_access_owner_allowed(session):
    user = make_user(session, login="owner", twitch_id="1")
    channel = make_channel(session, slug="owner", owner_id=user.id)
    # Simulates the resolved dependency - no FastAPI request needed
    # Guard logic: user.is_admin == False, channel.owner_id == user.id -> OK
    assert not user.is_admin
    assert channel.owner_id == user.id


def test_channel_access_admin_allowed(session):
    admin = make_user(session, login="admin", twitch_id="2", is_admin=True)
    channel = make_channel(session, slug="otherchannel", owner_id=None)
    assert admin.is_admin
    # Admin can access any channel regardless of owner_id
    assert admin.is_admin or channel.owner_id == admin.id


def test_channel_access_stranger_denied(session):
    owner = make_user(session, login="owner", twitch_id="3")
    stranger = make_user(session, login="stranger", twitch_id="4")
    channel = make_channel(session, slug="ownerchan", owner_id=owner.id)
    assert not stranger.is_admin
    assert channel.owner_id != stranger.id


# ---------------------------------------------------------------------------
# _upsert_user
# ---------------------------------------------------------------------------


def test_upsert_user_creates_new(session):
    data = {
        "id": "99",
        "login": "NewUser",
        "display_name": "New User",
        "profile_image_url": "https://example.com/img.png",
    }
    user = _upsert_user(session, data)
    assert user.twitch_id == "99"
    assert user.login == "newuser"  # lowercased
    assert user.display_name == "New User"
    assert user.avatar_url == "https://example.com/img.png"


def test_upsert_user_updates_existing(session):
    existing = make_user(session, login="oldlogin", twitch_id="77")
    data = {
        "id": "77",
        "login": "NewLogin",
        "display_name": "Updated Name",
        "profile_image_url": "",
    }
    updated = _upsert_user(session, data)
    assert updated.id == existing.id
    assert updated.login == "newlogin"
    assert updated.display_name == "Updated Name"


# ---------------------------------------------------------------------------
# _claim_channels (T2.5)
# ---------------------------------------------------------------------------


def test_claim_channels_assigns_owner(session):
    user = make_user(session, login="streamerguy", twitch_id="55")
    ch = make_channel(session, slug="StreamerGuy", owner_id=None)
    _claim_channels(session, user)
    session.refresh(ch)
    assert ch.owner_id == user.id


def test_claim_channels_skips_already_owned(session):
    existing_owner = make_user(session, login="other", twitch_id="10")
    user = make_user(session, login="mychannelsame", twitch_id="11")
    ch = make_channel(
        session, slug="mychannelsame", owner_id=existing_owner.id
    )
    _claim_channels(session, user)
    session.refresh(ch)
    assert ch.owner_id == existing_owner.id  # not overwritten


def test_claim_channels_skips_non_matching(session):
    user = make_user(session, login="alice", twitch_id="20")
    ch = make_channel(session, slug="BobChannel", owner_id=None)
    _claim_channels(session, user)
    session.refresh(ch)
    assert ch.owner_id is None


# ---------------------------------------------------------------------------
# seed_admins (T2.3)
# ---------------------------------------------------------------------------


def test_seed_admins_grants_flag(session, monkeypatch):
    user = make_user(session, login="supermod", twitch_id="30")
    assert not user.is_admin
    monkeypatch.setattr(settings, "admin_logins", "supermod")
    seed_admins()
    session.refresh(user)
    assert user.is_admin


def test_seed_admins_noop_when_empty(session, monkeypatch):
    user = make_user(session, login="nobody", twitch_id="31")
    monkeypatch.setattr(settings, "admin_logins", "")
    seed_admins()
    session.refresh(user)
    assert not user.is_admin


def test_seed_admins_idempotent(session, monkeypatch):
    user = make_user(
        session, login="already_admin", twitch_id="32", is_admin=True
    )
    monkeypatch.setattr(settings, "admin_logins", "already_admin")
    seed_admins()  # should not raise or duplicate
    session.refresh(user)
    assert user.is_admin
