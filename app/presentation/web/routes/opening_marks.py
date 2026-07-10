"""Rotas de marcação de fim de abertura (opening) por temporada."""

from __future__ import annotations

from fastapi import APIRouter

from app.application.title_utils import normalize_watch_titles
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import OpeningMarkSaveRequest

router = APIRouter(prefix="/api/opening-marks", tags=["opening-marks"])


@router.get("")
def get_opening_mark(
    state: AppState,
    anime_title: str,
    season_number: int = 1,
):
    """Retorna a marcação de fim de abertura para um anime/temporada."""
    svc = state.opening_mark_service
    anime_title, _, _ = normalize_watch_titles(anime_title, "", "")
    mark = svc.get_mark(anime_title, season_number)
    return {
        "anime_title": anime_title,
        "season_number": season_number,
        "end_seconds": mark,
        "has_mark": mark is not None,
    }


@router.post("")
def save_opening_mark(state: AppState, body: OpeningMarkSaveRequest):
    """Salva (ou sobrescreve) a marcação de fim de abertura para um anime/temporada."""
    svc = state.opening_mark_service
    anime_title, _, _ = normalize_watch_titles(body.anime_title, "", "")
    svc.save_mark(anime_title, body.season_number, body.end_seconds)
    return {
        "anime_title": anime_title,
        "season_number": body.season_number,
        "end_seconds": body.end_seconds,
        "ok": True,
    }
