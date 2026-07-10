"""Composition root — wiring de serviços e dependências de infraestrutura.

Único módulo que importa app.infrastructure e monta o grafo de objetos.
Injeta tudo em app.state (web) ou retorna objetos (TUI).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.application._executor import get_executor
from app.application.anime_service import AnimeService
from app.application.play_orchestration_service import PlayOrchestrationService
from app.application.skip_times_service import SkipTimesService
from app.application.stream_resolution_service import StreamResolutionService
from app.application.watch_history_service import WatchHistoryService
from app.infrastructure.anilist_client import GENRE_LABELS_PT, get_anilist_client
from app.infrastructure.aniskip_client import fetch_skip_times
from app.infrastructure.config import load as load_config, save as save_config
from app.infrastructure.player import (
    PLAYER_AUTO,
    PLAYER_BROWSER,
    PLAYER_LABELS,
    install_hint,
    is_player_available,
    open_video,
    selectable_backends,
)
from app.infrastructure.security import _MAX_IMAGE_BYTES, is_safe_url, safe_get_bytes
from app.infrastructure.sessions.stream_session_store import StreamSession, StreamSessionStore
from app.infrastructure.sources import SourceDiscovery
from app.infrastructure.sources._playback import resolve_blogger_context
from app.infrastructure.stream_probe import finalize_with_blogger, probe_stream
from app.infrastructure.streaming.hls_proxy import rewrite_m3u8
from app.infrastructure.streaming.image_proxy import fetch_proxied_image

logger = logging.getLogger(__name__)


def _make_anon_lambda(fn, *args):
    return lambda: fn(*args)


def build_anime_service() -> AnimeService:
    return AnimeService(
        source_discovery=SourceDiscovery(),
        anilist=get_anilist_client(),
        genre_labels=GENRE_LABELS_PT,
    )


def build_player_deps() -> dict:
    return {
        "PLAYER_AUTO": PLAYER_AUTO,
        "PLAYER_BROWSER": PLAYER_BROWSER,
        "PLAYER_LABELS": PLAYER_LABELS,
        "load_config": load_config,
        "save_config": save_config,
        "is_player_available": is_player_available,
        "install_hint": install_hint,
        "selectable_backends": selectable_backends,
    }


def build_image_deps() -> dict:
    return {
        "is_safe_url": is_safe_url,
        "safe_get_bytes": safe_get_bytes,
        "max_image_bytes": _MAX_IMAGE_BYTES,
    }


def build_tui_wiring() -> tuple[AnimeService, WatchHistoryService]:
    return build_anime_service(), WatchHistoryService()


def web_lifespan():
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO)
        svc = build_anime_service()
        hst = WatchHistoryService()
        sessions = StreamSessionStore()
        resolution = StreamResolutionService(
            probe=probe_stream,
            finalize=lambda ctx: finalize_with_blogger(ctx, resolve_blogger=resolve_blogger_context),
        )
        orchestrator = PlayOrchestrationService(
            anime_service=svc,
            history_service=hst,
            stream_resolution=resolution,
            create_token=lambda **kw: sessions.create(StreamSession(**kw)),
        )
        st = SkipTimesService()

        app.state.service = svc
        app.state.history = hst
        app.state.sessions = sessions
        app.state.play_orchestrator = orchestrator
        app.state.skip_times = st
        app.state.sources_ready = False
        app.state.is_safe_url = is_safe_url
        app.state.rewrite_m3u8 = rewrite_m3u8
        app.state.fetch_proxied_image = fetch_proxied_image
        app.state.ensure_sources = _make_anon_lambda(_ensure_sources, app.state)

        def warm():
            try:
                svc.init_sources()
            except Exception:
                logger.exception("Falha ao inicializar fontes")
            finally:
                app.state.sources_ready = True

        get_executor().submit(warm)
        yield
        get_executor().shutdown(wait=False, cancel_futures=True)
    return lifespan


def _ensure_sources(state) -> None:
    if state.sources_ready:
        return
    state.service.init_sources()
    state.sources_ready = True
