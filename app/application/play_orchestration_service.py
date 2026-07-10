"""Orquestração de play: resolve stream + grava histórico + busca progresso."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.application.anime_service import AnimeService
from app.application.dtos import PlayCandidate, PlayResult, ResolvedPlay
from app.application.stream_resolution_service import StreamResolutionService
from app.application.title_utils import normalize_watch_titles
from app.application.watch_history_service import WatchHistoryService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PlayRequest:
    candidates: list[PlayCandidate]
    preferred_source: str | None = None
    episode_link: str = ""
    anime_title: str = ""
    episode_title: str = ""
    episode_number: str = ""
    anime_image: str = ""
    season_number: int = 1
    source_color: str = ""


class PlayOrchestrationService:
    """Orquestra play: resolve stream + grava histórico + busca progresso."""

    def __init__(
        self,
        anime_service: AnimeService,
        history_service: WatchHistoryService,
        stream_resolution: StreamResolutionService | None = None,
        create_token: Callable[..., str] | None = None,
    ):
        self._anime = anime_service
        self._history = history_service
        self._resolution = stream_resolution or StreamResolutionService()
        self._create_token = create_token

    def play(self, req: PlayRequest) -> PlayResult:
        candidates = self._resolution.order_candidates(
            candidates=req.candidates,
            preferred_source=req.preferred_source,
            episode_link=req.episode_link,
            source_color=req.source_color,
        )
        if not candidates:
            return self._empty_result(req)

        resolved = self._resolve(candidates)
        if resolved is None:
            return self._empty_result(req)

        ctx = resolved.ctx
        link = resolved.link
        url = (ctx.url or "").strip() if ctx else ""
        playable = resolved.playable
        src_name = resolved.source_name or req.preferred_source or ""
        src_color = resolved.source_color or req.source_color or ""

        token = None
        stream_url = None
        if playable and url and self._create_token:
            headers = self._resolution.build_upstream_headers(ctx) if ctx else {}
            token = self._create_token(
                url=url,
                headers=headers,
                page_url=(ctx.page_url or link) if ctx else link,
                anime_title=req.anime_title,
                episode_title=req.episode_title,
                episode_number=req.episode_number,
                episode_link=link,
                source_name=src_name,
                anime_image=req.anime_image,
                season_number=req.season_number,
                source_color=src_color,
            )
            stream_url = f"/api/stream/{token}"

        # histórico
        anime_t, ep_t, ep_n = normalize_watch_titles(
            req.anime_title or req.episode_title or "Anime",
            req.episode_title or "",
            req.episode_number or "",
        )
        try:
            self._history.add_entry(
                anime_title=anime_t,
                episode_title=ep_t,
                episode_number=ep_n or "0",
                episode_link=link,
                source_name=src_name,
                anime_image=req.anime_image,
                season_number=req.season_number,
                source_color=src_color,
            )
        except Exception:
            logger.exception("Falha ao gravar histórico no play")

        progress = self._history.get_progress(link)
        if progress <= 0:
            for c in candidates:
                progress = self._history.get_progress(c.link)
                if progress > 0:
                    break

        failed = [t for t in (resolved.tried or []) if not t.get("ok")]
        return PlayResult(
            playable=playable,
            stream_url=stream_url,
            page_url=(ctx.page_url or link) if ctx else link,
            external_url=None if playable else ((ctx.page_url or url) if ctx else None),
            is_hls=".m3u8" in url.lower(),
            start_at=progress,
            token=token,
            source_name=src_name,
            source_color=src_color,
            episode_link=link,
            switched=bool(failed) and playable,
            tried=list(resolved.tried or []),
        )

    def _empty_result(self, req: PlayRequest) -> PlayResult:
        return PlayResult(
            playable=False,
            stream_url=None,
            page_url="",
            external_url=None,
            is_hls=False,
            start_at=0.0,
            token=None,
            source_name="",
            source_color="",
            episode_link=req.episode_link,
            switched=False,
        )

    def _resolve(self, candidates: list[PlayCandidate]) -> ResolvedPlay | None:
        def get_context(link: str, preferred: str | None):
            if preferred:
                ctx = self._anime.get_play_context_from_source(link, preferred)
                if ctx:
                    return ctx
                return None
            return self._anime.get_play_context(link, None)

        return self._resolution.resolve_with_fallback(
            candidates=candidates,
            get_context=get_context,
            require_probe=True,
        )
