"""Composition root — wiring de serviços e dependências de infraestrutura.

Único módulo que importa app.infrastructure e monta o grafo de objetos.
Injeta tudo em app.state (web) ou retorna objetos (TUI).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from getpass import getpass

from fastapi import FastAPI

from app.application._executor import get_executor
from app.application.anime_service import AnimeService
from app.application.skip_times_service import SkipTimesService
from app.application.stream_resolution_service import StreamResolutionService
from app.application.watch_history_service import WatchHistoryService
from app.infrastructure.anilist_client import GENRE_LABELS_PT, get_anilist_client
from app.infrastructure.config import load as load_config
from app.infrastructure.config import save as save_config
from app.infrastructure.mongodb import get_database
from app.infrastructure.auth import authenticate
from app.infrastructure.player import (
    PLAYER_AUTO,
    PLAYER_BROWSER,
    PLAYER_LABELS,
    install_hint,
    is_player_available,
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


def build_anime_service(config=None) -> AnimeService:
    return AnimeService(
        source_discovery=SourceDiscovery(config=config or load_config()),
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
    _client, db = get_database()
    email = input("E-mail: ").strip()
    password = getpass("Senha: ")
    user = authenticate(email, password)
    if not user:
        raise RuntimeError("E-mail ou senha inválidos")
    config = load_config(mongo_db=db, user_id=user["id"])
    return build_anime_service(config), WatchHistoryService(mongo_db=db, user_id=user["id"])


def web_lifespan():
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO)
        client, db = get_database()
        svc = build_anime_service()
        sessions = StreamSessionStore()
        resolution = StreamResolutionService(
            probe=probe_stream,
            finalize=lambda ctx: finalize_with_blogger(
                ctx, resolve_blogger=resolve_blogger_context
            ),
        )
        st = SkipTimesService()

        app.state.service = svc
        app.state.mongo_db = db
        app.state.mongo_client = client
        app.state.user_services = {}
        app.state.resolution = resolution
        app.state.StreamSession = StreamSession
        app.state.sessions = sessions
        app.state.play_orchestrator = None
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
        try:
            get_executor().shutdown(wait=True, cancel_futures=False)
            logger.info("Thread pool finalizado")
        except RuntimeError:
            logger.warning("Thread pool ja estava finalizado")
        client.close()

    return lifespan


def _ensure_sources(state) -> None:
    if state.sources_ready:
        return
    state.service.init_sources()
    state.sources_ready = True
