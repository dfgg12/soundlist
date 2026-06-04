"""Tests for CSRF helpers, flash messages, and panel CRUD routes (M3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import app.db as db_module
import app.panel as panel_module
from app.auth import current_user, require_channel_access, require_user
from app.csrf import csrf_token, require_csrf
from app.flash import flash, get_flashes
from app.main import app
from app.models import Channel, ChannelSound, Sound, User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Isolated SQLite engine for panel tests."""
    url = f"sqlite:///{tmp_path / 'test_panel.db'}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    return eng


@pytest.fixture()
def session(db):
    """Open session on the test engine."""
    with Session(db) as s:
        yield s


@pytest.fixture()
def test_user(session):
    user = User(twitch_id="u1", login="tester", display_name="Tester")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def test_channel(session, test_user):
    ch = Channel(
        slug="testchan",
        display_name="Test Chan",
        owner_id=test_user.id,
    )
    session.add(ch)
    session.commit()
    session.refresh(ch)
    return ch


@pytest.fixture()
def client(db, test_user, test_channel, monkeypatch):
    """TestClient with auth dependencies overridden and CSRF bypassed."""
    app.dependency_overrides[current_user] = lambda: test_user
    app.dependency_overrides[require_user] = lambda: test_user
    app.dependency_overrides[require_channel_access] = lambda: test_channel

    monkeypatch.setattr(panel_module, "require_csrf", lambda req, tok: None)

    yield TestClient(app, raise_server_exceptions=True)

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# CSRF unit tests
# ---------------------------------------------------------------------------


class _FakeSession(dict):
    """Dict that also supports attribute-style session access."""


class _FakeRequest:
    def __init__(self):
        self.session: dict = {}


def test_csrf_token_creates_on_first_call():
    req = _FakeRequest()
    token = csrf_token(req)
    assert token
    assert req.session["csrf_token"] == token


def test_csrf_token_stable_across_calls():
    req = _FakeRequest()
    t1 = csrf_token(req)
    t2 = csrf_token(req)
    assert t1 == t2


def test_require_csrf_passes_matching_token():
    req = _FakeRequest()
    req.session["csrf_token"] = "good-token"
    require_csrf(req, "good-token")  # no exception


def test_require_csrf_rejects_wrong_token():
    req = _FakeRequest()
    req.session["csrf_token"] = "real-token"
    with pytest.raises(Exception) as exc_info:
        require_csrf(req, "wrong-token")
    assert exc_info.value.status_code == 403


def test_require_csrf_rejects_missing_session_token():
    req = _FakeRequest()
    with pytest.raises(Exception) as exc_info:
        require_csrf(req, "any-token")
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Flash unit tests
# ---------------------------------------------------------------------------


def test_flash_queues_message():
    req = _FakeRequest()
    flash(req, "hello", "info")
    assert req.session["_flash"] == [{"msg": "hello", "level": "info"}]


def test_get_flashes_consumes():
    req = _FakeRequest()
    flash(req, "msg1", "info")
    flash(req, "msg2", "error")
    result = get_flashes(req)
    assert len(result) == 2
    assert result[0]["msg"] == "msg1"
    assert req.session["_flash"] == []


def test_get_flashes_empty():
    req = _FakeRequest()
    assert get_flashes(req) == []


# ---------------------------------------------------------------------------
# Dashboard (T3.2)
# ---------------------------------------------------------------------------


def test_dashboard_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Test Chan" in resp.content


def test_dashboard_shows_channel_link(client):
    resp = client.get("/")
    assert b"/c/testchan" in resp.content


# ---------------------------------------------------------------------------
# Channel editor GET (T3.3)
# ---------------------------------------------------------------------------


def test_channel_editor_renders(client):
    resp = client.get("/c/testchan")
    assert resp.status_code == 200
    assert b"Test Chan" in resp.content
    assert b"Add trigger" in resp.content


def test_channel_editor_shows_existing_trigger(client, session, test_channel):
    sound = Sound(
        name="bruh", url="https://example.com/bruh.mp3", created_by=1
    )
    session.add(sound)
    session.commit()
    session.refresh(sound)
    cs = ChannelSound(
        channel_id=test_channel.id,
        sound_id=sound.id,
        trigger_word="!bruh",
        chance="100%",
    )
    session.add(cs)
    session.commit()
    resp = client.get("/c/testchan")
    assert b"!bruh" in resp.content


# ---------------------------------------------------------------------------
# Add trigger (T3.4)
# ---------------------------------------------------------------------------


def test_add_sound_creates_trigger(client, session, test_channel):
    resp = client.post(
        "/c/testchan/sound",
        data={
            "trigger_word": "!hello",
            "sound_mode": "new",
            "sound_name": "hello",
            "sound_url": "https://example.com/hello.mp3",
            "chance": "100%",
            "trigger_cooldown": "0",
            "csrf": "ignored",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cs = session.exec(
        __import__("sqlmodel").select(ChannelSound).where(
            ChannelSound.trigger_word == "!hello"
        )
    ).first()
    assert cs is not None
    assert cs.channel_id == test_channel.id


def test_add_sound_rejects_duplicate_trigger(client, session, test_channel):
    sound = Sound(name="dup", url="https://example.com/dup.mp3", created_by=1)
    session.add(sound)
    session.commit()
    session.refresh(sound)
    cs = ChannelSound(
        channel_id=test_channel.id,
        sound_id=sound.id,
        trigger_word="!dup",
        chance="100%",
    )
    session.add(cs)
    session.commit()
    resp = client.post(
        "/c/testchan/sound",
        data={
            "trigger_word": "!dup",
            "sound_mode": "new",
            "sound_url": "https://example.com/dup.mp3",
            "chance": "100%",
            "trigger_cooldown": "0",
            "csrf": "ignored",
        },
        follow_redirects=True,
    )
    assert b"already exists" in resp.content


def test_add_sound_rejects_missing_url(client):
    resp = client.post(
        "/c/testchan/sound",
        data={
            "trigger_word": "!missing",
            "sound_mode": "new",
            "sound_name": "",
            "sound_url": "",
            "chance": "100%",
            "trigger_cooldown": "0",
            "csrf": "ignored",
        },
        follow_redirects=True,
    )
    assert b"URL is required" in resp.content


def test_add_sound_links_existing(client, session, test_channel):
    sound = Sound(
        name="shared", url="https://example.com/shared.mp3", created_by=1
    )
    session.add(sound)
    session.commit()
    session.refresh(sound)
    resp = client.post(
        "/c/testchan/sound",
        data={
            "trigger_word": "!shared",
            "sound_mode": "existing",
            "sound_id": str(sound.id),
            "chance": "100%",
            "trigger_cooldown": "0",
            "csrf": "ignored",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    cs = session.exec(
        __import__("sqlmodel").select(ChannelSound).where(
            ChannelSound.trigger_word == "!shared"
        )
    ).first()
    assert cs is not None
    assert cs.sound_id == sound.id


# ---------------------------------------------------------------------------
# Edit trigger (T3.5)
# ---------------------------------------------------------------------------


def _make_cs(session, test_channel):
    sound = Sound(
        name="editsnd", url="https://example.com/e.mp3", created_by=1
    )
    session.add(sound)
    session.commit()
    session.refresh(sound)
    cs = ChannelSound(
        channel_id=test_channel.id,
        sound_id=sound.id,
        trigger_word="!edit",
        chance="100%",
        enabled=True,
    )
    session.add(cs)
    session.commit()
    session.refresh(cs)
    return cs


def test_edit_sound_updates_fields(client, session, test_channel):
    cs = _make_cs(session, test_channel)
    resp = client.post(
        f"/c/testchan/sound/{cs.id}",
        data={
            "trigger_word": "!edited",
            "volume": "0.8",
            "chance": "50%",
            "trigger_cooldown": "5",
            "csrf": "ignored",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    session.refresh(cs)
    assert cs.trigger_word == "!edited"
    assert abs(cs.volume - 0.8) < 1e-9
    assert cs.chance == "50%"
    assert cs.trigger_cooldown == 5


def test_edit_sound_unchecked_enabled_disables(client, session, test_channel):
    cs = _make_cs(session, test_channel)
    # No 'enabled' key in form data = checkbox unchecked
    resp = client.post(
        f"/c/testchan/sound/{cs.id}",
        data={
            "trigger_word": "!edit",
            "chance": "100%",
            "trigger_cooldown": "0",
            "csrf": "ignored",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    session.refresh(cs)
    assert cs.enabled is False


# ---------------------------------------------------------------------------
# Delete trigger (T3.5)
# ---------------------------------------------------------------------------


def test_delete_sound_removes_trigger(client, session, test_channel):
    cs = _make_cs(session, test_channel)
    cs_id = cs.id
    resp = client.post(
        f"/c/testchan/sound/{cs_id}/delete",
        data={"csrf": "ignored"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    gone = session.exec(
        select(ChannelSound).where(ChannelSound.id == cs_id)
    ).first()
    assert gone is None


def test_delete_sound_404_for_wrong_channel(
    client, session, test_channel
):
    other_chan = Channel(slug="other", display_name="Other")
    session.add(other_chan)
    session.commit()
    session.refresh(other_chan)
    sound = Sound(
        name="othersnd", url="https://example.com/o.mp3", created_by=1
    )
    session.add(sound)
    session.commit()
    session.refresh(sound)
    cs = ChannelSound(
        channel_id=other_chan.id,
        sound_id=sound.id,
        trigger_word="!other",
        chance="100%",
    )
    session.add(cs)
    session.commit()
    session.refresh(cs)
    resp = client.post(
        f"/c/testchan/sound/{cs.id}/delete",
        data={"csrf": "ignored"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Toggle trigger (T3.5)
# ---------------------------------------------------------------------------


def test_toggle_sound_flips_enabled(client, session, test_channel):
    cs = _make_cs(session, test_channel)
    assert cs.enabled is True
    client.post(
        f"/c/testchan/sound/{cs.id}/toggle",
        data={"csrf": "ignored"},
        follow_redirects=False,
    )
    session.refresh(cs)
    assert cs.enabled is False
    # Toggle again
    client.post(
        f"/c/testchan/sound/{cs.id}/toggle",
        data={"csrf": "ignored"},
        follow_redirects=False,
    )
    session.refresh(cs)
    assert cs.enabled is True
