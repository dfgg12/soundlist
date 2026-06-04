"""Importer: parse lists/*.json into SQLite DB. Idempotent."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=wrong-import-position
from app.db import create_db_and_tables, engine
from app.models import Channel, ChannelSound, Sound, SoundClip

# pylint: enable=wrong-import-position

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

_SoundRow = dict[str, Any]


# -------------------------------------------------------------------
# Name and key helpers
# -------------------------------------------------------------------


def _url_stem(url: str) -> str:
    """Return filename stem from a URL ('LOOKING' from '...LOOKING.ogg')."""
    return os.path.splitext(os.path.basename(url))[0]


def _unique_name(base: str, existing: set[str]) -> str:
    """Return base if not in existing, else base_2, base_3, ..."""
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def _equal_chance(count: int) -> str:
    """Return equal-distribution chance string for count clips."""
    return f"{round(100.0 / count, 2):g}%"


# Canonical cache key for a random sound already in the DB
def _clips_to_key(
    clips: list[SoundClip],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted((c.url, str(c.volume), c.chance) for c in clips))


# Key for a simple URL-list random sound (equal weights)
def _simple_urls_to_key(
    urls: list[str], volume: float
) -> tuple[tuple[str, str, str], ...]:
    n = len(urls)
    ch = _equal_chance(n)
    return tuple(sorted((u, str(volume), ch) for u in urls))


# Key for a weighted clip-dict random sound
def _weighted_dicts_to_key(
    clips: list[dict[str, Any]],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (c["clip"], str(c.get("volume", "")), str(c.get("chance", "")))
            for c in clips
        )
    )


# -------------------------------------------------------------------
# DB cache - pre-loaded for idempotency
# -------------------------------------------------------------------


class _Cache:
    """In-memory index of sounds already in the DB."""

    def __init__(self, session: Session) -> None:
        self.single: dict[str, Sound] = {}
        self.random: dict[tuple[tuple[str, str, str], ...], Sound] = {}
        self.names: set[str] = set()
        self._load(session)

    def _load(self, session: Session) -> None:
        for sound in session.exec(select(Sound)).all():
            self.names.add(sound.name)
            if not sound.is_random and sound.url:
                self.single[sound.url] = sound
            elif sound.is_random:
                clips = session.exec(
                    select(SoundClip).where(SoundClip.sound_id == sound.id)
                ).all()
                if clips:
                    self.random[_clips_to_key(list(clips))] = sound


# -------------------------------------------------------------------
# Sound get-or-create functions
# -------------------------------------------------------------------


def _get_or_create_single(
    session: Session,
    cache: _Cache,
    url: str,
    volume: float,
) -> Sound:
    if url in cache.single:
        return cache.single[url]

    name = _unique_name(_url_stem(url), cache.names)
    sound = Sound(name=name, default_volume=volume, is_random=False, url=url)
    session.add(sound)
    session.flush()
    cache.single[url] = sound
    cache.names.add(name)
    return sound


def _get_or_create_simple_random(
    session: Session,
    cache: _Cache,
    urls: list[str],
    volume: float,
    trigger_word: str,
) -> Sound:
    key = _simple_urls_to_key(urls, volume)
    if key in cache.random:
        return cache.random[key]

    name = _unique_name(trigger_word, cache.names)
    ch = _equal_chance(len(urls))
    sound = Sound(name=name, default_volume=volume, is_random=True, url=None)
    session.add(sound)
    session.flush()
    for url in urls:
        session.add(
            SoundClip(
                sound_id=sound.id, url=url, volume=volume, chance=ch
            )
        )
    cache.random[key] = sound
    cache.names.add(name)
    return sound


def _get_or_create_weighted_random(
    session: Session,
    cache: _Cache,
    clips: list[dict[str, Any]],
    trigger_word: str,
) -> Sound:
    key = _weighted_dicts_to_key(clips)
    if key in cache.random:
        return cache.random[key]

    default_vol = float(clips[0].get("volume", 0.5)) if clips else 0.5
    name = _unique_name(trigger_word, cache.names)
    sound = Sound(
        name=name, default_volume=default_vol, is_random=True, url=None
    )
    session.add(sound)
    session.flush()
    for c in clips:
        session.add(
            SoundClip(
                sound_id=sound.id,
                url=c["clip"],
                volume=float(c.get("volume", default_vol)),
                chance=str(c.get("chance", "100%")),
            )
        )
    cache.random[key] = sound
    cache.names.add(name)
    return sound


# -------------------------------------------------------------------
# Channel and ChannelSound upserts
# -------------------------------------------------------------------


def _upsert_channel(
    session: Session,
    slug: str,
    avatar_url: str,
) -> Channel:
    channel = session.exec(
        select(Channel).where(Channel.slug == slug)
    ).first()
    if channel is None:
        channel = Channel(
            slug=slug,
            display_name=slug,
            avatar_url=avatar_url,
            is_sub_board=slug.lower().endswith("_sub"),
        )
        session.add(channel)
        session.flush()
        log.info("  created channel %s", slug)
    elif channel.avatar_url != avatar_url and avatar_url:
        channel.avatar_url = avatar_url
    return channel


def _upsert_channel_sound(
    session: Session,
    channel: Channel,
    sound: Sound,
    row: _SoundRow,
    position: int,
) -> None:
    cs = session.exec(
        select(ChannelSound).where(
            ChannelSound.channel_id == channel.id,
            ChannelSound.trigger_word == row["trigger_word"],
        )
    ).first()

    enabled = str(row.get("enabled", "true")).lower() != "false"
    volume = float(row.get("volume", sound.default_volume))
    chance = str(row.get("chance", "100%"))
    cooldown = int(row.get("trigger_cooldown", 0))

    if cs is None:
        session.add(
            ChannelSound(
                channel_id=channel.id,
                sound_id=sound.id,
                trigger_word=row["trigger_word"],
                volume=volume,
                chance=chance,
                trigger_cooldown=cooldown,
                enabled=enabled,
                position=position,
            )
        )
    else:
        cs.sound_id = sound.id
        cs.volume = volume
        cs.chance = chance
        cs.trigger_cooldown = cooldown
        cs.enabled = enabled
        cs.position = position


# -------------------------------------------------------------------
# Per-channel import
# -------------------------------------------------------------------


def _import_channel(
    session: Session,
    cache: _Cache,
    slug: str,
    json_path: Path,
    avatar_url: str,
) -> int:
    """Import one channel JSON; return trigger count."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    rows: list[_SoundRow] = data.get("sounds", [])
    channel = _upsert_channel(session, slug, avatar_url)

    count = 0
    for position, row in enumerate(rows):
        snd_data = row.get("sound")
        volume = float(row.get("volume", 0.5))
        trigger = row.get("trigger_word", "")

        if isinstance(snd_data, str):
            sound = _get_or_create_single(session, cache, snd_data, volume)
        elif isinstance(snd_data, list) and snd_data:
            if isinstance(snd_data[0], dict):
                sound = _get_or_create_weighted_random(
                    session, cache, snd_data, trigger
                )
            else:
                sound = _get_or_create_simple_random(
                    session, cache, snd_data, volume, trigger
                )
        else:
            log.warning("skipping %s/%s: unknown sound format", slug, trigger)
            continue

        _upsert_channel_sound(session, channel, sound, row, position)
        count += 1

    return count


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------


def run_import(lists_dir: Path) -> None:
    """Import all channels from lists_dir into the DB."""
    create_db_and_tables()

    index_path = lists_dir / "index.json"
    if not index_path.exists():
        log.error("index.json not found at %s", index_path)
        sys.exit(1)

    index: dict[str, str] = json.loads(
        index_path.read_text(encoding="utf-8")
    )

    avatars_path = lists_dir / "internals" / "avatars.json"
    avatars: dict[str, str] = {}
    if avatars_path.exists():
        raw: dict[str, str] = json.loads(
            avatars_path.read_text(encoding="utf-8")
        )
        avatars = {k.lower(): v for k, v in raw.items()}
    else:
        log.warning("avatars.json not found at %s", avatars_path)

    with Session(engine) as session:
        cache = _Cache(session)
        log.info("loaded %d existing sounds from DB", len(cache.names))

        total_triggers = 0
        for slug, rel_path in index.items():
            json_path = lists_dir.parent / rel_path
            if not json_path.exists():
                log.warning("missing file for channel %s: %s", slug, json_path)
                continue
            avatar_url = avatars.get(slug.lower(), "")
            log.info("importing %s", slug)
            n = _import_channel(session, cache, slug, json_path, avatar_url)
            total_triggers += n
            log.info("  %d triggers", n)

        session.commit()

    log.info(
        "done - %d channels, %d triggers, %d sounds",
        len(index),
        total_triggers,
        len(cache.names),
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Import lists/*.json into the SQLite DB"
    )
    parser.add_argument(
        "--lists-dir",
        default="lists",
        help="path to the lists directory (default: lists)",
    )
    args = parser.parse_args()
    run_import(Path(args.lists_dir))


if __name__ == "__main__":
    main()
