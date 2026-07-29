"""Servidor FastAPI — adaptador web para animes-tui."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.infrastructure.auth import decode_token

from app.presentation.web.routes import (
    episodes_router,
    history_router,
    opening_marks_router,
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

    @app.middleware("http")
    async def authenticate_request(request: Request, call_next):
        token = request.cookies.get("anishelf_token")
        request.state.user = None
        if token:
            try:
                claims = decode_token(token)
                request.state.user = {"id": claims["sub"], "email": claims.get("email", "")}
            except Exception:
                pass
        if not request.url.path.startswith("/api/") or request.url.path.startswith("/api/auth") or request.url.path == "/api/health":
            return await call_next(request)
        if not request.state.user:
            return JSONResponse({"detail": "Autenticação necessária"}, status_code=401)
        return await call_next(request)

    app.include_router(playback_router)
    from app.presentation.web.routes.auth import router as auth_router
    app.include_router(auth_router)
    app.include_router(episodes_router)
    app.include_router(history_router)
    app.include_router(opening_marks_router)
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
