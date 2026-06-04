"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from sqlmodel import SQLModel, create_engine

import app.db as db_module
import scripts.import_json as importer_module


@pytest.fixture()
def tmp_engine(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
):
    """Isolated SQLite engine; patches app.db and import_json engines."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    eng = create_engine(db_url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(db_module, "engine", eng)
    monkeypatch.setattr(importer_module, "engine", eng)
    return eng
