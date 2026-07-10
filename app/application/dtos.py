"""DTOs de aplicação — dados agregados entre fontes, candidatos e resultados de play."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.play_context import PlayContext


@dataclass(slots=True)
class SourceEntry:
    name: str
    identifier: str
    color: str
    has_search: bool = True
    has_details: bool = True
    available: bool = True
    error: str = ""
    base_url: str = ""
    status: str = "unknown"
    latency_ms: float | None = None
    last_check_at: str = ""
    checks_total: int = 0
    checks_ok: int = 0
    uptime_percent: float | None = None
    _recent: list[bool] = field(default_factory=list)


@dataclass(slots=True)
class SourceInfo:
    name: str
    video_src: str
    link: str
    color: str = ""
    variant: str = ""
    title: str = ""


@dataclass(slots=True)
class EpisodeEntry:
    title: str
    image: str
    date: str
    sources: list[SourceInfo] = field(default_factory=list)
    number: str = ""


@dataclass(slots=True)
class AnimeEntry:
    title: str
    rating: str
    image: str
    sources: list[SourceInfo] = field(default_factory=list)
    anilist_id: int | None = None
    meta: dict = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class EpisodeItem:
    number: str
    title: str
    link: str
    video_src: str
    image: str = ""
    date: str = ""


@dataclass(slots=True, frozen=True)
class SeasonDetail:
    number: int
    episodes: list[EpisodeItem]


@dataclass(slots=True, frozen=True)
class AnimeDetail:
    title: str
    rating: str
    link: str
    image: str = ""
    description: str | None = None
    seasons: list[SeasonDetail] | None = None


@dataclass(slots=True)
class PlayCandidate:
    name: str
    link: str
    color: str = ""


@dataclass(slots=True)
class ResolvedPlay:
    ctx: PlayContext | None = None
    link: str = ""
    source_name: str = ""
    source_color: str = ""
    playable: bool = False
    tried: list[dict] | None = None

    def __post_init__(self):
        if self.tried is None:
            self.tried = []


@dataclass(slots=True)
class PlayResult:
    playable: bool
    stream_url: str | None
    page_url: str
    external_url: str | None
    is_hls: bool
    start_at: float
    token: str | None
    source_name: str
    source_color: str
    episode_link: str
    switched: bool
    tried: list[dict] | None = None

    def __post_init__(self):
        if self.tried is None:
            self.tried = []


@dataclass(slots=True, frozen=True)
class GenreResolveItem:
    id: int = 0
    title: str = ""
    titles: list[str] | None = None
    image: str = ""
    score: int | None = None
    banner: str = ""
    season: str = ""
    season_label: str = ""
    season_line: str = ""
    year: int | None = None
    format: str = ""
    format_label: str = ""
    status: str = ""
    status_label: str = ""
    episodes: int | None = None
    studios: list[str] | None = None
    genres: list[str] | None = None
    genres_label: list[str] | None = None
    description: str = ""

    def __post_init__(self):
        if self.titles is None:
            object.__setattr__(self, "titles", [])
        if self.studios is None:
            object.__setattr__(self, "studios", [])
        if self.genres is None:
            object.__setattr__(self, "genres", [])
        if self.genres_label is None:
            object.__setattr__(self, "genres_label", [])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "titles": self.titles,
            "image": self.image,
            "score": self.score,
            "banner": self.banner,
            "season": self.season,
            "season_label": self.season_label,
            "season_line": self.season_line,
            "year": self.year,
            "format": self.format,
            "format_label": self.format_label,
            "status": self.status,
            "status_label": self.status_label,
            "episodes": self.episodes,
            "studios": self.studios,
            "genres": self.genres,
            "genres_label": self.genres_label,
            "description": self.description,
        }


@dataclass(slots=True, frozen=True)
class AniListSearchMedia:
    id: int
    title_romaji: str = ""
    title_english: str = ""
    title_native: str = ""
    image: str = ""
    score: int | None = None
    season: str = ""
    year: int | None = None
    format: str = ""
    status: str = ""
    episodes: int | None = None
    description: str = ""
    studios: list[str] | None = None
    genres: list[str] | None = None
    banner: str = ""

    @property
    def primary_title(self) -> str:
        return self.title_romaji or self.title_english or self.title_native or ""

    def search_titles(self) -> list[str]:
        titles: list[str] = []
        for t in (self.title_romaji, self.title_english, self.title_native):
            if t and t not in titles:
                titles.append(t)
        return titles or [self.primary_title]
