"""Interface para armazenamento de sessões de stream (token → URL + headers)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable


@runtime_checkable
class ISession(Protocol):
    url: str
    headers: dict[str, str]
    page_url: str
    created_at: float


class ISessionStore(ABC):
    @abstractmethod
    def create(self, session: ISession) -> str:
        ...

    @abstractmethod
    def get(self, token: str) -> ISession | None:
        ...
