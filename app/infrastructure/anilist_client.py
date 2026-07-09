"""Cliente AniList (GraphQL) — catálogo, lookup e metadados ricos sem API key."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

ANILIST_URL = "https://graphql.anilist.co"
_TIMEOUT = 20

# Rótulos em PT para a UI (chaves = GenreCollection da AniList).
GENRE_LABELS_PT: dict[str, str] = {
    "Action": "Ação",
    "Adventure": "Aventura",
    "Comedy": "Comédia",
    "Drama": "Drama",
    "Ecchi": "Ecchi",
    "Fantasy": "Fantasia",
    "Horror": "Terror",
    "Mahou Shoujo": "Mahou Shoujo",
    "Mecha": "Mecha",
    "Music": "Música",
    "Mystery": "Mistério",
    "Psychological": "Psicológico",
    "Romance": "Romance",
    "Sci-Fi": "Sci-Fi",
    "Slice of Life": "Slice of Life",
    "Sports": "Esportes",
    "Supernatural": "Sobrenatural",
    "Thriller": "Thriller",
}

SEASON_LABELS_PT: dict[str, str] = {
    "WINTER": "Inverno",
    "SPRING": "Primavera",
    "SUMMER": "Verão",
    "FALL": "Outono",
}

STATUS_LABELS_PT: dict[str, str] = {
    "FINISHED": "Completo",
    "RELEASING": "Em exibição",
    "NOT_YET_RELEASED": "Em breve",
    "CANCELLED": "Cancelado",
    "HIATUS": "Hiato",
}

FORMAT_LABELS: dict[str, str] = {
    "TV": "TV",
    "TV_SHORT": "TV Short",
    "MOVIE": "Filme",
    "SPECIAL": "Special",
    "OVA": "OVA",
    "ONA": "ONA",
    "MUSIC": "Music",
}

RELATION_LABELS_PT: dict[str, str] = {
    "PREQUEL": "Anterior",
    "SEQUEL": "Continuação",
    "PARENT": "Principal",
    "SIDE_STORY": "História paralela",
    "SPIN_OFF": "Spin-off",
    "ALTERNATIVE": "Alternativo",
    "SUMMARY": "Resumo",
    "COMPILATION": "Compilação",
    "CONTAINS": "Contém",
    "OTHER": "Relacionado",
    "CHARACTER": "Personagem",
    "ADAPTATION": "Adaptação",
    "SOURCE": "Obra original",
}

_MEDIA_FIELDS = """
  id
  title {
    romaji
    english
    native
  }
  coverImage {
    large
    medium
    extraLarge
  }
  bannerImage
  averageScore
  meanScore
  popularity
  favourites
  genres
  season
  seasonYear
  format
  status
  episodes
  duration
  description(asHtml: false)
  studios(isMain: true) {
    nodes {
      id
      name
    }
  }
  startDate {
    year
    month
    day
  }
  endDate {
    year
    month
    day
  }
  nextAiringEpisode {
    airingAt
    timeUntilAiring
    episode
  }
  trailer {
    id
    site
  }
"""

_GENRES_QUERY = """
query {
  GenreCollection
}
"""

_BY_GENRE_QUERY = f"""
query ($genre: String, $page: Int, $perPage: Int) {{
  Page(page: $page, perPage: $perPage) {{
    pageInfo {{
      total
      currentPage
      lastPage
      hasNextPage
      perPage
    }}
    media(genre: $genre, type: ANIME, sort: POPULARITY_DESC, isAdult: false) {{
      {_MEDIA_FIELDS}
    }}
  }}
}}
"""

_SEARCH_QUERY = f"""
query ($search: String, $page: Int, $perPage: Int) {{
  Page(page: $page, perPage: $perPage) {{
    pageInfo {{
      total
      currentPage
      hasNextPage
      perPage
    }}
    media(search: $search, type: ANIME, sort: SEARCH_MATCH, isAdult: false) {{
      {_MEDIA_FIELDS}
    }}
  }}
}}
"""

_MEDIA_BY_ID_QUERY = f"""
query ($id: Int) {{
  Media(id: $id, type: ANIME) {{
    {_MEDIA_FIELDS}
    streamingEpisodes {{
      title
      thumbnail
      url
      site
    }}
    relations {{
      edges {{
        relationType(version: 2)
        node {{
          id
          type
          format
          status
          season
          seasonYear
          episodes
          averageScore
          title {{
            romaji
            english
            native
          }}
          coverImage {{
            large
            medium
          }}
        }}
      }}
    }}
  }}
}}
"""

_AIRING_SCHEDULE_QUERY = """
query ($page: Int, $perPage: Int, $airingAtGreater: Int, $airingAtLesser: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo {
      total
      currentPage
      hasNextPage
      perPage
    }
    airingSchedules(
      notYetAired: true
      sort: TIME
      airingAt_greater: $airingAtGreater
      airingAt_lesser: $airingAtLesser
    ) {
      id
      airingAt
      timeUntilAiring
      episode
      media {
        id
        type
        isAdult
        format
        status
        episodes
        averageScore
        season
        seasonYear
        genres
        title {
          romaji
          english
          native
        }
        coverImage {
          large
          medium
        }
        studios(isMain: true) {
          nodes {
            name
          }
        }
      }
    }
  }
}
"""


def _strip_html(text: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _date_label(d: dict | None) -> str:
    if not d or not d.get("year"):
        return ""
    y, m, day = d.get("year"), d.get("month"), d.get("day")
    if m and day:
        return f"{day:02d}/{m:02d}/{y}"
    if m:
        return f"{m:02d}/{y}"
    return str(y)


@dataclass(slots=True)
class AniListRelation:
    id: int
    relation_type: str
    title: str = ""
    image: str = ""
    format: str = ""
    status: str = ""
    season: str = ""
    year: int | None = None
    episodes: int | None = None
    score: int | None = None
    media_type: str = "ANIME"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "relation_type": self.relation_type,
            "relation_label": RELATION_LABELS_PT.get(
                self.relation_type, self.relation_type or "Relacionado"
            ),
            "title": self.title,
            "image": self.image,
            "format": self.format,
            "format_label": FORMAT_LABELS.get(self.format, self.format or ""),
            "status": self.status,
            "status_label": STATUS_LABELS_PT.get(self.status, self.status or ""),
            "season": self.season,
            "season_label": SEASON_LABELS_PT.get(self.season, self.season or ""),
            "year": self.year,
            "episodes": self.episodes,
            "score": self.score,
            "type": self.media_type,
        }


@dataclass(slots=True)
class AniListMedia:
    id: int
    title_romaji: str = ""
    title_english: str = ""
    title_native: str = ""
    image: str = ""
    banner: str = ""
    score: int | None = None
    mean_score: int | None = None
    popularity: int | None = None
    favourites: int | None = None
    genres: list[str] = field(default_factory=list)
    season: str = ""
    year: int | None = None
    format: str = ""
    status: str = ""
    episodes: int | None = None
    duration: int | None = None
    description: str = ""
    studios: list[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    next_episode: int | None = None
    next_airing_at: int | None = None
    relations: list[AniListRelation] = field(default_factory=list)
    # thumbs/títulos por ep (Crunchyroll etc. via AniList)
    episode_thumbs: list[dict] = field(default_factory=list)

    @property
    def primary_title(self) -> str:
        return (
            self.title_romaji
            or self.title_english
            or self.title_native
            or f"#{self.id}"
        )

    def search_titles(self) -> list[str]:
        """Títulos candidatos para busca nas fontes (ordem de preferência)."""
        seen: set[str] = set()
        out: list[str] = []
        for t in (self.title_romaji, self.title_english, self.title_native):
            t = (t or "").strip()
            if not t:
                continue
            key = t.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
        return out

    def season_line(self) -> str:
        """Ex.: 'Outono 2023' ou só o ano."""
        season = SEASON_LABELS_PT.get(self.season, self.season or "")
        if season and self.year:
            return f"{season} {self.year}"
        if self.year:
            return str(self.year)
        return season

    def to_dict(self, *, include_relations: bool = True) -> dict:
        genres_pt = [GENRE_LABELS_PT.get(g, g) for g in (self.genres or [])]
        data = {
            "id": self.id,
            "title": self.primary_title,
            "titles": self.search_titles(),
            "title_romaji": self.title_romaji,
            "title_english": self.title_english,
            "title_native": self.title_native,
            "image": self.image,
            "banner": self.banner,
            "score": self.score,
            "mean_score": self.mean_score,
            "popularity": self.popularity,
            "favourites": self.favourites,
            "genres": list(self.genres or []),
            "genres_label": genres_pt,
            "season": self.season or "",
            "season_label": SEASON_LABELS_PT.get(self.season, self.season or ""),
            "year": self.year,
            "season_line": self.season_line(),
            "format": self.format or "",
            "format_label": FORMAT_LABELS.get(self.format, self.format or ""),
            "status": self.status or "",
            "status_label": STATUS_LABELS_PT.get(self.status, self.status or ""),
            "episodes": self.episodes,
            "duration": self.duration,
            "description": self.description or "",
            "studios": list(self.studios or []),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "next_episode": self.next_episode,
            "next_airing_at": self.next_airing_at,
        }
        data["episode_thumbs"] = list(self.episode_thumbs or [])
        if include_relations:
            # franquia: prequel/sequel/parent em ordem de relação
            rels = [
                r.to_dict()
                for r in self.relations
                if r.media_type == "ANIME"
                and r.relation_type
                in {
                    "PREQUEL",
                    "SEQUEL",
                    "PARENT",
                    "SIDE_STORY",
                    "SPIN_OFF",
                    "ALTERNATIVE",
                    "SUMMARY",
                    "COMPILATION",
                }
            ]
            data["relations"] = rels
            data["franchise"] = _order_franchise(self, rels)
        return data


def _order_franchise(current: AniListMedia, rels: list[dict]) -> list[dict]:
    """Monta trilha de franquia: prequels → atual → sequels."""
    prequels = [r for r in rels if r.get("relation_type") == "PREQUEL"]
    sequels = [r for r in rels if r.get("relation_type") == "SEQUEL"]
    others = [
        r
        for r in rels
        if r.get("relation_type") not in {"PREQUEL", "SEQUEL"}
    ]
    current_card = {
        "id": current.id,
        "relation_type": "CURRENT",
        "relation_label": "Este anime",
        "title": current.primary_title,
        "image": current.image,
        "format": current.format,
        "format_label": FORMAT_LABELS.get(current.format, current.format or ""),
        "status": current.status,
        "status_label": STATUS_LABELS_PT.get(current.status, current.status or ""),
        "season": current.season,
        "season_label": SEASON_LABELS_PT.get(current.season, current.season or ""),
        "year": current.year,
        "episodes": current.episodes,
        "score": current.score,
        "type": "ANIME",
        "is_current": True,
    }
    # prequels do mais antigo (último da lista AniList costuma ser o imediato)
    chain = list(reversed(prequels)) + [current_card] + sequels
    # sidestories etc. no fim
    return chain + others


@dataclass(slots=True)
class AniListPage:
    items: list[AniListMedia]
    page: int
    per_page: int
    has_next: bool
    total: int | None = None


@dataclass(slots=True)
class AiringEntry:
    schedule_id: int
    airing_at: int
    episode: int | None
    time_until: int | None
    media: AniListMedia

    def to_dict(self) -> dict:
        m = self.media.to_dict(include_relations=False)
        return {
            "schedule_id": self.schedule_id,
            "airing_at": self.airing_at,
            "episode": self.episode,
            "time_until": self.time_until,
            "media": m,
            "id": m.get("id"),
            "title": m.get("title"),
            "titles": m.get("titles"),
            "image": m.get("image"),
            "score": m.get("score"),
            "format_label": m.get("format_label"),
            "status_label": m.get("status_label"),
            "studios": m.get("studios") or [],
            "genres_label": m.get("genres_label") or [],
            "season_line": m.get("season_line") or "",
        }


def _parse_streaming_episodes(raw: list | None) -> list[dict]:
    """Extrai nº + thumbnail + título de streamingEpisodes da AniList."""
    out: list[dict] = []
    if not raw:
        return out
    seen: set[str] = set()
    for i, ep in enumerate(raw):
        if not ep:
            continue
        title = (ep.get("title") or "").strip()
        thumb = (ep.get("thumbnail") or "").strip()
        # "Episode 1 - Name" / "Episódio 1: Name"
        num = ""
        m = re.search(
            r"(?:episode|epis[oó]dio|ep)\s*[#.:\-–—]?\s*(\d{1,4})",
            title,
            re.I,
        )
        if m:
            num = str(int(m.group(1)))
        else:
            m2 = re.match(r"^\s*(\d{1,4})\b", title)
            if m2:
                num = str(int(m2.group(1)))
            else:
                num = str(i + 1)
        if num in seen and not thumb:
            continue
        seen.add(num)
        # limpa título (remove "Episode N - ")
        clean = re.sub(
            r"^(?:episode|epis[oó]dio|ep)\s*[#.:\-–—]?\s*\d{1,4}\s*[\-–—:|·]?\s*",
            "",
            title,
            flags=re.I,
        ).strip()
        out.append(
            {
                "number": num,
                "title": clean or title,
                "thumbnail": thumb,
                "site": (ep.get("site") or "") or "",
            }
        )
    return out


def _parse_media(m: dict | None, *, with_relations: bool = False) -> AniListMedia | None:
    if not m:
        return None
    title = m.get("title") or {}
    cover = m.get("coverImage") or {}
    studios_raw = ((m.get("studios") or {}).get("nodes")) or []
    studios = [s.get("name") for s in studios_raw if s and s.get("name")]
    next_ep = m.get("nextAiringEpisode") or {}
    image = (
        cover.get("extraLarge")
        or cover.get("large")
        or cover.get("medium")
        or ""
    ).strip()

    episode_thumbs = _parse_streaming_episodes(m.get("streamingEpisodes"))

    relations: list[AniListRelation] = []
    if with_relations:
        edges = ((m.get("relations") or {}).get("edges")) or []
        for edge in edges:
            if not edge:
                continue
            node = edge.get("node") or {}
            if (node.get("type") or "ANIME") != "ANIME":
                continue
            ntitle = node.get("title") or {}
            ncover = node.get("coverImage") or {}
            rel_title = (
                (ntitle.get("romaji") or "")
                or (ntitle.get("english") or "")
                or (ntitle.get("native") or "")
            ).strip()
            relations.append(
                AniListRelation(
                    id=int(node.get("id") or 0),
                    relation_type=(edge.get("relationType") or "OTHER") or "OTHER",
                    title=rel_title,
                    image=(ncover.get("large") or ncover.get("medium") or "").strip(),
                    format=(node.get("format") or "") or "",
                    status=(node.get("status") or "") or "",
                    season=(node.get("season") or "") or "",
                    year=node.get("seasonYear"),
                    episodes=node.get("episodes"),
                    score=node.get("averageScore"),
                    media_type=(node.get("type") or "ANIME") or "ANIME",
                )
            )

    return AniListMedia(
        id=int(m.get("id") or 0),
        title_romaji=(title.get("romaji") or "").strip(),
        title_english=(title.get("english") or "").strip(),
        title_native=(title.get("native") or "").strip(),
        image=image,
        banner=(m.get("bannerImage") or "").strip(),
        score=m.get("averageScore"),
        mean_score=m.get("meanScore"),
        popularity=m.get("popularity"),
        favourites=m.get("favourites"),
        genres=list(m.get("genres") or []),
        season=(m.get("season") or "") or "",
        year=m.get("seasonYear"),
        format=(m.get("format") or "") or "",
        status=(m.get("status") or "") or "",
        episodes=m.get("episodes"),
        duration=m.get("duration"),
        description=_strip_html(m.get("description") or ""),
        studios=studios,
        start_date=_date_label(m.get("startDate")),
        end_date=_date_label(m.get("endDate")),
        next_episode=next_ep.get("episode"),
        next_airing_at=next_ep.get("airingAt"),
        relations=relations,
        episode_thumbs=episode_thumbs,
    )


class AniListClient:
    """Cliente AniList: gêneros, catálogo, busca e ficha completa."""

    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._genres_cache: list[str] | None = None
        self._genres_cached_at: float = 0.0
        self._genres_ttl = 3600.0  # 1h
        self._media_cache: dict[int, tuple[float, AniListMedia]] = {}
        self._media_ttl = 900.0  # 15 min
        self._search_cache: dict[str, tuple[float, list[AniListMedia]]] = {}
        self._search_ttl = 300.0

    def _post(self, query: str, variables: dict | None = None) -> dict:
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            r = self._session.post(
                ANILIST_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.warning("AniList request falhou: %s", e)
            raise
        if "errors" in data and data["errors"]:
            msg = data["errors"][0].get("message", "AniList error")
            logger.warning("AniList GraphQL error: %s", msg)
            raise RuntimeError(msg)
        return data.get("data") or {}

    def get_genres(self, *, force: bool = False) -> list[str]:
        now = time.monotonic()
        if (
            not force
            and self._genres_cache is not None
            and (now - self._genres_cached_at) < self._genres_ttl
        ):
            return list(self._genres_cache)

        data = self._post(_GENRES_QUERY)
        raw = data.get("GenreCollection") or []
        # Hentai permanece na collection da API; filtramos do catálogo público
        skip = {"hentai"}
        genres = [
            g
            for g in raw
            if isinstance(g, str) and g.strip() and g.casefold() not in skip
        ]
        self._genres_cache = genres
        self._genres_cached_at = now
        return list(genres)

    def get_anime_by_genre(
        self,
        genre: str,
        *,
        page: int = 1,
        per_page: int = 20,
    ) -> AniListPage:
        genre = (genre or "").strip()
        if not genre:
            return AniListPage(items=[], page=page, per_page=per_page, has_next=False)

        page = max(1, int(page))
        per_page = max(1, min(50, int(per_page)))

        data = self._post(
            _BY_GENRE_QUERY,
            {"genre": genre, "page": page, "perPage": per_page},
        )
        page_data = data.get("Page") or {}
        page_info = page_data.get("pageInfo") or {}
        media = page_data.get("media") or []

        items: list[AniListMedia] = []
        for m in media:
            parsed = _parse_media(m)
            if parsed:
                items.append(parsed)

        return AniListPage(
            items=items,
            page=int(page_info.get("currentPage") or page),
            per_page=int(page_info.get("perPage") or per_page),
            has_next=bool(page_info.get("hasNextPage")),
            total=page_info.get("total"),
        )

    def search(self, query: str, *, page: int = 1, per_page: int = 8) -> list[AniListMedia]:
        q = (query or "").strip()
        if not q:
            return []
        key = f"{q.casefold()}|{page}|{per_page}"
        now = time.monotonic()
        cached = self._search_cache.get(key)
        if cached and cached[0] > now:
            return list(cached[1])

        data = self._post(
            _SEARCH_QUERY,
            {"search": q, "page": max(1, page), "perPage": max(1, min(20, per_page))},
        )
        media = ((data.get("Page") or {}).get("media")) or []
        items = [p for m in media if (p := _parse_media(m))]
        self._search_cache[key] = (now + self._search_ttl, items)
        if len(self._search_cache) > 200:
            expired = [k for k, (exp, _) in self._search_cache.items() if exp <= now]
            for k in expired:
                self._search_cache.pop(k, None)
        return items

    def get_media(self, media_id: int, *, with_relations: bool = True) -> AniListMedia | None:
        mid = int(media_id or 0)
        if mid <= 0:
            return None
        now = time.monotonic()
        cached = self._media_cache.get(mid)
        if cached and cached[0] > now:
            return cached[1]

        data = self._post(_MEDIA_BY_ID_QUERY, {"id": mid})
        parsed = _parse_media(data.get("Media"), with_relations=with_relations)
        if parsed:
            self._media_cache[mid] = (now + self._media_ttl, parsed)
        return parsed

    def get_airing_schedule(
        self,
        *,
        days: int = 7,
        per_page: int = 50,
        max_pages: int = 4,
    ) -> list[AiringEntry]:
        """
        Lançamentos (episódios) nos próximos ``days`` dias.
        Retorna lista ordenada por airingAt.
        """
        days = max(1, min(14, int(days)))
        now = int(time.time())
        end = now + days * 24 * 3600
        out: list[AiringEntry] = []
        page = 1
        while page <= max_pages:
            data = self._post(
                _AIRING_SCHEDULE_QUERY,
                {
                    "page": page,
                    "perPage": max(1, min(50, per_page)),
                    "airingAtGreater": now - 60,  # inclui o que está saindo agora
                    "airingAtLesser": end,
                },
            )
            page_data = data.get("Page") or {}
            schedules = page_data.get("airingSchedules") or []
            page_info = page_data.get("pageInfo") or {}
            for s in schedules:
                if not s:
                    continue
                media_raw = s.get("media") or {}
                if media_raw.get("isAdult"):
                    continue
                if (media_raw.get("type") or "ANIME") != "ANIME":
                    continue
                media = _parse_media(media_raw)
                if not media:
                    continue
                airing_at = int(s.get("airingAt") or 0)
                if airing_at <= 0 or airing_at > end:
                    continue
                out.append(
                    AiringEntry(
                        schedule_id=int(s.get("id") or 0),
                        airing_at=airing_at,
                        episode=s.get("episode"),
                        time_until=s.get("timeUntilAiring"),
                        media=media,
                    )
                )
            if not page_info.get("hasNextPage") or not schedules:
                break
            page += 1

        out.sort(key=lambda e: e.airing_at)
        return out

    def lookup(
        self,
        *,
        title: str = "",
        media_id: int | None = None,
    ) -> AniListMedia | None:
        """Resolve ficha completa por id ou pelo melhor match de título."""
        if media_id:
            try:
                full = self.get_media(int(media_id), with_relations=True)
                if full:
                    return full
            except Exception as e:
                logger.debug("AniList get_media(%s): %s", media_id, e)

        cleaned = clean_anime_title(title)
        if not cleaned:
            return None

        # tenta título limpo e, se ainda for longo, uma versão mais curta
        queries = [cleaned]
        short = _short_query(cleaned)
        if short and short not in queries:
            queries.append(short)

        best: AniListMedia | None = None
        best_score = 0.0
        for q in queries:
            try:
                hits = self.search(q, per_page=8)
            except Exception as e:
                logger.warning("AniList search falhou (%s): %s", q, e)
                continue
            for m in hits:
                score = _title_score(q, m)
                # prefere TV "principal" a OVA/Special/Movie com score parecido
                score += _format_bonus(m)
                if score > best_score:
                    best_score = score
                    best = m

        # exige match mínimo pra não enriquecer com obra errada
        if not best or best_score < 0.55:
            return None
        try:
            full = self.get_media(best.id, with_relations=True)
            return full or best
        except Exception:
            return best


def clean_anime_title(title: str) -> str:
    """Remove ruído de fontes BR (dublado, todos os episódios, etc.)."""
    t = (title or "").strip()
    if not t:
        return ""
    # sufixos/padrões comuns nos scrapers
    noise = [
        r"\btodos\s+os\s+epis[oó]dios?\b.*$",
        r"\ball\s+episodes?\b.*$",
        r"\bonline\b.*$",
        r"\bassistir\b.*$",
        r"\bcompleto\b",
        r"\bdublado\b",
        r"\blegendado\b",
        r"\bhd\b",
        r"\bfull\s*hd\b",
        r"\b\d{3,4}p\b",
        r"\btemporada\s*\d+\b",
        r"\bseason\s*\d+\b",
        r"\b[(\[]\s*(?:dub|leg|dublado|legendado)\s*[)\]]",
    ]
    for pat in noise:
        t = re.sub(pat, " ", t, flags=re.I)
    t = re.sub(r"\s*[\-|–—:]\s*$", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—|:")
    return t


def _short_query(title: str) -> str:
    """Primeiros tokens úteis (ajuda quando sobra lixo no título)."""
    parts = [p for p in _norm(title).split() if len(p) > 1][:6]
    return " ".join(parts)


def _format_bonus(media: AniListMedia) -> float:
    fmt = (media.format or "").upper()
    if fmt == "TV":
        return 0.08
    if fmt in {"TV_SHORT", "ONA"}:
        return 0.02
    if fmt in {"MOVIE", "OVA", "SPECIAL", "MUSIC"}:
        return -0.12
    return 0.0


def _title_score(query: str, media: AniListMedia) -> float:
    q = _norm(query)
    if not q:
        return 0.0
    best = 0.0
    for t in media.search_titles():
        nt = _norm(t)
        if not nt:
            continue
        if q == nt:
            return 1.0
        if q in nt or nt in q:
            best = max(best, 0.85 * min(len(q), len(nt)) / max(len(q), len(nt)))
        qa, ta = set(q.split()), set(nt.split())
        if qa and ta:
            best = max(best, len(qa & ta) / max(len(qa), len(ta)))
    return best


def _norm(text: str) -> str:
    t = (text or "").casefold().strip()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


_default_client: AniListClient | None = None


def get_anilist_client() -> AniListClient:
    global _default_client
    if _default_client is None:
        _default_client = AniListClient()
    return _default_client
