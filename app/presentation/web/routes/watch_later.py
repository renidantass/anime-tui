"""Rotas de assistir depois (watch later)."""

from __future__ import annotations

from fastapi import APIRouter

from app.presentation.web import serializers as ser
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import WatchLaterAddRequest

router = APIRouter(prefix="/api/watch-later", tags=["watch-later"])


@router.get("")
def get_watch_later(state: AppState):
    ws = state.watch_later
    return {"items": [ser.watch_later_entry(e) for e in ws.get_all()]}


@router.post("")
def add_watch_later(state: AppState, body: WatchLaterAddRequest):
    entry = state.watch_later.add_entry(
        anime_title=body.anime_title,
        anime_image=body.anime_image,
        source_name=body.source_name,
        source_link=body.source_link,
        source_color=body.source_color,
    )
    return ser.watch_later_entry(entry)


@router.delete("")
def clear_watch_later(state: AppState):
    state.watch_later.clear_all()
    return {"ok": True}


@router.delete("/{title}")
def remove_watch_later(state: AppState, title: str):
    from urllib.parse import unquote

    state.watch_later.remove_entry(unquote(title))
    return {"ok": True}
