"""Servidor FastAPI — API + estáticos da UI web estilo Netflix."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urljoin

import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.application.anime_service import AnimeService
from app.application.watch_history_service import WatchHistoryService
from app.infrastructure.security import is_safe_url
from app.infrastructure.sources import SourceDiscovery
from app.infrastructure.sources._utils import HEADERS, normalize_watch_titles
from web import serializers as ser
from web.playback import (
    PlayCandidate,
    build_upstream_headers,
    order_candidates,
    resolve_with_fallback,
)
from web.stream_sessions import StreamSession, StreamSessionStore

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
_executor = ThreadPoolExecutor(max_workers=12)

service: AnimeService | None = None
history: WatchHistoryService | None = None
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
    global service, history
    logging.basicConfig(level=logging.INFO)
    service = AnimeService(source_discovery=SourceDiscovery())
    history = WatchHistoryService()
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


class PlayRequest(BaseModel):
    episode_link: str = ""
    preferred_source: str | None = None
    anime_title: str = ""
    episode_title: str = ""
    episode_number: str = ""
    anime_image: str = ""
    season_number: int = 1
    source_color: str = ""
    """Lista de fontes (name+link) para fallback automático."""
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


class GenreResolveItem(BaseModel):
    id: int = 0
    title: str = ""
    titles: list[str] = Field(default_factory=list)
    image: str = ""
    score: int | None = None
    banner: str = ""
    season: str = ""
    season_label: str = ""
    season_line: str = ""
    year: int | None = None
    format: str = ""
    format_label: str = ""
    status: str = ""
    status_label: str = ""
    episodes: int | None = None
    studios: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    genres_label: list[str] = Field(default_factory=list)
    description: str = ""


class GenreResolveRequest(BaseModel):
    items: list[GenreResolveItem] = Field(default_factory=list)


@app.get("/api/genres")
def list_genres():
    """Gêneros da AniList (id EN + label PT)."""
    items = get_service().get_genres()
    return {"items": items}


@app.get("/api/meta")
def anilist_meta(
    title: str = Query("", description="Título para buscar na AniList"),
    id: int | None = Query(None, description="ID AniList (preferencial)"),
):
    """
    Metadados ricos da AniList: season, status, studios, sinopse, franquia
    (prequel/sequel) e próximo episódio.
    """
    if not title.strip() and not id:
        raise HTTPException(400, "Informe title ou id")
    meta = get_service().get_anilist_meta(title=title.strip(), anilist_id=id)
    if not meta:
        raise HTTPException(404, "Metadados não encontrados na AniList")
    return meta


@app.get("/api/skip-times")
def skip_times(
    mal_id: int = Query(..., ge=1, description="MyAnimeList ID"),
    episode: int = Query(..., ge=1, description="Número do episódio"),
    episode_length: float = Query(
        0,
        ge=0,
        description="Duração do ep em segundos (0 = curinga na API AniSkip)",
    ),
    types: str = Query("op", description="Tipos separados por vírgula: op,ed,recap…"),
):
    """Proxy AniSkip — timestamps de opening/ending por anime+episódio.

    A API é sensível a ``episode_length``: valores longe da duração real
    (ex.: 1440 genérico) costumam retornar vazio. Preferir 0 ou a duração
    medida do vídeo.
    """
    type_list = [t.strip() for t in (types or "op").split(",") if t.strip()]
    if not type_list:
        type_list = ["op"]

    lengths: list[float] = []
    lengths.append(0.0)  # curinga — melhor taxa de acerto
    if episode_length and episode_length > 60:
        d = float(episode_length)
        lengths.extend(
            [
                d,
                round(d),
                round(d) - 1,
                round(d) + 1,
                round(d / 10) * 10,
                round(d / 60) * 60,
            ]
        )

    tried: set[int] = set()
    last_payload: dict | None = None
    for raw_len in lengths:
        L = max(0, int(raw_len or 0))
        if L in tried:
            continue
        tried.add(L)
        params: list[tuple[str, str | int]] = [("episodeLength", L)]
        for t in type_list:
            params.append(("types[]", t))
        try:
            r = requests.get(
                f"https://api.aniskip.com/v2/skip-times/{mal_id}/{episode}",
                params=params,
                headers={**HEADERS, "Accept": "application/json"},
                timeout=12,
            )
        except requests.RequestException as e:
            logger.warning("AniSkip request fail: %s", e)
            continue
        if r.status_code == 404:
            continue
        if r.status_code >= 400:
            logger.debug("AniSkip HTTP %s: %s", r.status_code, r.text[:120])
            continue
        try:
            payload = r.json()
        except Exception:
            continue
        last_payload = payload if isinstance(payload, dict) else None
        if isinstance(payload, dict) and payload.get("found") and payload.get("results"):
            return {
                "found": True,
                "mal_id": mal_id,
                "episode": episode,
                "episode_length": L,
                "results": payload.get("results") or [],
            }

    return {
        "found": False,
        "mal_id": mal_id,
        "episode": episode,
        "results": [],
        "message": (last_payload or {}).get("message") or "No skip times found",
    }


@app.get("/api/calendar")
def release_calendar(
    days: int = Query(7, ge=1, le=14, description="Janela de dias (1–14)"),
    check_sources: bool = Query(
        False,
        description="Se true, cruza cada episódio com as fontes (mais lento)",
    ),
):
    """Calendário de lançamentos. Cruzamento com fontes é opcional."""
    if check_sources:
        ensure_sources()
    result = get_service().get_release_calendar(
        days=days, check_sources=check_sources
    )
    if result.get("error") and not result.get("items"):
        raise HTTPException(502, f"AniList indisponível: {result['error']}")
    return result


@app.get("/api/genres/catalog")
def genre_catalog(
    genre: str = Query(..., min_length=1, description="Gênero AniList, ex.: Action"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=40),
):
    """Catálogo AniList puro (rápido) — sem checar fontes."""
    result = get_service().catalog_by_genre(
        genre.strip(), page=page, per_page=per_page
    )
    if result.get("error") and not result.get("items"):
        raise HTTPException(502, f"AniList indisponível: {result['error']}")
    return result


@app.post("/api/genres/resolve")
def genre_resolve(body: GenreResolveRequest):
    """
    Cruza candidatos do catálogo com as fontes ativas.
    Use em lotes pequenos para a UI ir preenchendo.
    """
    ensure_sources()
    if not body.items:
        return {"items": []}
    # evita abuso / timeouts longos
    batch = body.items[:12]
    raw = [
        {
            "id": it.id,
            "title": it.title,
            "titles": it.titles,
            "image": it.image,
            "score": it.score,
            "banner": it.banner,
            "season": it.season,
            "season_label": it.season_label,
            "season_line": it.season_line,
            "year": it.year,
            "format": it.format,
            "format_label": it.format_label,
            "status": it.status,
            "status_label": it.status_label,
            "episodes": it.episodes,
            "studios": it.studios,
            "genres": it.genres,
            "genres_label": it.genres_label,
            "description": it.description,
        }
        for it in batch
    ]
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
    """
    Compat: AniList + fontes num request.
    Prefira /catalog + /resolve para UX progressiva.
    """
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
def play(body: PlayRequest):
    """Resolve stream com fallback automático entre fontes candidatas."""
    ensure_sources()

    raw_candidates = [
        PlayCandidate(name=c.name, link=c.link, color=c.color)
        for c in body.candidates
        if (c.link or "").strip()
    ]
    # compat: request legado só com episode_link
    if body.episode_link.strip():
        raw_candidates.append(
            PlayCandidate(
                name=body.preferred_source or "",
                link=body.episode_link.strip(),
                color=body.source_color or "",
            )
        )

    candidates = order_candidates(
        candidates=raw_candidates,
        preferred_source=body.preferred_source,
        episode_link=body.episode_link.strip(),
        source_color=body.source_color,
    )
    if not candidates:
        raise HTTPException(400, "Nenhuma fonte candidata válida")

    svc = get_service()

    def get_context(link: str, preferred: str | None):
        # Com nome da fonte: usa só o reader certo (cada candidato tem seu link).
        if preferred:
            ctx = svc.get_play_context_from_source(link, preferred)
            if ctx:
                return ctx
            return None
        return svc.get_play_context(link, None)

    resolved = resolve_with_fallback(
        candidates=candidates,
        get_context=get_context,
        require_probe=True,
    )
    if resolved is None:
        raise HTTPException(404, "Nenhuma fonte de vídeo disponível")

    ctx = resolved.ctx
    link = resolved.link
    url = (ctx.url or "").strip()
    playable = resolved.playable
    src_name = resolved.source_name or body.preferred_source or ""
    src_color = resolved.source_color or body.source_color or ""

    token = None
    stream_url = None
    if playable and url:
        headers = build_upstream_headers(ctx)
        token = sessions.create(
            StreamSession(
                url=url,
                headers=headers,
                page_url=ctx.page_url or link,
                anime_title=body.anime_title,
                episode_title=body.episode_title,
                episode_number=body.episode_number,
                episode_link=link,
                source_name=src_name,
                anime_image=body.anime_image,
                season_number=body.season_number,
                source_color=src_color,
            )
        )
        stream_url = f"/api/stream/{token}"

    anime_t, ep_t, ep_n = normalize_watch_titles(
        body.anime_title or body.episode_title or "Anime",
        body.episode_title or "",
        body.episode_number or "",
    )
    try:
        get_history().add_entry(
            anime_title=anime_t,
            episode_title=ep_t,  # vazio se era só "Episódio N" — evita "Ep 1 · Episodio 1"
            episode_number=ep_n or "0",
            episode_link=link,
            source_name=src_name,
            anime_image=body.anime_image,
            season_number=body.season_number,
            source_color=src_color,
        )
    except Exception:
        logger.exception("Falha ao gravar histórico no play")

    # progresso: tenta o link resolvido e os candidatos (histórico anterior)
    progress = get_history().get_progress(link)
    if progress <= 0:
        for c in candidates:
            progress = get_history().get_progress(c.link)
            if progress > 0:
                break

    failed = [t for t in resolved.tried if not t.get("ok")]
    switched = bool(failed) and playable

    return {
        "playable": playable,
        "stream_url": stream_url,
        "page_url": ctx.page_url or link,
        "external_url": None if playable else (ctx.page_url or url),
        "is_hls": ".m3u8" in url.lower(),
        "start_at": progress,
        "token": token,
        "source_name": src_name,
        "source_color": src_color,
        "episode_link": link,
        "switched": switched,
        "tried": resolved.tried,
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
    # HLS playlist: reescreve URIs para passar pelo proxy de segmentos
    if "mpegurl" in content_type.lower() or url.lower().endswith(".m3u8"):
        text = upstream.content.decode("utf-8", errors="replace")
        upstream.close()
        rewritten = _rewrite_m3u8(text, url, token, session)
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
    """Proxy de segmento HLS / URI relativa reescrita do m3u8."""
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
    # nested playlist
    if "mpegurl" in content_type.lower() or u.lower().endswith(".m3u8"):
        text = upstream.content.decode("utf-8", errors="replace")
        upstream.close()
        rewritten = _rewrite_m3u8(text, u, token, session)
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


def _rewrite_m3u8(text: str, base_url: str, token: str, session: StreamSession) -> str:
    """Reescreve URIs do playlist para /api/segment/{token}?u=..."""
    from urllib.parse import quote

    lines_out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            # URI= em EXT-X-KEY / EXT-X-MAP
            if "URI=" in stripped:

                def repl(m: re.Match) -> str:
                    raw = m.group(1)
                    abs_u = urljoin(base_url, raw)
                    return f'URI="/api/segment/{token}?u={quote(abs_u, safe="")}"'

                lines_out.append(re.sub(r'URI="([^"]+)"', repl, line))
            else:
                lines_out.append(line)
            continue
        abs_u = urljoin(base_url, stripped)
        lines_out.append(f"/api/segment/{token}?u={quote(abs_u, safe='')}")
    return "\n".join(lines_out) + "\n"


@app.get("/api/image")
def image_proxy(url: str = Query(..., min_length=1)):
    """Proxy de imagem (evita hotlink / referer bloqueado)."""
    if not is_safe_url(url, allow_http=True, resolve_dns=True):
        raise HTTPException(400, "URL de imagem inválida")
    # vários CDNs de anime exigem Referer do próprio site
    referer = ""
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        if p.scheme and p.netloc:
            referer = f"{p.scheme}://{p.netloc}/"
    except Exception:
        referer = ""
    headers = {**HEADERS, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.get(
            url,
            headers=headers,
            timeout=15,
            stream=True,
        )
    except requests.RequestException as e:
        raise HTTPException(502, str(e)) from e
    if r.status_code >= 400:
        r.close()
        raise HTTPException(502, f"Imagem upstream {r.status_code}")

    content_type = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    data = r.content
    r.close()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Imagem grande demais")
    if len(data) < 32:
        raise HTTPException(502, "Imagem vazia")

    # magic bytes — rejeita HTML de 404 disfarçado
    is_img = (
        data[:3] == b"\xff\xd8\xff"  # jpeg
        or data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"GIF"
        or (data[:4] == b"RIFF" and b"WEBP" in data[:16])
        or data[4:8] == b"ftyp"  # avif/heic
    )
    if content_type.startswith("text/html") or (
        not content_type.startswith("image/")
        and "octet-stream" not in content_type
        and not is_img
    ):
        raise HTTPException(502, "Upstream não retornou imagem")

    if content_type.startswith("image/"):
        media = content_type
    elif data[:4] == b"RIFF" and b"WEBP" in data[:16]:
        media = "image/webp"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        media = "image/png"
    else:
        media = "image/jpeg"
    return Response(
        content=data,
        media_type=media,
        headers={"Cache-Control": "public, max-age=86400", "Access-Control-Allow-Origin": "*"},
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
        # dedupe=false legado: 1 por episódio (não dump bruto multi-fonte)
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
    """Revalida todas as fontes (status, latência, uptime)."""
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
    # permite ativar/desativar mesmo offline — só deixa de ser usada se offline
    svc.set_enabled(identifier, body.enabled)
    return {"identifier": identifier, "enabled": body.enabled}


# Estáticos por último
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
