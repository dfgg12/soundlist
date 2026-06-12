"""SQLModel ORM models - canonical SQLite schema."""

from datetime import UTC, datetime

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy import DateTime as SADateTime
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class User(SQLModel, table=True):
    """Authenticated Twitch user with optional admin privileges."""

    id: int | None = Field(default=None, primary_key=True)
    twitch_id: str = Field(unique=True, index=True)
    login: str = Field(unique=True, index=True)
    display_name: str
    avatar_url: str = ""
    is_admin: bool = False
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(SADateTime(timezone=True), default=_utcnow),
    )

    owned_channels: list["Channel"] = Relationship(back_populates="owner")
    created_sounds: list["Sound"] = Relationship(back_populates="creator")


class Channel(SQLModel, table=True):
    """A streamer's soundboard, identified by its slug."""

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    display_name: str
    owner_id: int | None = Field(
        default=None, foreign_key="user.id", index=True
    )
    avatar_url: str = ""
    is_sub_board: bool = False
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(SADateTime(timezone=True), default=_utcnow),
    )

    owner: User | None = Relationship(back_populates="owned_channels")
    channel_sounds: list["ChannelSound"] = Relationship(
        back_populates="channel"
    )


class Sound(SQLModel, table=True):
    """Shared audio asset in the library; may have multiple clips."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    default_volume: float = 0.5
    is_random: bool = False
    # Single-clip URL; None when is_random=True (use clips instead)
    url: str | None = None
    created_by: int | None = Field(
        default=None, foreign_key="user.id", index=True
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(SADateTime(timezone=True), default=_utcnow),
    )

    creator: User | None = Relationship(back_populates="created_sounds")
    clips: list["SoundClip"] = Relationship(back_populates="sound")
    channel_sounds: list["ChannelSound"] = Relationship(
        back_populates="sound"
    )


class SoundClip(SQLModel, table=True):
    """One weighted clip belonging to a random Sound."""

    id: int | None = Field(default=None, primary_key=True)
    sound_id: int = Field(foreign_key="sound.id", index=True)
    url: str
    volume: float
    # Stored as string to preserve legacy format exactly e.g. "3.3%"
    chance: str

    sound: Sound | None = Relationship(back_populates="clips")


class IconTrigger(SQLModel, table=True):
    """Global mapping from a trigger word to an emote icon URL."""

    id: int | None = Field(default=None, primary_key=True)
    trigger_word: str = Field(unique=True, index=True)
    icon_url: str
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(SADateTime(timezone=True), default=_utcnow),
    )


class ChannelSound(SQLModel, table=True):
    """A trigger word wired to a Sound on a specific Channel."""

    __table_args__ = (UniqueConstraint("channel_id", "trigger_word"),)

    id: int | None = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="channel.id", index=True)
    sound_id: int = Field(foreign_key="sound.id", index=True)
    trigger_word: str
    # None -> inherit Sound.default_volume at serialization time
    volume: float | None = None
    # Stored as string to preserve legacy format exactly e.g. "100%"
    chance: str = "100%"
    trigger_cooldown: int = 0
    enabled: bool = True
    position: int = 0

    channel: Channel | None = Relationship(back_populates="channel_sounds")
    sound: Sound | None = Relationship(back_populates="channel_sounds")
