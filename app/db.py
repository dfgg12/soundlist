"""Database engine and session factory."""

from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  # pylint: disable=unused-import
from app.settings import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=not settings.is_production,
)


def get_session():
    """Yield a database session; close on exit."""
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    """Create all tables that do not yet exist."""
    SQLModel.metadata.create_all(engine)
