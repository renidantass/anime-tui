"""Interface para cliente AniList — application layer."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IAniListClient(ABC):
    @abstractmethod
    def get_genres(self) -> list[str]:
        ...

    @abstractmethod
    def get_anime_by_genre(self, genre: str, *, page: int = 1, per_page: int = 24):
        ...

    @abstractmethod
    def get_airing_schedule(self, *, days: int = 7) -> list:
        ...

    @abstractmethod
    def lookup(self, *, title: str = "", media_id: int | None = None):
        ...
