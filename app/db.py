"""Database engine and session factory."""

from __future__ import annotations

from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  # pylint: disable=unused-import
from app.settings import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=not settings.is_production,
)

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def get_session():
    """Yield a database session; close on exit."""
    with Session(engine) as session:
        yield session


def run_migrations() -> None:
    """Apply all pending Alembic migrations to head."""
    cfg = AlembicConfig(_ALEMBIC_INI)
    alembic_command.upgrade(cfg, "head")


def create_db_and_tables() -> None:
    """Create all tables without Alembic - used by tests only."""
    SQLModel.metadata.create_all(engine)
