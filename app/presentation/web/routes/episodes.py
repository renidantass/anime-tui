"""Rotas de catálogo: episódios, busca, gêneros, metadados, calendário."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.application.dtos import GenreResolveItem
from app.presentation.web import serializers as ser
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import GenreResolveRequest

router = APIRouter(prefix="/api", tags=["catalog"])

PAGE = Query(1, ge=1)
PER_PAGE = Query(20, ge=1, le=50)
PER_PAGE_12 = Query(12, ge=1, le=50)

_MAX_RESOLVE_ITEMS = 12
_MAX_TITLE_LEN = 200
_MAX_DESCRIPTION_LEN = 500


def _guard_anilist(result: dict) -> None:
    if result.get("error") and not result.get("items"):
        raise HTTPException(502, f"AniList indisponível: {result['error']}")


@router.get("/episodes")
def list_episodes(
    state: AppState,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    """Lista os episódios mais recentes com paginação."""
    all_entries = state.service.get_last_episodes()
    total = len(all_entries)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = all_entries[start:end]
    return {
        "items": [ser.episode_entry(e) for e in page_items],
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_next": end < total,
    }


@router.get("/search")
def search(state: AppState, q: str = Query(..., min_length=1)):
    """Busca animes por nome em todas as fontes."""
    results = state.service.search_by(q.strip())
    return {"items": [ser.anime_entry(a) for a in results]}


@router.get("/genres")
def list_genres(state: AppState):
    """Lista gêneros disponíveis da AniList."""
    items = state.service.get_genres()
    return {"items": items}


@router.get("/genres/catalog")
def genre_catalog(
    state: AppState,
    genre: str = Query(..., min_length=1),
    page: int = PAGE,
    per_page: int = PER_PAGE,
):
    """Catálogo paginado de animes por gênero (AniList)."""
    result = state.service.catalog_by_genre(genre.strip(), page=page, per_page=per_page)
    _guard_anilist(result)
    return result


@router.post("/genres/resolve")
def genre_resolve(state: AppState, body: GenreResolveRequest):
    """Cruza resultados da AniList com fontes de anime disponíveis."""
    if not body.items:
        return {"items": []}
    batch = body.items[:_MAX_RESOLVE_ITEMS]
    raw: list[dict] = []
    for it in batch:
        if not isinstance(it, dict):
            continue
        item = GenreResolveItem(
            id=int(it.get("id") or 0),
            title=str(it.get("title") or "")[:_MAX_TITLE_LEN],
            titles=list(it.get("titles") or [])[:10],
            image=str(it.get("image") or "")[:_MAX_TITLE_LEN],
            score=it.get("score"),
            banner=str(it.get("banner") or "")[:_MAX_TITLE_LEN],
            season=str(it.get("season") or "")[:20],
            season_label=str(it.get("season_label") or "")[:50],
            season_line=str(it.get("season_line") or "")[:80],
            year=it.get("year"),
            format=str(it.get("format") or "")[:20],
            format_label=str(it.get("format_label") or "")[:30],
            status=str(it.get("status") or "")[:20],
            status_label=str(it.get("status_label") or "")[:30],
            episodes=it.get("episodes"),
            studios=list(it.get("studios") or [])[:10],
            genres=list(it.get("genres") or [])[:10],
            genres_label=list(it.get("genres_label") or [])[:10],
            description=str(it.get("description") or "")[:_MAX_DESCRIPTION_LEN],
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
    """Navega por gênero com resolução de fontes."""
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
    """Detalhes de um anime com episódios e temporadas."""
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
    """Metadados da AniList para um anime (título ou ID)."""
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
    """Calendário de lançamentos da semana (AniList + fontes)."""
    result = state.service.get_release_calendar(days=days, check_sources=check_sources)
    _guard_anilist(result)
    return result
