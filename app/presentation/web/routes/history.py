"""Rotas de histórico de visualização."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.application.title_utils import normalize_watch_titles
from app.presentation.web import serializers as ser
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import HistoryAddRequest, ProgressRequest

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def get_history_list(
    state: AppState,
    dedupe: bool = True,
    mode: str = Query(
        "anime",
        description="anime = 1 card por anime; episode = 1 por episódio; all = bruto",
    ),
):
    hs = state.history
    mode = (mode or "anime").strip().lower()
    if mode == "all":
        entries = hs.get_all()
    elif mode == "episode" or not dedupe:
        entries = hs.get_all_unique_episodes()
    else:
        entries = hs.get_all_deduped()
    return {"items": [ser.history_entry(e) for e in entries]}


@router.post("")
def add_history(state: AppState, body: HistoryAddRequest):
    anime_t, ep_t, ep_n = normalize_watch_titles(
        body.anime_title, body.episode_title, body.episode_number
    )
    entry = state.history.add_entry(
        anime_title=anime_t,
        episode_title=ep_t,
        episode_number=ep_n,
        episode_link=body.episode_link,
        source_name=body.source_name,
        anime_image=body.anime_image,
        season_number=body.season_number,
        source_color=body.source_color,
        progress_seconds=body.progress_seconds,
        duration_seconds=body.duration_seconds,
    )
    return ser.history_entry(entry)


@router.post("/progress")
def update_progress(state: AppState, body: ProgressRequest):
    state.history.update_progress(
        body.episode_link, body.progress_seconds, body.duration_seconds
    )
    return {"ok": True}


@router.delete("")
def clear_history(state: AppState):
    state.history.clear_all()
    return {"ok": True}
