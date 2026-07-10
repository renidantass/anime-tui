"""Interfaces para dependências externas da camada de application."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class SessionStore(Protocol):
    """Armazenamento de sessões de stream (token → URL + headers)."""
    def create(self, session: Any) -> str: ...
    def get(self, token: str) -> Any: ...
