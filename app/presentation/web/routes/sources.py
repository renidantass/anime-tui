from fastapi import APIRouter, HTTPException

from app.presentation.web import serializers as ser
from app.presentation.web.routes._deps import AppState
from app.presentation.web.schemas import SourceToggle

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _require_known_source(svc, identifier: str) -> None:
    known = {e.identifier for e in svc.get_all_source_entries()}
    if identifier not in known:
        raise HTTPException(404, "Fonte desconhecida")


def _get_circuit_state(svc, identifier: str) -> str:
    sd = getattr(svc, "_sd", None)
    if sd and hasattr(sd, "circuit_state"):
        return sd.circuit_state(identifier)
    return ""


@router.get("")
def list_sources(state: AppState):
    sd = getattr(state.service, "_sd", None)
    items = [
        ser.source_entry(e, state.service.is_enabled(e.identifier))
        for e in state.service.get_all_source_entries()
    ]
    if sd and hasattr(sd, "circuit_state"):
        for item in items:
            item["circuit"] = sd.circuit_state(item["identifier"])
    return {"items": items}


@router.post("/health")
def refresh_sources_health(state: AppState):
    entries = state.service.refresh_source_health()
    items = [ser.source_entry(e, state.service.is_enabled(e.identifier)) for e in entries if e]
    return {
        "items": items,
        "circuits": {
            e["identifier"]: _get_circuit_state(state.service, e["identifier"]) for e in items
        },
    }


@router.post("/{identifier}/health")
def refresh_one_source_health(state: AppState, identifier: str):
    _require_known_source(state.service, identifier)
    entries = state.service.refresh_source_health(identifier)
    if not entries or not entries[0]:
        raise HTTPException(404, "Fonte não encontrada")
    e = entries[0]
    result = ser.source_entry(e, state.service.is_enabled(e.identifier))
    result["circuit"] = _get_circuit_state(state.service, identifier)
    return result


@router.post("/{identifier}/circuit-reset")
def reset_circuit(state: AppState, identifier: str):
    _require_known_source(state.service, identifier)
    sd = getattr(state.service, "_sd", None)
    if sd and hasattr(sd, "circuit_breaker"):
        sd.circuit_breaker.reset(identifier)
        return {"identifier": identifier, "circuit": "reset"}
    raise HTTPException(501, "Circuit breaker não disponível")


@router.put("/{identifier}")
def toggle_source(state: AppState, identifier: str, body: SourceToggle):
    _require_known_source(state.service, identifier)
    state.service.set_enabled(identifier, body.enabled)
    return {"identifier": identifier, "enabled": body.enabled}
