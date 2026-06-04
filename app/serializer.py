"""Serialize DB models to legacy JSON shapes for the public board."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models import Channel, ChannelSound, Sound, SoundClip

SoundField = str | list[str] | list[dict[str, Any]]


def _serialize_sound_field(
    sound: Sound, clips: list[SoundClip]
) -> SoundField:
    """Return the 'sound' field: str, URL list, or weighted-clip dict list."""
    if not sound.is_random:
        return sound.url or ""
    # All clips share the same volume+chance -> simple URL array
    if clips and len({(c.volume, c.chance) for c in clips}) == 1:
        return [c.url for c in clips]
    return [
        {"clip": c.url, "volume": c.volume, "chance": c.chance}
        for c in clips
    ]


def channel_to_dict(channel: Channel, session: Session) -> dict[str, Any]:
    """Return a channel's sounds in the legacy per-channel JSON shape."""
    channel_sounds = session.exec(
        select(ChannelSound)
        .where(ChannelSound.channel_id == channel.id)
        .order_by(ChannelSound.position, ChannelSound.id)
    ).all()

    sounds: list[dict[str, Any]] = []
    for cs in channel_sounds:
        sound = session.get(Sound, cs.sound_id)
        if sound is None:
            continue
        clips: list[SoundClip] = []
        if sound.is_random:
            clips = list(
                session.exec(
                    select(SoundClip)
                    .where(SoundClip.sound_id == sound.id)
                    .order_by(SoundClip.id)
                ).all()
            )
        volume = cs.volume if cs.volume is not None else sound.default_volume
        sounds.append({
            "trigger_word": cs.trigger_word,
            "sound": _serialize_sound_field(sound, clips),
            "volume": volume,
            "chance": cs.chance,
            "trigger_cooldown": cs.trigger_cooldown,
            "enabled": "true" if cs.enabled else "false",
        })

    return {"sounds": sounds}


def index_to_dict(channels: list[Channel]) -> dict[str, str]:
    """Return the channel index in the legacy index.json shape."""
    return {ch.slug: f"lists/{ch.slug}.json" for ch in channels}


def avatars_to_dict(channels: list[Channel]) -> dict[str, str]:
    """Return the avatars map in the legacy avatars.json shape."""
    return {ch.slug: ch.avatar_url for ch in channels if ch.avatar_url}
