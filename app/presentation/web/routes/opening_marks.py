"""Rotas de marcação de fim de abertura (opening) por temporada."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.application.title_utils import normalize_watch_titles
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import OpeningMarkSaveRequest, OpeningMarkVoteRequest

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
    info = svc.get_mark_info(anime_title, season_number)
    return {
        "anime_title": anime_title,
        "season_number": season_number,
        "end_seconds": info["end_seconds"] if info else None,
        "has_mark": info is not None,
        "mark_id": info.get("mark_id") if info else None,
        "score": info.get("score", 0) if info else 0,
        "upvotes": info.get("upvotes", 0) if info else 0,
        "downvotes": info.get("downvotes", 0) if info else 0,
    }


@router.post("")
def save_opening_mark(state: AppState, body: OpeningMarkSaveRequest):
    """Salva (ou sobrescreve) a marcação de fim de abertura para um anime/temporada."""
    svc = state.opening_mark_service
    anime_title, _, _ = normalize_watch_titles(body.anime_title, "", "")
    info = svc.save_mark(anime_title, body.season_number, body.end_seconds)
    return {
        "anime_title": anime_title,
        "season_number": body.season_number,
        "end_seconds": body.end_seconds,
        "mark_id": info.get("mark_id") if info else None,
        "score": info.get("score", 0) if info else 0,
        "ok": True,
    }


@router.post("/vote")
def vote_opening_mark(state: AppState, body: OpeningMarkVoteRequest):
    try:
        return {"ok": True, **state.opening_mark_service.vote(body.mark_id, body.value)}
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
