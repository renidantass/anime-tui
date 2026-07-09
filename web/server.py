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
    try:
        r = requests.get(
            url,
            headers={**HEADERS, "Accept": "image/*,*/*"},
            timeout=15,
            stream=True,
        )
    except requests.RequestException as e:
        raise HTTPException(502, str(e)) from e
    if r.status_code >= 400:
        r.close()
        raise HTTPException(502, f"Imagem upstream {r.status_code}")

    content_type = r.headers.get("Content-Type", "image/jpeg")
    if not content_type.startswith("image/") and "octet-stream" not in content_type:
        # ainda pode ser imagem sem content-type correto
        pass

    data = r.content
    r.close()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Imagem grande demais")
    return Response(
        content=data,
        media_type=content_type if content_type.startswith("image/") else "image/jpeg",
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
