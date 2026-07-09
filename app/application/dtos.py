from __future__ import annotations

from dataclasses import dataclass


# Use-case: listagem de últimos episódios / busca


class SourceEntry:
    def __init__(
        self,
        name: str,
        identifier: str,
        color: str,
        has_search: bool = True,
        has_details: bool = True,
        available: bool = True,
        error: str = "",
        base_url: str = "",
    ):
        self.name = name
        self.identifier = identifier
        self.color = color
        self.has_search = has_search
        self.has_details = has_details
        self.available = available
        self.error = error
        self.base_url = base_url
        # health / uptime
        self.status: str = "unknown"  # unknown | checking | online | offline
        self.latency_ms: float | None = None
        self.last_check_at: str = ""
        self.checks_total: int = 0
        self.checks_ok: int = 0
        self.uptime_percent: float | None = None
        # janela recente de checks (True=ok) — não serializar bruto
        self._recent: list[bool] = []


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
        number: str = "",
    ):
        self.title = title
        self.image = image
        self.date = date
        self.sources = sources or []
        self.number = number or ""


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


# Use-case: detalhes do anime


@dataclass(slots=True, frozen=True)
class EpisodeItem:
    number: str
    title: str
    link: str
    video_src: str
    image: str = ''
    date: str = ''


@dataclass(slots=True, frozen=True)
class SeasonDetail:
    number: int
    episodes: list[EpisodeItem]


@dataclass(slots=True, frozen=True)
class AnimeDetail:
    title: str
    rating: str
    link: str
    image: str = ''
    description: str | None = None
    seasons: list[SeasonDetail] | None = None