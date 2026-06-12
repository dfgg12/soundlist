"""Tests for the public static-file allowlist and health check."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    """Return a TestClient that does not raise on server errors."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "path",
    [
        "/index.html",
        "/styles.css",
        "/app.js",
        "/marquee.html",
    ],
)
def test_public_files_served(client: TestClient, path: str) -> None:
    """Allowlisted board assets stay reachable."""
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/.env",
        "/soundlist.db",
        "/.git/config",
        "/uv.lock",
        "/pyproject.toml",
        "/app/settings.py",
        "/app/main.py",
    ],
)
def test_secrets_not_served(client: TestClient, path: str) -> None:
    """Secrets and source files must never be exposed over HTTP."""
    assert client.get(path).status_code == 404


def test_healthz_not_shadowed(client: TestClient) -> None:
    """Health check resolves rather than falling through to static."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
