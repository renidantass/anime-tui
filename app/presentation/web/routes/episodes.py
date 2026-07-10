"""Rotas de catálogo: episódios, busca, gêneros, metadados, calendário."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.application.dtos import GenreResolveItem
from app.presentation.web import serializers as ser
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import GenreResolveRequest

router = APIRouter(prefix="/api", tags=["catalog"])

PAGE = Query(1, ge=1)
PER_PAGE = Query(20, ge=1, le=40)
PER_PAGE_12 = Query(12, ge=1, le=40)


def _guard_anilist(result: dict) -> None:
    if result.get("error") and not result.get("items"):
        raise HTTPException(502, f"AniList indisponível: {result['error']}")


@router.get("/episodes")
def list_episodes(state: AppState):
    entries = state.service.get_last_episodes()
    return {"items": [ser.episode_entry(e) for e in entries]}


@router.get("/search")
def search(state: AppState, q: str = Query(..., min_length=1)):
    results = state.service.search_by(q.strip())
    return {"items": [ser.anime_entry(a) for a in results]}


@router.get("/genres")
def list_genres(state: AppState):
    items = state.service.get_genres()
    return {"items": items}


@router.get("/genres/catalog")
def genre_catalog(
    state: AppState,
    genre: str = Query(..., min_length=1),
    page: int = PAGE,
    per_page: int = PER_PAGE,
):
    result = state.service.catalog_by_genre(genre.strip(), page=page, per_page=per_page)
    _guard_anilist(result)
    return result


@router.post("/genres/resolve")
def genre_resolve(state: AppState, body: GenreResolveRequest):
    if not body.items:
        return {"items": []}
    batch = body.items[:12]
    raw: list[dict] = []
    for it in batch:
        item = GenreResolveItem(
            id=it.get("id", 0),
            title=it.get("title", ""),
            titles=it.get("titles", []),
            image=it.get("image", ""),
            score=it.get("score"),
            banner=it.get("banner", ""),
            season=it.get("season", ""),
            season_label=it.get("season_label", ""),
            season_line=it.get("season_line", ""),
            year=it.get("year"),
            format=it.get("format", ""),
            format_label=it.get("format_label", ""),
            status=it.get("status", ""),
            status_label=it.get("status_label", ""),
            episodes=it.get("episodes"),
            studios=it.get("studios", []),
            genres=it.get("genres", []),
            genres_label=it.get("genres_label", []),
            description=it.get("description", ""),
        )
        raw.append(item.to_dict())
    found = state.service.resolve_catalog_items(raw, timeout=12.0)
    return {
        "items": [ser.anime_entry(a) for a in found],
        "checked": len(batch),
        "found": len(found),
    }


@router.get("/genres/browse")
def browse_genre(
    state: AppState,
    genre: str = Query(..., min_length=1),
    page: int = PAGE,
    per_page: int = PER_PAGE_12,
):
    result = state.service.browse_by_genre(
        genre.strip(),
        page=page,
        per_page=per_page,
        max_candidates=min(16, per_page + 6),
    )
    _guard_anilist(result)
    return {
        "genre": result.get("genre") or genre,
        "label": result.get("label") or genre,
        "page": result.get("page") or page,
        "per_page": result.get("per_page") or per_page,
        "has_next": bool(result.get("has_next")),
        "anilist_total": result.get("anilist_total"),
        "candidates_checked": result.get("candidates_checked"),
        "items": [ser.anime_entry(a) for a in result.get("items") or []],
    }


@router.get("/anime")
def anime_details(state: AppState, link: str = Query(..., min_length=1)):
    if not state.is_safe_url(link, allow_http=True, resolve_dns=False):
        raise HTTPException(400, "Link inválido")
    detail = state.service.get_anime_details(link)
    if not detail.title:
        raise HTTPException(404, "Anime não encontrado")
    return ser.anime_detail(detail)


@router.get("/meta")
def anilist_meta(
    state: AppState,
    title: str = Query(""),
    id: int | None = Query(None),
):
    if not title.strip() and not id:
        raise HTTPException(400, "Informe title ou id")
    meta = state.service.get_anilist_meta(title=title.strip(), anilist_id=id)
    if not meta:
        raise HTTPException(404, "Metadados não encontrados na AniList")
    return meta


@router.get("/calendar")
def release_calendar(
    state: AppState,
    days: int = Query(7, ge=1, le=14),
    check_sources: bool = Query(False),
):
    result = state.service.get_release_calendar(days=days, check_sources=check_sources)
    _guard_anilist(result)
    return result
