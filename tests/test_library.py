"""Tests for the shared sound library routes (M4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import app.db as db_module
import app.library as library_module
from app.auth import require_user
from app.main import app
from app.models import Channel, ChannelSound, Sound, SoundClip, User


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Isolated SQLite engine for library tests."""
    url = f"sqlite:///{tmp_path / 'test_library.db'}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    return eng


@pytest.fixture()
def session(db):
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
def client(db, test_user, monkeypatch):
    """TestClient with auth overridden and CSRF bypassed."""
    app.dependency_overrides[require_user] = lambda: test_user
    monkeypatch.setattr(library_module, "require_csrf", lambda req, tok: None)
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()


def _add_sound(session, name="snd", url="https://example.com/a.mp3"):
    sound = Sound(name=name, url=url, created_by=1)
    session.add(sound)
    session.commit()
    session.refresh(sound)
    return sound


def _link(session, channel_slug, sound, trigger="!t"):
    ch = Channel(slug=channel_slug, display_name=channel_slug)
    session.add(ch)
    session.commit()
    session.refresh(ch)
    cs = ChannelSound(
        channel_id=ch.id,
        sound_id=sound.id,
        trigger_word=trigger,
        chance="100%",
    )
    session.add(cs)
    session.commit()
    return cs


# ---------------------------------------------------------------------------
# Browse / search (T4.1)
# ---------------------------------------------------------------------------


def test_library_lists_assets(client, session):
    _add_sound(session, name="bruh")
    resp = client.get("/library")
    assert resp.status_code == 200
    assert b"bruh" in resp.content


def test_library_search_filters(client, session):
    _add_sound(session, name="apple")
    _add_sound(session, name="banana")
    resp = client.get("/library?q=app")
    assert b"apple" in resp.content
    assert b"banana" not in resp.content


def test_library_shows_usage_count(client, session):
    sound = _add_sound(session, name="shared")
    _link(session, "chan1", sound)
    resp = client.get("/library")
    assert resp.status_code == 200
    # count column renders the numeric usage count
    assert b'style="text-align:center">1<' in resp.content


# ---------------------------------------------------------------------------
# Create asset (T4.2)
# ---------------------------------------------------------------------------


def test_create_single_asset(client, session):
    resp = client.post(
        "/library",
        data={
            "name": "newsnd",
            "url": "https://example.com/new.mp3",
            "default_volume": "0.7",
            "csrf": "x",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    s = session.exec(select(Sound).where(Sound.name == "newsnd")).first()
    assert s is not None
    assert s.is_random is False
    assert s.url == "https://example.com/new.mp3"
    assert abs(s.default_volume - 0.7) < 1e-9


def test_create_random_asset_with_clips(client, session):
    resp = client.post(
        "/library",
        data={
            "name": "randsnd",
            "is_random": "on",
            "default_volume": "0.5",
            "clip_url": [
                "https://example.com/1.mp3",
                "https://example.com/2.mp3",
            ],
            "clip_volume": ["0.5", "0.5"],
            "clip_chance": ["100%", "100%"],
            "csrf": "x",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    s = session.exec(select(Sound).where(Sound.name == "randsnd")).first()
    assert s is not None
    assert s.is_random is True
    clips = session.exec(
        select(SoundClip).where(SoundClip.sound_id == s.id)
    ).all()
    assert len(clips) == 2


def test_create_rejects_duplicate_name(client, session):
    _add_sound(session, name="dup")
    resp = client.post(
        "/library",
        data={"name": "dup", "url": "https://x/d.mp3", "csrf": "x"},
        follow_redirects=True,
    )
    assert b"already taken" in resp.content


def test_create_single_requires_url(client):
    resp = client.post(
        "/library",
        data={"name": "nourl", "csrf": "x"},
        follow_redirects=True,
    )
    assert b"URL is required" in resp.content


def test_create_random_requires_clip(client):
    resp = client.post(
        "/library",
        data={"name": "empty", "is_random": "on", "csrf": "x"},
        follow_redirects=True,
    )
    assert b"at least one clip" in resp.content


# ---------------------------------------------------------------------------
# Edit asset (T4.4)
# ---------------------------------------------------------------------------


def test_edit_url_propagates(client, session):
    sound = _add_sound(session, name="prop", url="https://old/a.mp3")
    _link(session, "chanp", sound)
    resp = client.post(
        f"/library/{sound.id}",
        data={
            "name": "prop",
            "url": "https://new/a.mp3",
            "default_volume": "0.5",
            "csrf": "x",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    session.refresh(sound)
    assert sound.url == "https://new/a.mp3"


def test_edit_404_for_missing(client):
    resp = client.post(
        "/library/9999",
        data={"name": "x", "url": "https://x/x.mp3", "csrf": "x"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete asset (T4.5)
# ---------------------------------------------------------------------------


def test_delete_unused_asset(client, session):
    sound = _add_sound(session, name="gone")
    sid = sound.id
    resp = client.post(
        f"/library/{sid}/delete", data={"csrf": "x"}, follow_redirects=False
    )
    assert resp.status_code == 303
    gone = session.exec(select(Sound).where(Sound.id == sid)).first()
    assert gone is None


def test_delete_in_use_blocked(client, session):
    sound = _add_sound(session, name="busy")
    _link(session, "chanb", sound)
    resp = client.post(
        f"/library/{sound.id}/delete",
        data={"csrf": "x"},
        follow_redirects=True,
    )
    assert b"Cannot delete" in resp.content
    assert b"chanb" in resp.content
    assert session.get(Sound, sound.id) is not None
