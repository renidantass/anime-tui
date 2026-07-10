"""Servidor FastAPI — adaptador web para animes-tui."""

from __future__ import annotations

from fastapi import FastAPI, Request

from app.presentation.web.routes import (
    episodes_router,
    history_router,
    playback_router,
    sources_router,
)


def create_app(lifespan=None) -> FastAPI:
    kwargs = {}
    if lifespan:
        kwargs["lifespan"] = lifespan
    app = FastAPI(title="Animes Web", version="0.1.0", **kwargs)

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(playback_router)
    app.include_router(episodes_router)
    app.include_router(history_router)
    app.include_router(sources_router)

    @app.get("/api/health")
    def health(request: Request):
        return {"ok": True, "sources_ready": getattr(request.app.state, "sources_ready", False)}

    return app
