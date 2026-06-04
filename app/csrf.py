"""CSRF token helpers for form submissions."""

from __future__ import annotations

import secrets

from fastapi import HTTPException
from starlette.requests import Request


def csrf_token(request: Request) -> str:
    """Return session CSRF token, creating it if absent."""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def require_csrf(request: Request, token: str) -> None:
    """Raise 403 if submitted CSRF token does not match the session."""
    session_token = request.session.get("csrf_token")
    if not session_token or not secrets.compare_digest(token, session_token):
        raise HTTPException(status_code=403, detail="CSRF check failed")
