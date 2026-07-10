from __future__ import annotations

import logging
import re
import time
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from concurrent.futures import as_completed

from app.application.dtos import (
    AnimeDetail,
    AnimeEntry,
    AniListSearchMedia,
    EpisodeEntry,
    EpisodeItem,
    SeasonDetail,
    SourceEntry,
    SourceInfo,
)
from app.application.interfaces import ISourceDiscovery
from app.application.title_utils import (
    detect_audio_variant,
    extract_episode_number,
    is_unknown_episode_number,
    normalize_watch_titles,
    prefer_display_title,
    strip_title_variants,
)
from app.domain import Anime, Episode, PlayContext

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
# Pool dedicado p/ cruzar AniList × fontes (evita deadlock e permite mais paralelismo)
_genre_executor: ThreadPoolExecutor | None = None

# Cache de resolve: chave → (expires_at, AnimeEntry | None)
_resolve_cache: dict[str, tuple[float, AnimeEntry | None]] = {}
_RESOLVE_CACHE_TTL = 600.0  # 10 min


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=8)
    return _executor


def _get_genre_executor() -> ThreadPoolExecutor:
    global _genre_executor
    if _genre_executor is None:
        _genre_executor = ThreadPoolExecutor(max_workers=20)
    return _genre_executor


def _episode_to_item(ep: Episode) -> EpisodeItem:
    return EpisodeItem(
        number=ep.number,
        title=ep.title,
        link=ep.link,
        video_src=ep.video_src,
        image=ep.image,
        date=ep.date,
    )


class AnimeService:
    def __init__(
        self,
        source_discovery: ISourceDiscovery,
        anilist: AniListClient | None = None,
    ):
        self._sd = source_discovery
        self._enabled: set[str] = set()
        self._anilist = anilist or get_anilist_client()

    def init_sources(self):
        self._sd.discover()
        self._reset_enabled()

    def _reset_enabled(self):
        # por padrão todas as descobertas começam ativas (mesmo se offline no 1º check)
        self._enabled = {e.identifier for e in self._sd.get_all_entries()}

    def set_enabled(self, identifier: str, enabled: bool):
        if enabled:
            self._enabled.add(identifier)
        else:
            self._enabled.discard(identifier)

    def is_enabled(self, identifier: str) -> bool:
        return identifier in self._enabled

    def get_all_source_entries(self) -> list[SourceEntry]:
        return self._sd.get_all_entries()

    def is_source_available(self, identifier: str) -> bool:
        return self._sd.is_available(identifier)

    def refresh_source_health(self, identifier: str | None = None) -> list[SourceEntry]:
        """Revalida disponibilidade/latência/uptime das fontes."""
        sd = self._sd
        if hasattr(sd, "check_one") and identifier:
            entry = sd.check_one(identifier)
            return [entry] if entry else []
        if hasattr(sd, "check_all"):
            return list(sd.check_all(mark_checking=True))
        return self.get_all_source_entries()

    def _get_enabled_list(self) -> list[SourceEntry]:
        # ativa pelo usuário E online no último health check
        return [
            e
            for e in self._sd.get_all_entries()
            if e.identifier in self._enabled and e.available
        ]

    @staticmethod
    def _normalize(text: str) -> str:
        t = text.lower().strip()
        t = ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
        t = re.sub(r'[-–—:_/|]', ' ', t)
        t = re.sub(r'\bepisodio\b', 'ep', t)
        t = re.sub(r'\s+', ' ', t)
        return t.strip()

    @classmethod
    def _catalog_key(cls, title: str) -> str:
        """Chave de catálogo: ignora Dublado/Legendado/HD, mantém temporada."""
        return cls._normalize(strip_title_variants(title or ""))

    @classmethod
    def _ep_key(cls, ep: Episode) -> str:
        """Mesma obra + mesmo nº = 1 card (Legendado e Dublado colapsam)."""
        number = ep.number if not is_unknown_episode_number(ep.number) else ""
        if not number:
            number = extract_episode_number(ep.title, getattr(ep, "link", "") or "", default="")
        anime_t, _, num = normalize_watch_titles(ep.title or "", ep.title or "", number)
        base = cls._catalog_key(anime_t or ep.title or "")
        if num and not is_unknown_episode_number(num):
            n = str(int(num)) if str(num).strip().isdigit() else str(num).strip()
            return f"{base}|{n}"
        return cls._catalog_key(ep.title or "")

    @classmethod
    def _anime_key(cls, a: Anime) -> str:
        return cls._catalog_key(a.title or "")

    @staticmethod
    def _append_source(
        bucket: list[SourceInfo],
        *,
        name: str,
        video_src: str,
        link: str,
        color: str,
        title: str = "",
    ) -> None:
        """Mantém dublado e legendado da mesma fonte (links diferentes)."""
        link = (link or "").strip()
        variant = detect_audio_variant(title, link)
        for s in bucket:
            if link and s.link and s.link == link:
                return
            # mesma fonte + mesma variante de áudio → 1 slot
            if s.name == name and (s.variant or "original") == variant:
                return
        bucket.append(
            SourceInfo(
                name=name,
                video_src=video_src or "",
                link=link,
                color=color or "",
                variant=variant,
                title=title or "",
            )
        )

    def get_last_episodes(self) -> list[EpisodeEntry]:
        entries: dict[str, EpisodeEntry] = {}
        sources = self._get_enabled_list()
        if not sources:
            return []

        def fetch(entry: SourceEntry) -> tuple[str, list[Episode]]:
            reader = self._sd.get_reader(entry.identifier)
            return entry.name, reader.get_last_episodes() if reader else []

        futures = {_get_executor().submit(fetch, e): e for e in sources}
        for future in as_completed(futures):
            entry = futures[future]
            name = entry.name
            try:
                _, episodes = future.result()
            except Exception as e:
                logger.warning("Falha ao obter episódios de %s: %s", name, e)
                continue
            for ep in episodes:
                number = ep.number if not is_unknown_episode_number(ep.number) else ""
                if not number:
                    number = extract_episode_number(ep.title, ep.link, default="")
                key = self._ep_key(ep)
                if key not in entries:
                    entries[key] = EpisodeEntry(
                        title=ep.title,
                        image=ep.image,
                        date=ep.date,
                        number=number,
                    )
                else:
                    existing = entries[key]
                    # preenche número se a primeira fonte não tinha
                    if is_unknown_episode_number(existing.number) and number:
                        existing.number = number
                    # evita card “X” e “X Dublado” — fica o título mais limpo
                    existing.title = prefer_display_title(existing.title, ep.title)
                    if not existing.image and ep.image:
                        existing.image = ep.image
                    if not existing.date and ep.date:
                        existing.date = ep.date
                self._append_source(
                    entries[key].sources,
                    name=name,
                    video_src=ep.video_src,
                    link=ep.link,
                    color=entry.color,
                    title=ep.title,
                )

        return list(entries.values())

    def search_by(self, name: str) -> list[AnimeEntry]:
        entries: dict[str, AnimeEntry] = {}
        sources = [e for e in self._get_enabled_list() if e.has_search]
        if not sources:
            return []

        def fetch(entry: SourceEntry) -> tuple[str, list[Anime]]:
            reader = self._sd.get_reader(entry.identifier)
            return entry.name, reader.search_by(name) if reader else []

        futures = {_get_executor().submit(fetch, e): e for e in sources}
        for future in as_completed(futures):
            entry = futures[future]
            source_name = entry.name
            try:
                _, animes = future.result()
            except Exception as e:
                logger.warning("Falha ao buscar em %s: %s", source_name, e)
                continue
            for anime in animes:
                key = self._anime_key(anime)
                if key not in entries:
                    entries[key] = AnimeEntry(
                        title=anime.title,
                        rating=anime.rating,
                        image=anime.image,
                    )
                else:
                    existing = entries[key]
                    existing.title = prefer_display_title(existing.title, anime.title)
                    if not existing.image and anime.image:
                        existing.image = anime.image
                    if not existing.rating and anime.rating:
                        existing.rating = anime.rating
                self._append_source(
                    entries[key].sources,
                    name=source_name,
                    video_src="",
                    link=anime.link,
                    color=entry.color,
                    title=anime.title,
                )

        return list(entries.values())

    # ── AniList: catálogo por gênero (só o que existe nas fontes) ───────────

    def get_genres(self) -> list[dict[str, str]]:
        """Lista de gêneros da AniList com rótulo PT para a UI."""
        try:
            names = self._anilist.get_genres()
        except Exception as e:
            logger.warning("Falha ao listar gêneros AniList: %s", e)
            return []
        return [
            {
                "id": name,
                "name": name,
                "label": self._genre_labels.get(name, name),
            }
            for name in names
        ]

    def catalog_by_genre(
        self,
        genre: str,
        *,
        page: int = 1,
        per_page: int = 24,
    ) -> dict:
        """Só AniList — rápido, sem checar fontes. Para UI progressiva."""
        genre = (genre or "").strip()
        empty = {
            "genre": genre,
            "label": self._genre_labels.get(genre, genre) if genre else "",
            "page": page,
            "per_page": per_page,
            "has_next": False,
            "items": [],
        }
        if not genre:
            return empty
        try:
            al_page = self._anilist.get_anime_by_genre(
                genre, page=page, per_page=min(50, max(1, per_page))
            )
        except Exception as e:
            logger.warning("Falha AniList catalog genre=%s: %s", genre, e)
            empty["error"] = str(e)
            return empty

        items = []
        for m in al_page.items:
            d = m.to_dict(include_relations=False)
            # payload leve pro catálogo (sem relations)
            items.append(
                {
                    "id": d["id"],
                    "title": d["title"],
                    "titles": d["titles"],
                    "image": d["image"],
                    "banner": d.get("banner") or "",
                    "score": d.get("score"),
                    "year": d.get("year"),
                    "season": d.get("season") or "",
                    "season_label": d.get("season_label") or "",
                    "season_line": d.get("season_line") or "",
                    "genres": d.get("genres") or [],
                    "genres_label": d.get("genres_label") or [],
                    "format": d.get("format") or "",
                    "format_label": d.get("format_label") or "",
                    "status": d.get("status") or "",
                    "status_label": d.get("status_label") or "",
                    "episodes": d.get("episodes"),
                    "studios": d.get("studios") or [],
                    "description": (d.get("description") or "")[:280],
                }
            )
        return {
            "genre": genre,
            "label": self._genre_labels.get(genre, genre),
            "page": al_page.page,
            "per_page": al_page.per_page,
            "has_next": al_page.has_next,
            "anilist_total": al_page.total,
            "items": items,
        }

    def get_anilist_meta(
        self,
        *,
        title: str = "",
        anilist_id: int | None = None,
    ) -> dict | None:
        """Ficha rica da AniList (season, studios, relations/franquia, etc.)."""
        try:
            media = self._anilist.lookup(title=title, media_id=anilist_id)
        except Exception as e:
            logger.warning("AniList meta falhou: %s", e)
            return None
        if not media:
            return None
        data = media.to_dict(include_relations=True)
        # franquia/relacionados: só o que existe nas fontes (+ o atual)
        data["franchise"] = self._filter_franchise_in_sources(
            data.get("franchise") or []
        )
        data["relations"] = [
            r
            for r in (data.get("relations") or [])
            if any(
                f.get("id") == r.get("id") and f.get("available")
                for f in data["franchise"]
            )
            or r.get("relation_type") == "CURRENT"
        ]
        return data

    def get_release_calendar(
        self, *, days: int = 7, check_sources: bool = False
    ) -> dict:
        """
        Calendário de lançamentos (airing schedule AniList).

        Com ``check_sources=True``, marca ``available`` só quando o
        **episódio** existe em alguma fonte. Por padrão não cruza (mais rápido).
        """
        try:
            entries = self._anilist.get_airing_schedule(days=days)
        except Exception as e:
            logger.warning("Calendário AniList falhou: %s", e)
            return {
                "days": days,
                "check_sources": bool(check_sources),
                "total": 0,
                "available_total": 0,
                "items": [],
                "error": str(e),
            }

        flat = [e.to_dict() for e in entries]
        if check_sources:
            annotated = self._annotate_airing_availability(flat)
            available_total = sum(1 for it in annotated if it.get("available"))
            items = annotated
        else:
            items = []
            for it in flat:
                row = dict(it)
                row["available"] = None  # não verificado
                row["sources"] = []
                items.append(row)
            available_total = 0

        return {
            "days": days,
            "check_sources": bool(check_sources),
            "total": len(items),
            "available_total": available_total,
            "items": items,
        }

    def _annotate_airing_availability(self, items: list[dict]) -> list[dict]:
        """
        Para cada lançamento (anime + nº de episódio):
        1) resolve o anime nas fontes
        2) carrega a ficha e confere se o episódio existe
        """
        if not items:
            return []

        # 1) candidatos únicos por id AniList
        candidates: dict[int, dict] = {}
        for it in items:
            mid = int(it.get("id") or 0)
            if mid <= 0 or mid in candidates:
                continue
            titles = list(it.get("titles") or [])
            title = (it.get("title") or "").strip()
            if title and title not in titles:
                titles = [title, *titles]
            candidates[mid] = {
                "id": mid,
                "title": title,
                "titles": titles,
                "image": it.get("image") or "",
                "score": it.get("score"),
            }

        by_id: dict[int, AnimeEntry] = {}
        if candidates:
            found = self.resolve_catalog_items(
                list(candidates.values()), timeout=18.0
            )
            by_id = self._index_resolved_by_anilist_id(found)

        # 2) mapa de episódios por (fonte, link do anime) — paralelo
        # key: "SourceName|https://..."
        detail_jobs: dict[str, tuple[str, str]] = {}
        for entry in by_id.values():
            for src in entry.sources:
                if not src.link or not src.name:
                    continue
                key = f"{src.name}|{src.link}"
                detail_jobs[key] = (src.name, src.link)

        ep_maps: dict[str, dict[str, dict]] = {}
        if detail_jobs:
            pool = _get_genre_executor()
            futures = {
                pool.submit(self._episode_map_for_source_link, name, link): key
                for key, (name, link) in detail_jobs.items()
            }
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    ep_maps[key] = fut.result() or {}
                except Exception as e:
                    logger.debug("mapa de eps falhou %s: %s", key, e)
                    ep_maps[key] = {}

        # 3) anota cada item do calendário
        out: list[dict] = []
        for it in items:
            mid = int(it.get("id") or 0)
            entry = by_id.get(mid)
            row = dict(it)
            ep_target = self._normalize_ep_number(it.get("episode"))

            if not entry or not entry.sources:
                row["available"] = False
                row["sources"] = []
                out.append(row)
                continue

            if entry.title:
                row["source_title"] = entry.title
            if entry.image:
                row["source_image"] = entry.image

            # sem nº de episódio na AniList → não dá para validar ep
            if not ep_target:
                row["available"] = False
                row["sources"] = []
                row["unavailable_reason"] = "episode_unknown"
                out.append(row)
                continue

            matching_sources: list[dict] = []
            for src in entry.sources:
                key = f"{src.name}|{src.link}"
                ep_map = ep_maps.get(key) or {}
                hit = ep_map.get(ep_target)
                if not hit:
                    continue
                matching_sources.append(
                    {
                        "name": src.name,
                        "link": src.link,  # ficha do anime
                        "episode_link": hit.get("link") or "",
                        "color": src.color or "",
                        "video_src": hit.get("video_src") or "",
                        "variant": getattr(src, "variant", "")
                        or detect_audio_variant(
                            getattr(src, "title", "") or "", src.link or ""
                        ),
                        "title": getattr(src, "title", "") or "",
                    }
                )

            if matching_sources:
                row["available"] = True
                row["sources"] = matching_sources
            else:
                row["available"] = False
                row["sources"] = []
                row["unavailable_reason"] = (
                    "anime_only" if entry.sources else "missing"
                )
            out.append(row)
        return out

    def _episode_map_for_source_link(
        self, source_name: str, anime_link: str
    ) -> dict[str, dict]:
        """
        Retorna mapa número_normalizado → {link, title, video_src, image}
        para a ficha do anime na fonte indicada.
        """
        if not anime_link or not source_name:
            return {}
        entry = next(
            (
                e
                for e in self._get_enabled_list()
                if e.has_details and e.name == source_name
            ),
            None,
        )
        if not entry:
            return {}
        try:
            reader = self._sd.get_reader(entry.identifier)
            if not reader:
                return {}
            anime = reader.get_anime_details(anime_link)
        except Exception as e:
            logger.debug(
                "detalhes %s @ %s: %s", source_name, anime_link[:60], e
            )
            return {}
        if not anime or not anime.seasons:
            return {}

        ep_map: dict[str, dict] = {}
        for season in anime.seasons:
            for ep in season.episodes or []:
                num = self._normalize_ep_number(ep.number)
                if not num:
                    num = self._normalize_ep_number(
                        extract_episode_number(ep.title, ep.link, default="")
                    )
                if not num or num in ep_map:
                    continue
                ep_map[num] = {
                    "link": ep.link or "",
                    "title": ep.title or "",
                    "video_src": ep.video_src or "",
                    "image": ep.image or "",
                    "number": num,
                }
        return ep_map

    @staticmethod
    def _normalize_ep_number(value) -> str:
        """Normaliza nº de episódio para comparação ('01' → '1')."""
        if value is None:
            return ""
        s = str(value).strip()
        if not s or is_unknown_episode_number(s):
            return ""
        m = re.search(r"(\d{1,4})", s)
        if not m:
            return ""
        n = m.group(1)
        # rejeita anos sozinhos
        if len(n) == 4 and (n.startswith("19") or n.startswith("20")):
            return ""
        try:
            return str(int(n))
        except ValueError:
            return ""

    def _filter_franchise_in_sources(self, franchise: list[dict]) -> list[dict]:
        """Mantém o anime atual + relacionados presentes nas fontes."""
        if not franchise:
            return []
        current = [
            f
            for f in franchise
            if f.get("is_current") or f.get("relation_type") == "CURRENT"
        ]
        others = [
            f
            for f in franchise
            if not (f.get("is_current") or f.get("relation_type") == "CURRENT")
        ]
        candidates: list[dict] = []
        for f in others:
            mid = int(f.get("id") or 0)
            title = (f.get("title") or "").strip()
            if mid <= 0 or not title:
                continue
            candidates.append(
                {
                    "id": mid,
                    "title": title,
                    "titles": [title],
                    "image": f.get("image") or "",
                    "score": f.get("score"),
                }
            )
        by_id: dict[int, AnimeEntry] = {}
        if candidates:
            found = self.resolve_catalog_items(candidates, timeout=16.0)
            by_id = self._index_resolved_by_anilist_id(found)

        out: list[dict] = []
        for f in current:
            row = dict(f)
            row["available"] = True
            row["is_current"] = True
            out.append(row)
        for f in others:
            mid = int(f.get("id") or 0)
            entry = by_id.get(mid)
            if not entry or not entry.sources:
                continue
            row = dict(f)
            row["available"] = True
            row["sources"] = [
                {
                    "name": s.name,
                    "link": s.link,
                    "color": s.color or "",
                    "video_src": s.video_src or "",
                }
                for s in entry.sources
            ]
            if entry.title:
                row["source_title"] = entry.title
            if entry.image:
                row["image"] = entry.image or row.get("image") or ""
            out.append(row)
        return out

    @staticmethod
    def _index_resolved_by_anilist_id(
        entries: list[AnimeEntry],
    ) -> dict[int, AnimeEntry]:
        by_id: dict[int, AnimeEntry] = {}
        for e in entries:
            mid = int(getattr(e, "anilist_id", 0) or 0)
            if mid > 0:
                by_id[mid] = e
        return by_id

    def resolve_catalog_items(
        self,
        items: list[dict],
        *,
        timeout: float = 14.0,
    ) -> list[AnimeEntry]:
        """
        Cruza candidatos AniList com fontes ativas.

        Plano (sem futures aninhados):
        - cache hit imediato
        - 1 query por título × todas as fontes em paralelo no pool de gênero
        - agrega matches e devolve na ordem do catálogo
        """
        if not items:
            return []
        sources = [e for e in self._get_enabled_list() if e.has_search]
        if not sources:
            return []
        sources_sig = ",".join(sorted(e.identifier for e in sources))

        media_list: list[AniListSearchMedia] = []
        meta_by_id: dict[int, dict] = {}
        for raw in items:
            titles = [t for t in (raw.get("titles") or []) if t]
            title = (raw.get("title") or "").strip()
            if title and title not in titles:
                titles = [title, *titles]
            if not titles:
                continue
            mid = int(raw.get("id") or 0)
            media_list.append(
                AniListSearchMedia(
                    id=mid,
                    title_romaji=titles[0],
                    title_english=titles[1] if len(titles) > 1 else "",
                    title_native=titles[2] if len(titles) > 2 else "",
                    image=(raw.get("image") or "").strip(),
                    score=raw.get("score"),
                    season=(raw.get("season") or "") or "",
                    year=raw.get("year"),
                    format=(raw.get("format") or "") or "",
                    status=(raw.get("status") or "") or "",
                    episodes=raw.get("episodes"),
                    description=(raw.get("description") or "") or "",
                    studios=list(raw.get("studios") or []),
                    genres=list(raw.get("genres") or []),
                    banner=(raw.get("banner") or "") or "",
                )
            )
            # guarda meta do catálogo para serializar no card final
            meta_by_id[mid] = {
                k: raw[k]
                for k in (
                    "season_line",
                    "season_label",
                    "year",
                    "format_label",
                    "status_label",
                    "status",
                    "score",
                    "episodes",
                    "studios",
                    "genres_label",
                    "banner",
                    "description",
                    "format",
                    "season",
                )
                if k in raw and raw[k] not in (None, "", [])
            }
            if raw.get("score") is not None:
                meta_by_id[mid]["score"] = raw.get("score")
        if not media_list:
            return []

        # cache → resultados parciais; só busca o que falta
        now = time.monotonic()
        by_id: dict[int, AnimeEntry] = {}
        to_fetch: list[AniListSearchMedia] = []
        for media in media_list:
            ck = self._resolve_cache_key(media, sources_sig)
            cached = _resolve_cache.get(ck)
            if cached and cached[0] > now:
                if cached[1] is not None:
                    entry = cached[1]
                    # reanexa meta/id caso o cache seja de versão antiga
                    if not getattr(entry, "anilist_id", None):
                        entry.anilist_id = media.id
                    if not getattr(entry, "meta", None) and media.id in meta_by_id:
                        entry.meta = meta_by_id[media.id]
                    by_id[media.id] = entry
                continue
            to_fetch.append(media)

        if to_fetch:
            pool = _get_genre_executor()
            # (future) -> (media, source_entry)
            pending: dict = {}
            for media in to_fetch:
                query = media.search_titles()[0]
                for entry in sources:
                    fut = pool.submit(self._search_one_source, entry, query)
                    pending[fut] = (media, entry)

            # coleta: media_id -> parcial
            acc: dict[int, dict] = {
                m.id: {
                    "sources": [],  # list[SourceInfo]
                    "title": m.primary_title,
                    "image": m.image,
                    "rating": (
                        f"{m.score / 10:.1f}" if m.score is not None else ""
                    ),
                    "titles": m.search_titles(),
                    "keys": {self._normalize(t) for t in m.search_titles() if t},
                    "best_sim": 0.0,
                }
                for m in to_fetch
            }

            deadline = time.monotonic() + max(4.0, timeout)
            while pending and time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                done, _ = wait(
                    list(pending.keys()),
                    timeout=remaining,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    break
                for fut in done:
                    media, _entry = pending.pop(fut)
                    bucket = acc[media.id]
                    try:
                        hits = fut.result()
                    except Exception:
                        continue
                    # melhor hit por fonte × variante de áudio (mantém dublado + legendado)
                    best_by_variant: dict[str, tuple[float, Anime, SourceInfo]] = {}
                    for anime, src in hits:
                        sim = self._best_title_score(
                            anime.title, bucket["keys"], bucket["titles"]
                        )
                        if sim < 0.62:
                            continue
                        vkey = f"{src.name}|{src.variant or detect_audio_variant(anime.title, anime.link)}"
                        prev = best_by_variant.get(vkey)
                        if prev is None or sim > prev[0]:
                            best_by_variant[vkey] = (sim, anime, src)
                    if not best_by_variant:
                        continue
                    for best_sim, best_anime, best_src in best_by_variant.values():
                        variant = best_src.variant or detect_audio_variant(
                            best_anime.title, best_src.link
                        )
                        best_src.variant = variant
                        best_src.title = best_anime.title or best_src.title
                        if any(
                            s.name == best_src.name
                            and (s.variant or "original") == variant
                            for s in bucket["sources"]
                        ):
                            continue
                        if any(
                            s.link and best_src.link and s.link == best_src.link
                            for s in bucket["sources"]
                        ):
                            continue
                        bucket["sources"].append(best_src)
                        # meta de exibição: título limpo (sem “Dublado”)
                        if best_sim >= bucket["best_sim"]:
                            bucket["best_sim"] = best_sim
                            clean = prefer_display_title(
                                bucket.get("title") or "", best_anime.title or ""
                            )
                            if clean:
                                bucket["title"] = clean
                            if best_anime.image:
                                bucket["image"] = best_anime.image
                            if best_anime.rating and str(best_anime.rating).strip():
                                bucket["rating"] = str(best_anime.rating).strip()

            for fut in list(pending.keys()):
                fut.cancel()

            for media in to_fetch:
                bucket = acc[media.id]
                result: AnimeEntry | None = None
                if bucket["sources"]:
                    result = AnimeEntry(
                        title=bucket["title"],
                        rating=bucket["rating"],
                        image=bucket["image"] or media.image,
                        sources=list(bucket["sources"]),
                        anilist_id=media.id or None,
                        meta=meta_by_id.get(media.id) or {},
                    )
                    by_id[media.id] = result
                ck = self._resolve_cache_key(media, sources_sig)
                _resolve_cache[ck] = (
                    time.monotonic() + _RESOLVE_CACHE_TTL,
                    result,
                )

            if len(_resolve_cache) > 800:
                self._prune_resolve_cache()

        out: list[AnimeEntry] = []
        for media in media_list:
            if media.id in by_id:
                out.append(by_id[media.id])
        return out

    def browse_by_genre(
        self,
        genre: str,
        *,
        page: int = 1,
        per_page: int = 12,
        max_candidates: int = 16,
    ) -> dict:
        """
        Compat: catálogo + resolve num request.
        Preferir catalog_by_genre + resolve_catalog_items na UI.
        """
        catalog = self.catalog_by_genre(
            genre, page=page, per_page=max(max_candidates, per_page)
        )
        if catalog.get("error") and not catalog.get("items"):
            return {
                "genre": genre,
                "label": catalog.get("label") or genre,
                "page": page,
                "per_page": per_page,
                "has_next": False,
                "items": [],
                "error": catalog.get("error"),
            }

        candidates = (catalog.get("items") or [])[:max_candidates]
        found = self.resolve_catalog_items(candidates)[:per_page]
        return {
            "genre": catalog.get("genre") or genre,
            "label": catalog.get("label") or genre,
            "page": catalog.get("page") or page,
            "per_page": per_page,
            "has_next": bool(catalog.get("has_next")),
            "anilist_total": catalog.get("anilist_total"),
            "candidates_checked": len(candidates),
            "items": found,
        }

    def _resolve_cache_key(self, media: AniListSearchMedia, sources_sig: str) -> str:
        titles = "|".join(media.search_titles()[:2])
        return f"{sources_sig}::{self._normalize(titles)}"

    @staticmethod
    def _prune_resolve_cache() -> None:
        now = time.monotonic()
        expired = [k for k, (exp, _) in _resolve_cache.items() if exp <= now]
        for k in expired:
            _resolve_cache.pop(k, None)
        if len(_resolve_cache) > 800:
            oldest = sorted(_resolve_cache.items(), key=lambda kv: kv[1][0])[:200]
            for k, _ in oldest:
                _resolve_cache.pop(k, None)

    def _search_one_source(
        self, entry: SourceEntry, query: str
    ) -> list[tuple[Anime, SourceInfo]]:
        """Uma fonte × uma query → hits (Anime + SourceInfo)."""
        try:
            reader = self._sd.get_reader(entry.identifier)
            if not reader:
                return []
            animes = reader.search_by(query) or []
        except Exception as e:
            logger.debug("search %s @ %s: %s", query, entry.name, e)
            return []
        out: list[tuple[Anime, SourceInfo]] = []
        for anime in animes:
            out.append(
                (
                    anime,
                    SourceInfo(
                        name=entry.name,
                        video_src="",
                        link=anime.link,
                        color=entry.color,
                        variant=detect_audio_variant(anime.title, anime.link),
                        title=anime.title or "",
                    ),
                )
            )
        return out

    @classmethod
    def _anime_key_from_title(cls, title: str) -> str:
        return cls._catalog_key(title)

    @classmethod
    def _titles_match(
        cls,
        source_title: str,
        anilist_keys: set[str],
        anilist_titles: list[str],
    ) -> bool:
        return cls._best_title_score(source_title, anilist_keys, anilist_titles) >= 0.62

    @classmethod
    def _best_title_score(
        cls,
        source_title: str,
        anilist_keys: set[str],
        anilist_titles: list[str],
    ) -> float:
        """
        Score 0..1 do match fonte × títulos AniList.
        Prefere igualdade / prefixo (sazonal, dublado) a contenção frouxa.
        """
        sk = cls._normalize(source_title)
        if not sk:
            return 0.0
        # remove sufixos comuns de fontes BR
        sk_clean = re.sub(
            r"\b(dublado|legendado|audiodescrito|ova|ona|movie|filme|special|especiais?)\b",
            " ",
            sk,
        )
        sk_clean = re.sub(r"\s+", " ", sk_clean).strip()

        best = 0.0
        for ak in anilist_keys:
            if not ak:
                continue
            if sk == ak or sk_clean == ak:
                return 1.0
            # "Title 2", "Title (Dublado)", "Title season 2"
            if sk_clean.startswith(ak + " ") or sk.startswith(ak + " "):
                best = max(best, 0.92)
                continue
            if sk_clean.startswith(ak) and len(sk_clean) - len(ak) <= 4:
                best = max(best, 0.88)
                continue
            # fonte mais curta só se for praticamente o título
            if ak.startswith(sk_clean) and len(sk_clean) >= 10:
                ratio = len(sk_clean) / max(len(ak), 1)
                if ratio >= 0.75:
                    best = max(best, 0.8 * ratio)
            # similaridade de tokens (sem aceitar superconjunto frouxo)
            sim = cls._title_similarity(sk_clean, ak)
            # penaliza se a fonte tem muitas palavras a mais (spin-off)
            extra = max(0, len(sk_clean.split()) - len(ak.split()))
            if extra >= 2:
                sim *= 0.55
            elif extra == 1:
                sim *= 0.85
            best = max(best, sim)

        # também tenta títulos crus
        for t in anilist_titles:
            best = max(best, cls._title_similarity(sk_clean, cls._normalize(t)))
        return best

    @classmethod
    def _title_similarity(cls, a: str, b: str) -> float:
        na = cls._normalize(a).split()
        nb = cls._normalize(b).split()
        if not na or not nb:
            return 0.0
        sa, sb = set(na), set(nb)
        inter = len(sa & sb)
        # Jaccard-ish com viés no menor conjunto
        return inter / max(len(sa), len(sb))

    def get_anime_details(self, link: str) -> AnimeDetail:
        sources = [e for e in self._get_enabled_list() if e.has_details]
        if not sources:
            return AnimeDetail(title="", rating="", link=link)

        # prefere a fonte dona do host do link (evita scraper errado “ganhar” a corrida)
        link_l = (link or "").lower()
        ordered = sorted(
            sources,
            key=lambda e: (
                0
                if e.base_url
                and e.base_url.replace("https://", "")
                .replace("http://", "")
                .split("/")[0]
                .lower()
                in link_l
                else 1,
                e.name,
            ),
        )

        def fetch(entry: SourceEntry) -> Anime | None:
            try:
                reader = self._sd.get_reader(entry.identifier)
                return reader.get_anime_details(link) if reader else None
            except Exception as e:
                logger.warning("Falha ao obter detalhes de %s: %s", entry.name, e)
                return None

        # tenta a fonte “dona” do link primeiro, em sync (rápido e correto)
        owner = ordered[0] if ordered else None
        if owner and owner.base_url and owner.base_url.split("//")[-1].split("/")[0].lower() in link_l:
            result = fetch(owner)
            if result and result.title:
                return self._anime_to_detail(result)

        futures = {_get_executor().submit(fetch, e): e for e in ordered}
        try:
            for future in as_completed(futures):
                result = future.result()
                if result and result.title:
                    for f in futures:
                        f.cancel()
                    return self._anime_to_detail(result)
        finally:
            for f in futures:
                f.cancel()
        return AnimeDetail(title="", rating="", link=link)

    @staticmethod
    def _anime_to_detail(anime: Anime) -> AnimeDetail:
        seasons: list[SeasonDetail] | None = None
        if anime.seasons:
            seasons = [
                SeasonDetail(
                    number=s.number,
                    episodes=[_episode_to_item(ep) for ep in s.episodes],
                )
                for s in anime.seasons
            ]
        return AnimeDetail(
            title=anime.title,
            rating=anime.rating,
            link=anime.link,
            image=anime.image,
            description=anime.description,
            seasons=seasons,
        )

    def get_play_context_from_source(
        self, episode_link: str, source_name: str
    ) -> PlayContext | None:
        """Resolve playback apenas com o reader da fonte indicada (por nome)."""
        if not episode_link or not source_name:
            return None
        for e in self._get_enabled_list():
            if e.name != source_name:
                continue
            try:
                reader = self._sd.get_reader(e.identifier)
                if not reader:
                    return None
                ctx = reader.get_play_context(episode_link)
                return ctx if ctx and ctx.url else None
            except Exception as ex:
                logger.warning(
                    "Falha ao obter play_context de %s: %s", source_name, ex
                )
                return None
        return None

    def get_play_context(
        self, episode_link: str, preferred_source: str | None = None
    ) -> PlayContext | None:
        """Resolve playback (URL + headers) pela fonte — sem heurística no player."""
        sources = self._get_enabled_list()
        if not sources:
            return None

        def fetch(entry: SourceEntry) -> PlayContext | None:
            try:
                reader = self._sd.get_reader(entry.identifier)
                if not reader:
                    return None
                ctx = reader.get_play_context(episode_link)
                return ctx if ctx and ctx.url else None
            except Exception as e:
                logger.warning("Falha ao obter play_context de %s: %s", entry.name, e)
                return None

        if preferred_source:
            # só essa fonte — evita reader A em link de B retornando page() “válida”
            only = self.get_play_context_from_source(episode_link, preferred_source)
            if only:
                return only

        futures = {_get_executor().submit(fetch, e): e for e in sources}
        for future in as_completed(futures):
            result = future.result()
            if result:
                return result
        return None

    def get_video_src(self, episode_link: str, preferred_source: str | None = None) -> str:
        """Compat: só a URL. Prefira :meth:`get_play_context`."""
        ctx = self.get_play_context(episode_link, preferred_source)
        return ctx.url if ctx else ""
