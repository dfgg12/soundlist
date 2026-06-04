"""Tests for the import_json importer helpers and smoke test."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=wrong-import-position
from app.models import Channel, ChannelSound, Sound, SoundClip
from scripts.import_json import (
    _equal_chance,
    _simple_urls_to_key,
    _unique_name,
    _url_stem,
    _weighted_dicts_to_key,
    run_import,
)

# pylint: enable=wrong-import-position


# -------------------------------------------------------------------
# Pure helper tests
# -------------------------------------------------------------------


def test_url_stem_r2():
    assert _url_stem("https://pub-abc.r2.dev/HUH.ogg") == "HUH"


def test_url_stem_catbox():
    assert _url_stem("https://files.catbox.moe/yl7cd8.ogg") == "yl7cd8"


def test_equal_chance_2():
    assert _equal_chance(2) == "50%"


def test_equal_chance_4():
    assert _equal_chance(4) == "25%"


def test_equal_chance_3():
    assert _equal_chance(3) == "33.33%"


def test_unique_name_no_conflict():
    assert _unique_name("HUH", {"LMAO"}) == "HUH"


def test_unique_name_conflict():
    assert _unique_name("HUH", {"HUH"}) == "HUH_2"


def test_unique_name_multi_conflict():
    assert _unique_name("HUH", {"HUH", "HUH_2"}) == "HUH_3"


def test_simple_urls_to_key_order_independent():
    urls_a = ["https://example.com/a.ogg", "https://example.com/b.ogg"]
    urls_b = list(reversed(urls_a))
    assert _simple_urls_to_key(urls_a, 0.5) == _simple_urls_to_key(urls_b, 0.5)


def test_simple_vs_weighted_keys_differ():
    """Same URL set but weighted format should not match simple-random key."""
    urls = ["https://example.com/a.ogg", "https://example.com/b.ogg"]
    simple_key = _simple_urls_to_key(urls, 0.5)
    # weighted clips with different chance values
    clips = [
        {"clip": urls[0], "volume": 0.5, "chance": "10%"},
        {"clip": urls[1], "volume": 0.5, "chance": "90%"},
    ]
    weighted_key = _weighted_dicts_to_key(clips)
    assert simple_key != weighted_key


# -------------------------------------------------------------------
# Integration smoke test: import real lists into in-memory SQLite
# -------------------------------------------------------------------



LISTS_DIR = Path(__file__).parent.parent / "lists"


@pytest.mark.skipif(
    not LISTS_DIR.exists(),
    reason="lists/ directory not present",
)
def test_import_counts(tmp_engine):
    """Import all lists and verify DB row counts are reasonable."""
    run_import(LISTS_DIR)

    with Session(tmp_engine) as s:
        channels = s.exec(select(Channel)).all()
        sounds = s.exec(select(Sound)).all()
        channel_sounds = s.exec(select(ChannelSound)).all()

        assert len(channels) == 24
        # Dedup: fewer sounds than raw triggers
        assert len(sounds) < len(channel_sounds)
        # All 663 raw triggers present (minus 1 dup KEKW in PuertoRicanPup)
        assert len(channel_sounds) == 662


@pytest.mark.skipif(
    not LISTS_DIR.exists(),
    reason="lists/ directory not present",
)
def test_import_idempotent(tmp_engine):
    """Running import twice must not change row counts."""
    run_import(LISTS_DIR)

    with Session(tmp_engine) as s:
        cs_count_1 = len(s.exec(select(ChannelSound)).all())
        snd_count_1 = len(s.exec(select(Sound)).all())

    run_import(LISTS_DIR)

    with Session(tmp_engine) as s:
        cs_count_2 = len(s.exec(select(ChannelSound)).all())
        snd_count_2 = len(s.exec(select(Sound)).all())

    assert cs_count_1 == cs_count_2
    assert snd_count_1 == snd_count_2


@pytest.mark.skipif(
    not LISTS_DIR.exists(),
    reason="lists/ directory not present",
)
def test_shared_sounds_dedup(tmp_engine):
    """Sounds shared across channels use a single DB row."""
    run_import(LISTS_DIR)

    with Session(tmp_engine) as s:
        # "LMAO.ogg" appears in many channels - should be one Sound row
        lmao_sounds = s.exec(
            select(Sound).where(
                Sound.url.like("%LMAO.ogg")  # type: ignore[union-attr]
            )
        ).all()
        assert len(lmao_sounds) == 1

        # That one Sound should link to multiple ChannelSounds
        links = s.exec(
            select(ChannelSound).where(
                ChannelSound.sound_id == lmao_sounds[0].id
            )
        ).all()
        assert len(links) > 1


@pytest.mark.skipif(
    not LISTS_DIR.exists(),
    reason="lists/ directory not present",
)
def test_avatar_urls_populated(tmp_engine):
    """Channels that appear in avatars.json have avatar_url set."""
    run_import(LISTS_DIR)

    with Session(tmp_engine) as s:
        amedoll = s.exec(
            select(Channel).where(Channel.slug == "Amedoll")
        ).first()
        assert amedoll is not None
        assert amedoll.avatar_url.startswith("https://")


@pytest.mark.skipif(
    not LISTS_DIR.exists(),
    reason="lists/ directory not present",
)
def test_sub_board_flag(tmp_engine):
    """RadiantSoul_Tv_Sub must have is_sub_board=True."""
    run_import(LISTS_DIR)

    with Session(tmp_engine) as s:
        sub = s.exec(
            select(Channel).where(Channel.slug == "RadiantSoul_Tv_Sub")
        ).first()
        assert sub is not None
        assert sub.is_sub_board is True


@pytest.mark.skipif(
    not LISTS_DIR.exists(),
    reason="lists/ directory not present",
)
def test_weighted_clips_preserved(tmp_engine):
    """ssoulDoinDaCatJiggleThing clips are stored with correct data."""
    run_import(LISTS_DIR)

    with Session(tmp_engine) as s:
        # The sound name comes from the trigger_word on first encounter
        sound = s.exec(
            select(Sound).where(
                Sound.name == "ssoulDoinDaCatJiggleThing"
            )
        ).first()
        assert sound is not None
        assert sound.is_random is True

        clips = s.exec(
            select(SoundClip).where(SoundClip.sound_id == sound.id)
        ).all()
        assert len(clips) == 5
        chances = {c.chance for c in clips}
        # Weighted - should have varied chances, not all equal
        assert len(chances) > 1
