"""Rotas de favoritos (watch later)."""

from __future__ import annotations

import asyncio
from urllib.parse import unquote

from fastapi import APIRouter

from app.presentation.web import serializers as ser
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import WatchLaterAddRequest

router = APIRouter(prefix="/api/watch-later", tags=["watch-later"])


@router.get("")
async def get_watch_later(state: AppState):
    ws = state.watch_later
    entries = await asyncio.to_thread(ws.get_all)
    return {"items": [ser.watch_later_entry(e) for e in entries]}


@router.post("")
async def add_watch_later(state: AppState, body: WatchLaterAddRequest):
    entry = await asyncio.to_thread(
        state.watch_later.add_entry,
        anime_title=body.anime_title,
        anime_image=body.anime_image,
        source_name=body.source_name,
        source_link=body.source_link,
        source_color=body.source_color,
    )
    return ser.watch_later_entry(entry)


@router.delete("")
async def clear_watch_later(state: AppState):
    await asyncio.to_thread(state.watch_later.clear_all)
    return {"ok": True}


@router.delete("/{title}")
async def remove_watch_later(state: AppState, title: str):
    await asyncio.to_thread(state.watch_later.remove_entry, unquote(title))
    return {"ok": True}
