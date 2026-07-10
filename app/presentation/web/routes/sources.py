from fastapi import APIRouter, HTTPException

from app.presentation.web import serializers as ser
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import SourceToggle

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _require_known_source(svc, identifier: str) -> None:
    known = {e.identifier for e in svc.get_all_source_entries()}
    if identifier not in known:
        raise HTTPException(404, "Fonte desconhecida")


@router.get("")
def list_sources(state: AppState):
    items = [
        ser.source_entry(e, state.service.is_enabled(e.identifier))
        for e in state.service.get_all_source_entries()
    ]
    return {"items": items}


@router.post("/health")
def refresh_sources_health(state: AppState):
    entries = state.service.refresh_source_health()
    return {
        "items": [
            ser.source_entry(e, state.service.is_enabled(e.identifier)) for e in entries if e
        ]
    }


@router.post("/{identifier}/health")
def refresh_one_source_health(state: AppState, identifier: str):
    _require_known_source(state.service, identifier)
    entries = state.service.refresh_source_health(identifier)
    if not entries or not entries[0]:
        raise HTTPException(404, "Fonte não encontrada")
    e = entries[0]
    return ser.source_entry(e, state.service.is_enabled(e.identifier))


@router.put("/{identifier}")
def toggle_source(state: AppState, identifier: str, body: SourceToggle):
    _require_known_source(state.service, identifier)
    state.service.set_enabled(identifier, body.enabled)
    return {"identifier": identifier, "enabled": body.enabled}
