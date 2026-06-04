"""Session-based flash messages."""

from __future__ import annotations

from starlette.requests import Request


def flash(request: Request, msg: str, level: str = "info") -> None:
    """Queue a flash message for display on the next response."""
    msgs: list[dict] = request.session.get("_flash", [])
    msgs.append({"msg": msg, "level": level})
    request.session["_flash"] = msgs


def get_flashes(request: Request) -> list[dict]:
    """Consume and return all queued flash messages."""
    msgs: list[dict] = request.session.get("_flash", [])
    request.session["_flash"] = []
    return msgs
