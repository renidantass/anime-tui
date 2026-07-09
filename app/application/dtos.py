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
    def __init__(
        self,
        name: str,
        video_src: str,
        link: str,
        color: str = "",
        variant: str = "",
        title: str = "",
    ):
        self.name = name
        self.video_src = video_src
        self.link = link
        self.color = color
        # dublado | legendado | original — p/ menu de áudio na UI
        self.variant = variant or ""
        # título bruto da listagem (ex.: "Foo Dublado - Ep 3")
        self.title = title or ""


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
        anilist_id: int | None = None,
        meta: dict | None = None,
    ):
        self.title = title
        self.rating = rating
        self.image = image
        self.sources = sources or []
        self.anilist_id = anilist_id
        self.meta = meta or {}


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


# Use-case: resolução de stream com fallback


@dataclass(slots=True)
class PlayCandidate:
    name: str
    link: str
    color: str = ""


@dataclass(slots=True)
class ResolvedPlay:
    ctx: "PlayContext | None" = None  # noqa: F821
    link: str = ""
    source_name: str = ""
    source_color: str = ""
    playable: bool = False
    tried: list[dict] | None = None

    def __post_init__(self):
        if self.tried is None:
            self.tried = []


# Use-case: resultado completo de play (orquestração)


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


# Use-case: catálogo de gêneros (resolve contra fontes)


@dataclass(slots=True)
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
            self.titles = []
        if self.studios is None:
            self.studios = []
        if self.genres is None:
            self.genres = []
        if self.genres_label is None:
            self.genres_label = []

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
