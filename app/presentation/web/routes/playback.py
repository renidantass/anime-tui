"""Rotas de playback: play, stream proxy, segmentos, skip-times, imagens."""

from __future__ import annotations

from urllib.parse import quote

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from app.application.dtos import PlayCandidate
from app.application.play_orchestration_service import PlayRequest as OrchestratedPlayRequest
from app.presentation.web.schemas import WebPlayRequest

router = APIRouter(prefix="/api", tags=["playback"])

def _state(request: Request):
    return request.app.state


@router.post("/play")
def play(request: Request, body: WebPlayRequest):
    state = request.app.state
    state.ensure_sources()

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
def stream_proxy(token: str, request: Request):
    state = request.app.state
    session = state.sessions.get(token)
    if not session:
        raise HTTPException(404, "Sessão de stream expirada")

    url = session.url
    if not state.is_safe_url(url, allow_http=True, resolve_dns=True):
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

        rewritten = state.rewrite_m3u8(text, url, uri_builder)
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


@router.get("/segment/{token}")
def stream_segment(
    token: str,
    request: Request,
    u: str = Query(..., min_length=1),
):
    state = request.app.state
    session = state.sessions.get(token)
    if not session:
        raise HTTPException(404, "Sessão expirada")
    if not state.is_safe_url(u, allow_http=True, resolve_dns=True):
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

        rewritten = state.rewrite_m3u8(text, u, uri_builder)
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


@router.get("/skip-times")
def skip_times_endpoint(
    request: Request,
    mal_id: int = Query(..., ge=1, description="MyAnimeList ID"),
    episode: int = Query(..., ge=1, description="Número do episódio"),
    episode_length: float = Query(
        0,
        ge=0,
        description="Duração do ep em segundos (0 = curinga na API AniSkip)",
    ),
    types: str = Query("op", description="Tipos separados por vírgula: op,ed,recap…"),
):
    st = request.app.state.skip_times
    type_list = [t.strip() for t in (types or "op").split(",") if t.strip()]
    return st.get_skip_times(
        mal_id=mal_id,
        episode=episode,
        episode_length=episode_length,
        types=type_list,
    )


@router.get("/image")
def image_proxy(request: Request, url: str = Query(..., min_length=1)):
    try:
        data, media_type = request.app.state.fetch_proxied_image(url)
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
