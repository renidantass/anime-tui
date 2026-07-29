"""Dependências FastAPI compartilhadas entre os routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request


def _get_state(request: Request):
    request.app.state.ensure_sources()
    state = request.app.state
    user = request.state.user
    state.current_user = user
    state.user_id = user["id"]
    services = state.user_services.get(user["id"])
    if services is None:
        from app.application.opening_mark_service import OpeningMarkService
        from app.application.play_orchestration_service import PlayOrchestrationService
        from app.application.watch_history_service import WatchHistoryService
        from app.application.watch_later_service import WatchLaterService
        from app.infrastructure.config import load as load_config
        from bootstrap import build_anime_service

        config = load_config(mongo_db=state.mongo_db, user_id=user["id"])
        user_anime_service = build_anime_service(config)
        user_anime_service.init_sources()
        history = WatchHistoryService(mongo_db=state.mongo_db, user_id=user["id"])
        later = WatchLaterService(mongo_db=state.mongo_db, user_id=user["id"])
        opening = OpeningMarkService(mongo_db=state.mongo_db, user_id=user["id"])
        orchestrator = PlayOrchestrationService(
            anime_service=user_anime_service,
            history_service=history,
            stream_resolution=state.resolution,
            create_token=lambda **kw: state.sessions.create(state.StreamSession(**kw)),
        )
        services = (history, later, opening, orchestrator, user_anime_service)
        state.user_services[user["id"]] = services
    state.history, state.watch_later, state.opening_mark_service, state.play_orchestrator, state.service = services
    return state


AppState = Annotated[object, Depends(_get_state)]
