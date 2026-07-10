"""Resolução cruzada AniList × fontes com cache."""

from __future__ import annotations

import logging
import time
from concurrent.futures import wait
from concurrent.futures import as_completed

from app.application._cache import TTLCache
from app.application._executor import get_executor
from app.application.dtos import AnimeEntry, AniListSearchMedia, SourceEntry, SourceInfo
from app.application.interfaces import ISourceDiscovery
from app.application.title_matcher import best_title_score, normalize_text
from app.application.title_utils import detect_audio_variant, prefer_display_title
from app.domain import Anime

logger = logging.getLogger(__name__)
_RESOLVE_CACHE_TTL = 600.0


class CatalogResolver:
    def __init__(self, source_discovery: ISourceDiscovery, get_enabled_list):
        self._sd = source_discovery
        self._get_enabled_list = get_enabled_list
        self._cache = TTLCache(ttl=_RESOLVE_CACHE_TTL, max_size=800)

    def resolve(self, items: list[dict], *, timeout: float = 14.0) -> list[AnimeEntry]:
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
            media_list.append(AniListSearchMedia(
                id=mid, title_romaji=titles[0],
                title_english=titles[1] if len(titles) > 1 else "",
                title_native=titles[2] if len(titles) > 2 else "",
                image=(raw.get("image") or "").strip(), score=raw.get("score"),
                season=(raw.get("season") or ""), year=raw.get("year"),
                format=(raw.get("format") or ""), status=(raw.get("status") or ""),
                episodes=raw.get("episodes"), description=(raw.get("description") or ""),
                studios=list(raw.get("studios") or []), genres=list(raw.get("genres") or []),
                banner=(raw.get("banner") or ""),
            ))
            meta_by_id[mid] = {
                k: raw[k] for k in (
                    "season_line", "season_label", "year", "format_label", "status_label",
                    "status", "score", "episodes", "studios", "genres_label", "banner",
                    "description", "format", "season",
                ) if k in raw and raw[k] not in (None, "", [])
            }
            if raw.get("score") is not None:
                meta_by_id[mid]["score"] = raw.get("score")
        if not media_list:
            return []

        now = time.monotonic()
        by_id: dict[int, AnimeEntry] = {}
        to_fetch: list[AniListSearchMedia] = []
        for media in media_list:
            ck = _cache_key(media, sources_sig)
            cached = self._cache.get(ck)
            if cached is not None:
                entry = cached
                if not getattr(entry, "anilist_id", None):
                    entry.anilist_id = media.id
                if not getattr(entry, "meta", None) and media.id in meta_by_id:
                    entry.meta = meta_by_id[media.id]
                by_id[media.id] = entry
                continue
            to_fetch.append(media)

        if to_fetch:
            pool = get_executor()
            pending: dict = {}
            for media in to_fetch:
                query = media.search_titles()[0]
                for entry in sources:
                    fut = pool.submit(_search_one_source, self._sd, entry, query)
                    pending[fut] = (media, entry)

            acc: dict[int, dict] = {
                m.id: {
                    "sources": [], "title": m.primary_title, "image": m.image,
                    "rating": f"{m.score / 10:.1f}" if m.score is not None else "",
                    "titles": m.search_titles(),
                    "keys": {normalize_text(t) for t in m.search_titles() if t},
                    "best_sim": 0.0,
                }
                for m in to_fetch
            }

            deadline = time.monotonic() + max(4.0, timeout)
            while pending and time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                done, _ = wait(list(pending.keys()), timeout=remaining, return_when="FIRST_COMPLETED" if True else None)
                for future in as_completed(list(pending.keys()), timeout=remaining):
                    if future not in pending:
                        continue
                    try:
                        done.add(future)
                    except Exception:
                        break
                if not done:
                    break
                for fut in done:
                    media, _entry = pending.pop(fut)
                    bucket = acc[media.id]
                    try:
                        hits = fut.result()
                    except Exception:
                        continue
                    best_by_variant: dict[str, tuple[float, Anime, SourceInfo]] = {}
                    for anime, src in hits:
                        sim = best_title_score(anime.title, bucket["keys"], bucket["titles"])
                        if sim < 0.62:
                            continue
                        vkey = f"{src.name}|{src.variant or detect_audio_variant(anime.title, anime.link)}"
                        prev = best_by_variant.get(vkey)
                        if prev is None or sim > prev[0]:
                            best_by_variant[vkey] = (sim, anime, src)
                    if not best_by_variant:
                        continue
                    for best_sim, best_anime, best_src in best_by_variant.values():
                        variant = best_src.variant or detect_audio_variant(best_anime.title, best_src.link)
                        best_src.variant = variant
                        best_src.title = best_anime.title or best_src.title
                        if any(s.name == best_src.name and (s.variant or "original") == variant
                               for s in bucket["sources"]):
                            continue
                        if any(s.link and best_src.link and s.link == best_src.link
                               for s in bucket["sources"]):
                            continue
                        bucket["sources"].append(best_src)
                        if best_sim >= bucket["best_sim"]:
                            bucket["best_sim"] = best_sim
                            clean = prefer_display_title(bucket.get("title") or "", best_anime.title or "")
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
                        title=bucket["title"], rating=bucket["rating"],
                        image=bucket["image"] or media.image, sources=list(bucket["sources"]),
                        anilist_id=media.id or None, meta=meta_by_id.get(media.id) or {},
                    )
                    by_id[media.id] = result
                self._cache.set(_cache_key(media, sources_sig), result)

        out: list[AnimeEntry] = []
        for media in media_list:
            if media.id in by_id:
                out.append(by_id[media.id])
        return out


def _cache_key(media: AniListSearchMedia, sources_sig: str) -> str:
    titles = "|".join(media.search_titles()[:2])
    return f"{sources_sig}::{normalize_text(titles)}"


def _search_one_source(sd: ISourceDiscovery, entry: SourceEntry, query: str) -> list[tuple[Anime, SourceInfo]]:
    try:
        reader = sd.get_reader(entry.identifier)
        if not reader:
            return []
        animes = reader.search_by(query) or []
    except Exception as e:
        logger.debug("search %s @ %s: %s", query, entry.name, e)
        return []
    out: list[tuple[Anime, SourceInfo]] = []
    for anime in animes:
        out.append((anime, SourceInfo(
            name=entry.name, video_src="", link=anime.link, color=entry.color,
            variant=detect_audio_variant(anime.title, anime.link), title=anime.title or "",
        )))
    return out
