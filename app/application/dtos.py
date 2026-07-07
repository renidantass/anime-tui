from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EpisodeItem:
    number: str
    title: str
    link: str
    video_src: str
    image: str = ''
    date: str = '00/00'


@dataclass(slots=True)
class SeasonDetail:
    number: int
    episodes: list[EpisodeItem]


@dataclass(slots=True)
class AnimeDetail:
    title: str
    rating: str
    link: str
    image: str = ''
    description: str | None = None
    seasons: list[SeasonDetail] | None = None