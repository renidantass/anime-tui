"""Servidor FastAPI — API + estáticos da UI web estilo Netflix."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.application.anime_service import AnimeService
from app.application.dtos import GenreResolveItem, PlayCandidate
from app.application.play_orchestration_service import (
    PlayOrchestrationService,
    PlayRequest as OrchestratedPlayRequest,
)
from app.application.skip_times_service import SkipTimesService
from app.application.watch_history_service import WatchHistoryService
from app.infrastructure.security import is_safe_url
from app.infrastructure.sessions.stream_session_store import StreamSessionStore
from app.infrastructure.sources import SourceDiscovery
from app.infrastructure.sources._utils import HEADERS, normalize_watch_titles
from app.infrastructure.streaming.hls_proxy import rewrite_m3u8
from app.infrastructure.streaming.image_proxy import fetch_proxied_image
from web import serializers as ser

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
_executor = ThreadPoolExecutor(max_workers=12)

service: AnimeService | None = None
history: WatchHistoryService | None = None
play_orchestrator: PlayOrchestrationService | None = None
skip_times: SkipTimesService | None = None
sessions = StreamSessionStore()
_sources_ready = False


def get_service() -> AnimeService:
    if service is None:
        raise HTTPException(503, "Serviço ainda não inicializado")
    return service


def get_history() -> WatchHistoryService:
    if history is None:
        raise HTTPException(503, "Histórico ainda não inicializado")
    return history


def get_play_orchestrator() -> PlayOrchestrationService:
    if play_orchestrator is None:
        raise HTTPException(503, "Serviço ainda não inicializado")
    return play_orchestrator


def get_skip_times() -> SkipTimesService:
    if skip_times is None:
        raise HTTPException(503, "Serviço ainda não inicializado")
    return skip_times


def ensure_sources() -> None:
    global _sources_ready
    if _sources_ready:
        return
    svc = get_service()
    svc.init_sources()
    _sources_ready = True


def _warm_sources() -> None:
    global _sources_ready
    try:
        if service is not None:
            service.init_sources()
            _sources_ready = True
    except Exception:
        logger.exception("Falha ao inicializar fontes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global service, history, play_orchestrator, skip_times
    logging.basicConfig(level=logging.INFO)
    svc = AnimeService(source_discovery=SourceDiscovery())
    hst = WatchHistoryService()
    service = svc
    history = hst
    play_orchestrator = PlayOrchestrationService(
        anime_service=svc,
        history_service=hst,
        session_store=sessions,
    )
    skip_times = SkipTimesService()
    _executor.submit(_warm_sources)
    yield
    _executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Animes Web", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────────────────


class PlaySourceCandidate(BaseModel):
    name: str = ""
    link: str
    color: str = ""


class WebPlayRequest(BaseModel):
    episode_link: str = ""
    preferred_source: str | None = None
    anime_title: str = ""
    episode_title: str = ""
    episode_number: str = ""
    anime_image: str = ""
    season_number: int = 1
    source_color: str = ""
    candidates: list[PlaySourceCandidate] = Field(default_factory=list)


class ProgressRequest(BaseModel):
    episode_link: str
    progress_seconds: float = 0.0
    duration_seconds: float = 0.0


class HistoryAddRequest(BaseModel):
    anime_title: str
    episode_title: str
    episode_number: str
    episode_link: str
    source_name: str
    anime_image: str = ""
    season_number: int = 1
    source_color: str = ""
    progress_seconds: float = 0.0
    duration_seconds: float = 0.0


class SourceToggle(BaseModel):
    enabled: bool


# ── API ──────────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {"ok": True, "sources_ready": _sources_ready}


@app.get("/api/episodes")
def list_episodes():
    ensure_sources()
    entries = get_service().get_last_episodes()
    return {"items": [ser.episode_entry(e) for e in entries]}


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    ensure_sources()
    results = get_service().search_by(q.strip())
    return {"items": [ser.anime_entry(a) for a in results]}


class GenreResolveRequest(BaseModel):
    items: list[dict] = Field(default_factory=list)


@app.get("/api/genres")
def list_genres():
    items = get_service().get_genres()
    return {"items": items}


@app.get("/api/meta")
def anilist_meta(
    title: str = Query("", description="Título para buscar na AniList"),
    id: int | None = Query(None, description="ID AniList (preferencial)"),
):
    if not title.strip() and not id:
        raise HTTPException(400, "Informe title ou id")
    meta = get_service().get_anilist_meta(title=title.strip(), anilist_id=id)
    if not meta:
        raise HTTPException(404, "Metadados não encontrados na AniList")
    return meta


@app.get("/api/skip-times")
def skip_times_endpoint(
    mal_id: int = Query(..., ge=1, description="MyAnimeList ID"),
    episode: int = Query(..., ge=1, description="Número do episódio"),
    episode_length: float = Query(
        0,
        ge=0,
        description="Duração do ep em segundos (0 = curinga na API AniSkip)",
    ),
    types: str = Query("op", description="Tipos separados por vírgula: op,ed,recap…"),
):
    st = get_skip_times()
    type_list = [t.strip() for t in (types or "op").split(",") if t.strip()]
    return st.get_skip_times(
        mal_id=mal_id,
        episode=episode,
        episode_length=episode_length,
        types=type_list,
    )


@app.get("/api/calendar")
def release_calendar(
    days: int = Query(7, ge=1, le=14, description="Janela de dias (1–14)"),
    check_sources: bool = Query(
        False,
        description="Se true, cruza cada episódio com as fontes (mais lento)",
    ),
):
    if check_sources:
        ensure_sources()
    result = get_service().get_release_calendar(days=days, check_sources=check_sources)
    if result.get("error") and not result.get("items"):
        raise HTTPException(502, f"AniList indisponível: {result['error']}")
    return result


@app.get("/api/genres/catalog")
def genre_catalog(
    genre: str = Query(..., min_length=1, description="Gênero AniList, ex.: Action"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=40),
):
    result = get_service().catalog_by_genre(genre.strip(), page=page, per_page=per_page)
    if result.get("error") and not result.get("items"):
        raise HTTPException(502, f"AniList indisponível: {result['error']}")
    return result


@app.post("/api/genres/resolve")
def genre_resolve(body: GenreResolveRequest):
    ensure_sources()
    if not body.items:
        return {"items": []}
    batch = body.items[:12]
    raw = []
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
    found = get_service().resolve_catalog_items(raw, timeout=12.0)
    return {
        "items": [ser.anime_entry(a) for a in found],
        "checked": len(batch),
        "found": len(found),
    }


@app.get("/api/genres/browse")
def browse_genre(
    genre: str = Query(..., min_length=1, description="Nome do gênero (AniList, ex.: Action)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=40),
):
    ensure_sources()
    result = get_service().browse_by_genre(
        genre.strip(),
        page=page,
        per_page=per_page,
        max_candidates=min(16, per_page + 6),
    )
    if result.get("error") and not result.get("items"):
        raise HTTPException(502, f"AniList indisponível: {result['error']}")
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


@app.get("/api/anime")
def anime_details(link: str = Query(..., min_length=1)):
    ensure_sources()
    if not is_safe_url(link, allow_http=True, resolve_dns=False):
        raise HTTPException(400, "Link inválido")
    detail = get_service().get_anime_details(link)
    if not detail.title:
        raise HTTPException(404, "Anime não encontrado")
    return ser.anime_detail(detail)


@app.post("/api/play")
def play(body: WebPlayRequest):
    ensure_sources()

    raw_candidates = [
        PlayCandidate(name=c.name, link=c.link, color=c.color)
        for c in body.candidates
        if (c.link or "").strip()
    ]
    if body.episode_link.strip():
        raw_candidates.append(
            PlayCandidate(
                name=body.preferred_source or "",
                link=body.episode_link.strip(),
                color=body.source_color or "",
            )
        )

    orchestrator = get_play_orchestrator()
    result = orchestrator.play(
        OrchestratedPlayRequest(
            candidates=raw_candidates,
            preferred_source=body.preferred_source,
            episode_link=body.episode_link.strip(),
            anime_title=body.anime_title,
            episode_title=body.episode_title,
            episode_number=body.episode_number,
            anime_image=body.anime_image,
            season_number=body.season_number,
            source_color=body.source_color,
        )
    )

    return {
        "playable": result.playable,
        "stream_url": result.stream_url,
        "page_url": result.page_url,
        "external_url": result.external_url,
        "is_hls": result.is_hls,
        "start_at": result.start_at,
        "token": result.token,
        "source_name": result.source_name,
        "source_color": result.source_color,
        "episode_link": result.episode_link,
        "switched": result.switched,
        "tried": result.tried,
    }


@app.get("/api/stream/{token}")
def stream_proxy(token: str, request: Request):
    session = sessions.get(token)
    if not session:
        raise HTTPException(404, "Sessão de stream expirada")

    url = session.url
    if not is_safe_url(url, allow_http=True, resolve_dns=True):
        raise HTTPException(403, "Stream bloqueado por segurança")

    range_header = request.headers.get("range")
    upstream_headers = dict(session.headers)
    if range_header:
        upstream_headers["Range"] = range_header

    try:
        upstream = requests.get(
            url,
            headers=upstream_headers,
            stream=True,
            timeout=(10, 60),
            allow_redirects=True,
        )
    except requests.RequestException as e:
        logger.warning("Falha no proxy de stream: %s", e)
        raise HTTPException(502, f"Erro ao obter stream: {e}") from e

    if upstream.status_code >= 400:
        body = upstream.content[:500]
        upstream.close()
        raise HTTPException(
            502,
            f"Upstream retornou {upstream.status_code}: {body[:120]!r}",
        )

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    if "mpegurl" in content_type.lower() or url.lower().endswith(".m3u8"):
        text = upstream.content.decode("utf-8", errors="replace")
        upstream.close()

        def uri_builder(abs_url: str) -> str:
            return f"/api/segment/{token}?u={quote(abs_url, safe='')}"

        rewritten = rewrite_m3u8(text, url, uri_builder)
        return Response(
            content=rewritten,
            media_type="application/vnd.apple.mpegurl",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"},
        )

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    headers_out: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
    }
    for h in ("Content-Length", "Content-Range", "Content-Type"):
        if h in upstream.headers:
            headers_out[h] = upstream.headers[h]

    status = 206 if upstream.status_code == 206 else 200
    return StreamingResponse(
        generate(),
        status_code=status,
        media_type=content_type,
        headers=headers_out,
    )


@app.get("/api/segment/{token}")
def stream_segment(
    token: str,
    request: Request,
    u: str = Query(..., min_length=1),
):
    session = sessions.get(token)
    if not session:
        raise HTTPException(404, "Sessão expirada")
    if not is_safe_url(u, allow_http=True, resolve_dns=True):
        raise HTTPException(403, "URL de segmento bloqueada")

    headers = dict(session.headers)
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    try:
        upstream = requests.get(
            u, headers=headers, stream=True, timeout=(10, 60), allow_redirects=True
        )
    except requests.RequestException as e:
        raise HTTPException(502, str(e)) from e

    if upstream.status_code >= 400:
        upstream.close()
        raise HTTPException(502, f"Segmento upstream {upstream.status_code}")

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    if "mpegurl" in content_type.lower() or u.lower().endswith(".m3u8"):
        text = upstream.content.decode("utf-8", errors="replace")
        upstream.close()

        def uri_builder(abs_url: str) -> str:
            return f"/api/segment/{token}?u={quote(abs_url, safe='')}"

        rewritten = rewrite_m3u8(text, u, uri_builder)
        return Response(
            content=rewritten,
            media_type="application/vnd.apple.mpegurl",
            headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"},
        )

    headers_out = {"Access-Control-Allow-Origin": "*"}
    for h in ("Content-Length", "Content-Range", "Content-Type"):
        if h in upstream.headers:
            headers_out[h] = upstream.headers[h]
    status = 206 if upstream.status_code == 206 else 200
    return StreamingResponse(
        generate(), status_code=status, media_type=content_type, headers=headers_out
    )


@app.get("/api/image")
def image_proxy(url: str = Query(..., min_length=1)):
    try:
        data, media_type = fetch_proxied_image(url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/history")
def get_history_list(
    dedupe: bool = True,
    mode: str = Query(
        "anime",
        description="anime = 1 card por anime; episode = 1 por episódio; all = bruto",
    ),
):
    hs = get_history()
    mode = (mode or "anime").strip().lower()
    if mode == "all":
        entries = hs.get_all()
    elif mode == "episode" or not dedupe:
        entries = hs.get_all_unique_episodes()
    else:
        entries = hs.get_all_deduped()
    return {"items": [ser.history_entry(e) for e in entries]}


@app.post("/api/history")
def add_history(body: HistoryAddRequest):
    anime_t, ep_t, ep_n = normalize_watch_titles(
        body.anime_title, body.episode_title, body.episode_number
    )
    entry = get_history().add_entry(
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


@app.post("/api/history/progress")
def update_progress(body: ProgressRequest):
    get_history().update_progress(
        body.episode_link, body.progress_seconds, body.duration_seconds
    )
    return {"ok": True}


@app.delete("/api/history")
def clear_history():
    get_history().clear_all()
    return {"ok": True}


@app.get("/api/sources")
def list_sources():
    ensure_sources()
    svc = get_service()
    items = [
        ser.source_entry(e, svc.is_enabled(e.identifier))
        for e in svc.get_all_source_entries()
    ]
    return {"items": items}


@app.post("/api/sources/health")
def refresh_sources_health():
    ensure_sources()
    svc = get_service()
    entries = svc.refresh_source_health()
    return {
        "items": [
            ser.source_entry(e, svc.is_enabled(e.identifier)) for e in entries if e
        ]
    }


@app.post("/api/sources/{identifier}/health")
def refresh_one_source_health(identifier: str):
    ensure_sources()
    svc = get_service()
    known = {e.identifier for e in svc.get_all_source_entries()}
    if identifier not in known:
        raise HTTPException(404, "Fonte desconhecida")
    entries = svc.refresh_source_health(identifier)
    if not entries or not entries[0]:
        raise HTTPException(404, "Fonte não encontrada")
    e = entries[0]
    return ser.source_entry(e, svc.is_enabled(e.identifier))


@app.put("/api/sources/{identifier}")
def toggle_source(identifier: str, body: SourceToggle):
    ensure_sources()
    svc = get_service()
    known = {e.identifier for e in svc.get_all_source_entries()}
    if identifier not in known:
        raise HTTPException(404, "Fonte desconhecida")
    svc.set_enabled(identifier, body.enabled)
    return {"identifier": identifier, "enabled": body.enabled}


# Estáticos por último
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
