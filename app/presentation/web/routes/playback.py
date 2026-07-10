"""Rotas de playback: play, stream proxy, segmentos, skip-times, imagens."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import quote

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from app.application.dtos import PlayCandidate
from app.application.play_orchestration_service import PlayRequest as OrchestratedPlayRequest
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import WebPlayRequest

router = APIRouter(prefix="/api", tags=["playback"])


# ── Helpers de streaming ─────────────────────────────────────────────────────


def _fetch_upstream(url: str, headers: dict) -> requests.Response:
    try:
        upstream = requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=(10, 60),
            allow_redirects=True,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Erro ao acessar stream: {e}") from e
    if upstream.status_code >= 400:
        body = upstream.content[:500]
        upstream.close()
        raise HTTPException(502, f"Upstream retornou {upstream.status_code}: {body[:120]!r}")
    return upstream


def _stream_chunks(upstream: requests.Response) -> Iterator[bytes]:
    try:
        for chunk in upstream.iter_content(chunk_size=64 * 1024):
            if chunk:
                yield chunk
    finally:
        upstream.close()


def _build_stream_headers(
    upstream: requests.Response, *, extra: dict | None = None
) -> dict[str, str]:
    headers_out = {"Access-Control-Allow-Origin": "*"}
    if extra:
        headers_out.update(extra)
    for h in ("Content-Length", "Content-Range", "Content-Type"):
        if h in upstream.headers:
            headers_out[h] = upstream.headers[h]
    return headers_out


def _stream_status(upstream: requests.Response) -> int:
    return 206 if upstream.status_code == 206 else 200


def _handle_m3u8(upstream: requests.Response, base_url: str, token: str, state) -> Response:
    text = upstream.content.decode("utf-8", errors="replace")
    upstream.close()

    def uri_builder(abs_url: str) -> str:
        return f"/api/segment/{token}?u={quote(abs_url, safe='')}"

    rewritten = state.rewrite_m3u8(text, base_url, uri_builder)
    return Response(
        content=rewritten,
        media_type="application/vnd.apple.mpegurl",
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"},
    )


def _validate_session(state, token: str, url: str):
    session = state.sessions.get(token)
    if not session:
        raise HTTPException(404, "Sessão de stream expirada")
    if not state.is_safe_url(url, allow_http=True, resolve_dns=True):
        raise HTTPException(403, "Stream bloqueado por segurança")
    return session


def _is_m3u8(content_type: str, url: str) -> bool:
    return "mpegurl" in content_type.lower() or url.lower().endswith(".m3u8")


# ── Rotas ────────────────────────────────────────────────────────────────────


@router.post("/play")
def play(state: AppState, body: WebPlayRequest):
    """Resolve e inicia playback de um episódio, retornando token de stream."""
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

    result = state.play_orchestrator.play(
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


@router.get("/stream/{token}")
def stream_proxy(token: str, state: AppState, request: Request):
    """Proxy de stream — redireciona ou faz bridge do conteúdo de vídeo."""
    session = state.sessions.get(token)
    if not session:
        raise HTTPException(404, "Sessão de stream expirada")

    url = session.url
    if not state.is_safe_url(url, allow_http=True, resolve_dns=True):
        raise HTTPException(403, "Stream bloqueado por segurança")

    upstream_headers = dict(session.headers)
    range_header = request.headers.get("range")
    if range_header:
        upstream_headers["Range"] = range_header

    upstream = _fetch_upstream(url, upstream_headers)

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    if _is_m3u8(content_type, url):
        return _handle_m3u8(upstream, url, token, state)

    extra = {
        "Accept-Ranges": "bytes",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
    }
    headers_out = _build_stream_headers(upstream, extra=extra)
    status = _stream_status(upstream)
    return StreamingResponse(
        _stream_chunks(upstream),
        status_code=status,
        media_type=content_type,
        headers=headers_out,
    )


@router.get("/segment/{token}")
def stream_segment(
    token: str,
    state: AppState,
    request: Request,
):
    """Proxy de segmento HLS — busca segmento individual com headers de referer."""
    session = state.sessions.get(token)
    if not session:
        raise HTTPException(404, "Sessão expirada")
    url = session.url
    if not state.is_safe_url(url, allow_http=True, resolve_dns=True):
        raise HTTPException(403, "URL de segmento bloqueada")

    headers = dict(session.headers)
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    upstream = _fetch_upstream(url, headers)

    content_type = upstream.headers.get("Content-Type", "application/octet-stream")
    if _is_m3u8(content_type, url):
        return _handle_m3u8(upstream, url, token, state)

    headers_out = _build_stream_headers(upstream)
    status = _stream_status(upstream)
    return StreamingResponse(
        _stream_chunks(upstream),
        status_code=status,
        media_type=content_type,
        headers=headers_out,
    )


@router.get("/skip-times")
def skip_times_endpoint(
    state: AppState,
    mal_id: int = Query(..., ge=1, description="MyAnimeList ID"),
    episode: int = Query(..., ge=1, description="Número do episódio"),
    episode_length: float = Query(
        0,
        ge=0,
        description="Duração do ep em segundos (0 = curinga na API AniSkip)",
    ),
    types: str = Query("op", description="Tipos separados por vírgula: op,ed,recap…"),
):
    """Timestamps de abertura/encerramento via AniSkip."""
    st = state.skip_times
    type_list = [t.strip() for t in (types or "op").split(",") if t.strip()]
    return st.get_skip_times(
        mal_id=mal_id,
        episode=episode,
        episode_length=episode_length,
        types=type_list,
    )


@router.get("/image")
def image_proxy(state: AppState, url: str = Query(..., min_length=1)):
    """Proxy de imagem — busca, valida e serve imagens com cache."""
    try:
        data, media_type = state.fetch_proxied_image(url)
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
