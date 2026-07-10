"""Rotas de gerenciamento de fontes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.presentation.web import serializers as ser
from app.presentation.web.schemas import SourceToggle

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
def list_sources(request: Request):
    state = request.app.state
    ensure_sources(state)
    svc = state.service
    items = [
        ser.source_entry(e, svc.is_enabled(e.identifier))
        for e in svc.get_all_source_entries()
    ]
    return {"items": items}


@router.post("/health")
def refresh_sources_health(request: Request):
    state = request.app.state
    ensure_sources(state)
    svc = state.service
    entries = svc.refresh_source_health()
    return {
        "items": [
            ser.source_entry(e, svc.is_enabled(e.identifier)) for e in entries if e
        ]
    }


@router.post("/{identifier}/health")
def refresh_one_source_health(request: Request, identifier: str):
    state = request.app.state
    ensure_sources(state)
    svc = state.service
    known = {e.identifier for e in svc.get_all_source_entries()}
    if identifier not in known:
        raise HTTPException(404, "Fonte desconhecida")
    entries = svc.refresh_source_health(identifier)
    if not entries or not entries[0]:
        raise HTTPException(404, "Fonte não encontrada")
    e = entries[0]
    return ser.source_entry(e, svc.is_enabled(e.identifier))


@router.put("/{identifier}")
def toggle_source(request: Request, identifier: str, body: SourceToggle):
    state = request.app.state
    ensure_sources(state)
    svc = state.service
    known = {e.identifier for e in svc.get_all_source_entries()}
    if identifier not in known:
        raise HTTPException(404, "Fonte desconhecida")
    svc.set_enabled(identifier, body.enabled)
    return {"identifier": identifier, "enabled": body.enabled}
