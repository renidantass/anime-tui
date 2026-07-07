from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.interfaces import IAnimeFeedReader


class SourceEntry:
    def __init__(self, source: IAnimeFeedReader, available: bool = True, error: str = ""):
        self.source = source
        self.available = available
        self.error = error


class SourceInfo:
    def __init__(self, name: str, video_src: str, link: str, color: str = ""):
        self.name = name
        self.video_src = video_src
        self.link = link
        self.color = color


class EpisodeEntry:
    def __init__(
        self,
        title: str,
        image: str,
        date: str,
        sources: list[SourceInfo] | None = None,
    ):
        self.title = title
        self.image = image
        self.date = date
        self.sources = sources or []

    @property
    def source_names(self) -> list[str]:
        return [s.name for s in self.sources]


class AnimeEntry:
    def __init__(
        self,
        title: str,
        rating: str,
        image: str,
        sources: list[SourceInfo] | None = None,
    ):
        self.title = title
        self.rating = rating
        self.image = image
        self.sources = sources or []

    @property
    def source_names(self) -> list[str]:
        return [s.name for s in self.sources]
