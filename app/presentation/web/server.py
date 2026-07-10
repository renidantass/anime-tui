"""Servidor FastAPI — adaptador web para animes-tui."""

from __future__ import annotations

from fastapi import FastAPI, Request

from app.presentation.web.routes import (
    episodes_router,
    history_router,
    playback_router,
    sources_router,
    watch_later_router,
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
    app.include_router(watch_later_router)

    @app.get("/api/health")
    def health(request: Request):
        state = request.app.state
        sources_ready = getattr(state, "sources_ready", False)
        svc = getattr(state, "service", None)
        sources_status: dict = {}
        if svc and sources_ready:
            entries = svc.get_all_source_entries()
            sources_status = {
                e.identifier: {
                    "name": e.name,
                    "available": e.available,
                    "status": e.status,
                    "latency_ms": e.latency_ms,
                    "uptime_percent": e.uptime_percent,
                    "error": e.error or "",
                    "circuit": "",
                }
                for e in entries
            }
            sd = getattr(svc, "_sd", None)
            if sd and hasattr(sd, "circuit_state"):
                for ident, info in sources_status.items():
                    info["circuit"] = sd.circuit_state(ident)

        return {
            "ok": True,
            "sources_ready": sources_ready,
            "sources": sources_status,
        }

    return app
