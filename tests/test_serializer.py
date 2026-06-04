"""Unit tests for app.serializer - pure serialization logic."""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models import Channel, ChannelSound, Sound, SoundClip
from app.serializer import _serialize_sound_field, channel_to_dict


@pytest.fixture()
def session():
    """In-memory SQLite session, isolated per test."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# -------------------------------------------------------------------
# _serialize_sound_field
# -------------------------------------------------------------------


def test_single_sound_returns_url():
    url = "https://example.com/a.ogg"
    sound = Sound(name="a", default_volume=0.5, is_random=False, url=url)
    assert _serialize_sound_field(sound, []) == url


def test_simple_random_returns_url_list():
    sound = Sound(name="r", default_volume=0.5, is_random=True)
    clips = [
        SoundClip(url="a.ogg", volume=0.5, chance="50%"),
        SoundClip(url="b.ogg", volume=0.5, chance="50%"),
    ]
    assert _serialize_sound_field(sound, clips) == ["a.ogg", "b.ogg"]


def test_weighted_random_returns_clip_dicts():
    sound = Sound(name="w", default_volume=0.5, is_random=True)
    clips = [
        SoundClip(url="a.ogg", volume=0.2, chance="10%"),
        SoundClip(url="b.ogg", volume=0.8, chance="90%"),
    ]
    assert _serialize_sound_field(sound, clips) == [
        {"clip": "a.ogg", "volume": 0.2, "chance": "10%"},
        {"clip": "b.ogg", "volume": 0.8, "chance": "90%"},
    ]


# -------------------------------------------------------------------
# channel_to_dict
# -------------------------------------------------------------------


def _add_single_trigger(
    session: Session,
    channel: Channel,
    trigger_word: str,
    url: str,
    volume: float = 0.5,
    chance: str = "100%",
    cooldown: int = 0,
    enabled: bool = True,
    position: int = 0,
) -> None:
    sound = Sound(name=url, default_volume=volume, is_random=False, url=url)
    session.add(sound)
    session.flush()
    session.add(ChannelSound(
        channel_id=channel.id,
        sound_id=sound.id,
        trigger_word=trigger_word,
        volume=volume,
        chance=chance,
        trigger_cooldown=cooldown,
        enabled=enabled,
        position=position,
    ))
    session.flush()


def test_enabled_serialized_as_string_true(session):
    ch = Channel(slug="TestCh", display_name="TestCh")
    session.add(ch)
    session.flush()
    _add_single_trigger(session, ch, "X", "https://x.com/a.ogg", enabled=True)
    result = channel_to_dict(ch, session)
    assert result["sounds"][0]["enabled"] == "true"


def test_enabled_serialized_as_string_false(session):
    ch = Channel(slug="TestCh2", display_name="TestCh2")
    session.add(ch)
    session.flush()
    _add_single_trigger(session, ch, "X", "https://x.com/b.ogg", enabled=False)
    result = channel_to_dict(ch, session)
    assert result["sounds"][0]["enabled"] == "false"


def test_volume_fallback_to_sound_default(session):
    ch = Channel(slug="TestCh3", display_name="TestCh3")
    session.add(ch)
    session.flush()
    sound = Sound(name="fallback", default_volume=0.7, is_random=False,
                  url="https://x.com/c.ogg")
    session.add(sound)
    session.flush()
    session.add(ChannelSound(
        channel_id=ch.id, sound_id=sound.id, trigger_word="Y",
        volume=None, chance="100%", trigger_cooldown=0,
        enabled=True, position=0,
    ))
    session.flush()
    result = channel_to_dict(ch, session)
    assert result["sounds"][0]["volume"] == 0.7


def test_trigger_insertion_order_preserved(session):
    ch = Channel(slug="TestCh4", display_name="TestCh4")
    session.add(ch)
    session.flush()
    for i, word in enumerate(["Z", "A", "M"]):
        _add_single_trigger(
            session, ch, word, f"https://x.com/{word}.ogg", position=i
        )
    result = channel_to_dict(ch, session)
    assert [s["trigger_word"] for s in result["sounds"]] == ["Z", "A", "M"]


def test_chance_string_preserved(session):
    ch = Channel(slug="TestCh5", display_name="TestCh5")
    session.add(ch)
    session.flush()
    _add_single_trigger(
        session, ch, "X", "https://x.com/d.ogg", chance="33.33%"
    )
    result = channel_to_dict(ch, session)
    assert result["sounds"][0]["chance"] == "33.33%"
