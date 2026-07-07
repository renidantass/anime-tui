from __future__ import annotations

from app.application.anime_service import AnimeService
from app.application.models import EpisodeEntry, AnimeEntry, SourceEntry
from app.application.dtos import AnimeDetail

_service: AnimeService | None = None


def set_service(service: AnimeService) -> None:
    global _service
    _service = service


def init_sources() -> None:
    assert _service is not None
    _service.init_sources()


def get_last_episodes() -> list[EpisodeEntry]:
    assert _service is not None
    return _service.get_last_episodes()


def search_by(name: str) -> list[AnimeEntry]:
    assert _service is not None
    return _service.search_by(name)


def get_anime_details(link: str) -> AnimeDetail:
    assert _service is not None
    return _service.get_anime_details(link)


def get_video_src(episode_link: str, preferred_source: str | None = None) -> str:
    assert _service is not None
    return _service.get_video_src(episode_link, preferred_source)


def set_enabled(identifier: str, enabled: bool) -> None:
    assert _service is not None
    _service.set_enabled(identifier, enabled)


def is_enabled(identifier: str) -> bool:
    assert _service is not None
    return _service.is_enabled(identifier)


def get_enabled_source_names() -> list[str]:
    assert _service is not None
    return _service.get_enabled_source_names()


def get_all_source_entries() -> list[SourceEntry]:
    assert _service is not None
    return _service.get_all_source_entries()


def is_source_available(identifier: str) -> bool:
    assert _service is not None
    return _service.is_source_available(identifier)
