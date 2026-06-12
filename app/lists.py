"""Read-only JSON list endpoints; legacy compatibility layer."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from app.db import get_session
from app.models import Channel, IconTrigger
from app.serializer import avatars_to_dict, channel_to_dict, index_to_dict

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/lists/index.json", include_in_schema=False)
def get_index(
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse:
    """Return the channel index in legacy index.json shape."""
    channels = list(session.exec(select(Channel).order_by(Channel.slug)).all())
    return JSONResponse(index_to_dict(channels))


@router.get("/lists/internals/avatars.json", include_in_schema=False)
def get_avatars(
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse:
    """Return the avatars map in legacy avatars.json shape."""
    channels = list(session.exec(select(Channel).order_by(Channel.slug)).all())
    return JSONResponse(avatars_to_dict(channels))


@router.get("/lists/internals/IconTriggers2.json", include_in_schema=False)
def get_icon_triggers(
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse:
    """Serve icon trigger mappings from DB in legacy JSON shape."""
    rows = session.exec(
        select(IconTrigger).order_by(IconTrigger.trigger_word)
    ).all()
    return JSONResponse({r.trigger_word: r.icon_url for r in rows})


@router.get("/lists/{slug}.json", include_in_schema=False)
def get_channel_list(
    slug: str,
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse:
    """Return a channel's sounds in legacy JSON shape, or 404."""
    channel = session.exec(
        select(Channel).where(Channel.slug == slug)
    ).first()
    if channel is None:
        raise HTTPException(
            status_code=404, detail=f"channel {slug!r} not found"
        )
    return JSONResponse(channel_to_dict(channel, session))
