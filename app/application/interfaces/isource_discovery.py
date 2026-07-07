from abc import ABC, abstractmethod

from app.application.models import SourceEntry


class ISourceDiscovery(ABC):
    @abstractmethod
    def discover(self) -> dict[str, SourceEntry]:
        pass

    @abstractmethod
    def get_all_entries(self) -> list[SourceEntry]:
        pass

    @abstractmethod
    def get_enabled_entries(self) -> list[SourceEntry]:
        pass

    @abstractmethod
    def is_available(self, identifier: str) -> bool:
        pass
