"""Rotas da API web — reexporta todos os routers por domínio."""

from app.presentation.web.routes.episodes import router as episodes_router
from app.presentation.web.routes.history import router as history_router
from app.presentation.web.routes.playback import router as playback_router
from app.presentation.web.routes.sources import router as sources_router
from app.presentation.web.routes.watch_later import router as watch_later_router

__all__ = ["episodes_router", "history_router", "playback_router", "sources_router", "watch_later_router"]
