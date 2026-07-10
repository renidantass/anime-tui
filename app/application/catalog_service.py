"""Catálogo — gêneros, meta, calendário de lançamentos."""

from __future__ import annotations

import logging
from concurrent.futures import as_completed

from app.application._executor import get_executor
from app.application.dtos import AnimeEntry
from app.application.interfaces.ianilist_client import IAniListClient
from app.application.interfaces import ISourceDiscovery
from app.application.title_utils import detect_audio_variant, extract_episode_number, is_unknown_episode_number, _clean_num

logger = logging.getLogger(__name__)


def index_by_anilist_id(entries: list[AnimeEntry]) -> dict[int, AnimeEntry]:
    by_id: dict[int, AnimeEntry] = {}
    for e in entries:
        mid = int(getattr(e, "anilist_id", 0) or 0)
        if mid > 0:
            by_id[mid] = e
    return by_id


def normalize_ep_number(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s or is_unknown_episode_number(s):
        return ""
    cleaned = _clean_num(s)
    return cleaned or ""


class CatalogService:
    def __init__(self, external_api: IAniListClient, genre_labels: dict, sd: ISourceDiscovery,
                 get_enabled_list, catalog_resolver):
        self._api = external_api
        self._genre_labels = genre_labels
        self._sd = sd
        self._get_enabled_list = get_enabled_list
        self._catalog_resolver = catalog_resolver

    def get_genres(self) -> list[dict[str, str]]:
        try:
            names = self._api.get_genres()
        except Exception as e:
            logger.warning("Falha ao listar gêneros: %s", e)
            return []
        return [{"id": name, "name": name, "label": self._genre_labels.get(name, name)} for name in names]

    def catalog_by_genre(self, genre: str, *, page: int = 1, per_page: int = 24) -> dict:
        genre = (genre or "").strip()
        empty = {"genre": genre, "label": self._genre_labels.get(genre, genre) if genre else "",
                 "page": page, "per_page": per_page, "has_next": False, "items": []}
        if not genre:
            return empty
        try:
            al_page = self._api.get_anime_by_genre(genre, page=page, per_page=min(50, max(1, per_page)))
        except Exception as e:
            logger.warning("Falha catalog genre=%s: %s", genre, e)
            empty["error"] = str(e)
            return empty
        items = []
        for m in al_page.items:
            d = m.to_dict(include_relations=False)
            items.append({
                "id": d["id"], "title": d["title"], "titles": d["titles"], "image": d["image"],
                "banner": d.get("banner") or "", "score": d.get("score"), "year": d.get("year"),
                "season": d.get("season") or "", "season_label": d.get("season_label") or "",
                "season_line": d.get("season_line") or "", "genres": d.get("genres") or [],
                "genres_label": d.get("genres_label") or [], "format": d.get("format") or "",
                "format_label": d.get("format_label") or "", "status": d.get("status") or "",
                "status_label": d.get("status_label") or "", "episodes": d.get("episodes"),
                "studios": d.get("studios") or [], "description": (d.get("description") or "")[:280],
            })
        return {"genre": genre, "label": self._genre_labels.get(genre, genre),
                "page": al_page.page, "per_page": al_page.per_page,
                "has_next": al_page.has_next, "anilist_total": al_page.total, "items": items}

    def get_meta(self, *, title: str = "", external_id: int | None = None) -> dict | None:
        try:
            media = self._api.lookup(title=title, media_id=external_id)
        except Exception as e:
            logger.warning("Meta falhou: %s", e)
            return None
        if not media:
            return None
        data = media.to_dict(include_relations=True)
        data["franchise"] = self._filter_franchise(data.get("franchise") or [])
        data["relations"] = [r for r in (data.get("relations") or [])
                              if any(f.get("id") == r.get("id") and f.get("available")
                                     for f in data["franchise"])
                              or r.get("relation_type") == "CURRENT"]
        return data

    def get_release_calendar(self, *, days: int = 7, check_sources: bool = False) -> dict:
        try:
            entries = self._api.get_airing_schedule(days=days)
        except Exception as e:
            logger.warning("Calendário falhou: %s", e)
            return {"days": days, "check_sources": check_sources, "total": 0,
                    "available_total": 0, "items": [], "error": str(e)}
        flat = [e.to_dict() for e in entries]
        if check_sources:
            annotated = self._annotate_airing(flat)
            return {"days": days, "check_sources": True, "total": len(annotated),
                    "available_total": sum(1 for it in annotated if it.get("available")), "items": annotated}
        items = []
        for it in flat:
            row = dict(it)
            row["available"] = None
            row["sources"] = []
            items.append(row)
        return {"days": days, "check_sources": False, "total": len(items),
                "available_total": 0, "items": items}

    def _annotate_airing(self, items: list[dict]) -> list[dict]:
        if not items:
            return []
        candidates: dict[int, dict] = {}
        for it in items:
            mid = int(it.get("id") or 0)
            if mid <= 0 or mid in candidates:
                continue
            titles = list(it.get("titles") or [])
            title = (it.get("title") or "").strip()
            if title and title not in titles:
                titles = [title, *titles]
            candidates[mid] = {"id": mid, "title": title, "titles": titles,
                               "image": it.get("image") or "", "score": it.get("score")}
        by_id: dict[int, AnimeEntry] = {}
        if candidates:
            found = self._catalog_resolver.resolve(list(candidates.values()), timeout=18.0)
            by_id = index_by_anilist_id(found)

        detail_jobs: dict[str, tuple[str, str]] = {}
        for entry in by_id.values():
            for src in entry.sources:
                if not src.link or not src.name:
                    continue
                detail_jobs[f"{src.name}|{src.link}"] = (src.name, src.link)
        ep_maps: dict[str, dict[str, dict]] = {}
        if detail_jobs:
            pool = get_executor()
            futures = {pool.submit(_episode_map_for_source_link, self._sd, self._get_enabled_list, name, link): key
                       for key, (name, link) in detail_jobs.items()}
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    ep_maps[key] = fut.result() or {}
                except Exception as e:
                    logger.debug("mapa de eps falhou %s: %s", key, e)
                    ep_maps[key] = {}

        out: list[dict] = []
        for it in items:
            mid = int(it.get("id") or 0)
            entry = by_id.get(mid)
            row = dict(it)
            ep_target = normalize_ep_number(it.get("episode"))
            if not entry or not entry.sources:
                row["available"] = False; row["sources"] = []; out.append(row); continue
            if entry.title:
                row["source_title"] = entry.title
            if entry.image:
                row["source_image"] = entry.image
            if not ep_target:
                row["available"] = False; row["sources"] = []; row["unavailable_reason"] = "episode_unknown"
                out.append(row); continue
            matching: list[dict] = []
            for src in entry.sources:
                key = f"{src.name}|{src.link}"
                ep_map = ep_maps.get(key) or {}
                hit = ep_map.get(ep_target)
                if not hit:
                    continue
                matching.append({"name": src.name, "link": src.link, "episode_link": hit.get("link") or "",
                                 "color": src.color or "", "video_src": hit.get("video_src") or "",
                                 "variant": getattr(src, "variant", "") or detect_audio_variant(
                                     getattr(src, "title", "") or "", src.link or ""),
                                 "title": getattr(src, "title", "") or ""})
            if matching:
                row["available"] = True; row["sources"] = matching
            else:
                row["available"] = False; row["sources"] = []; row["unavailable_reason"] = "anime_only" if entry.sources else "missing"
            out.append(row)
        return out

    def _filter_franchise(self, franchise: list[dict]) -> list[dict]:
        if not franchise:
            return []
        current = [f for f in franchise if f.get("is_current") or f.get("relation_type") == "CURRENT"]
        others = [f for f in franchise if not (f.get("is_current") or f.get("relation_type") == "CURRENT")]
        candidates = []
        for f in others:
            mid = int(f.get("id") or 0)
            title = (f.get("title") or "").strip()
            if mid <= 0 or not title:
                continue
            candidates.append({"id": mid, "title": title, "titles": [title],
                               "image": f.get("image") or "", "score": f.get("score")})
        by_id: dict[int, AnimeEntry] = {}
        if candidates:
            found = self._catalog_resolver.resolve(candidates, timeout=16.0)
            by_id = index_by_anilist_id(found)
        out: list[dict] = []
        for f in current:
            row = dict(f); row["available"] = True; row["is_current"] = True; out.append(row)
        for f in others:
            mid = int(f.get("id") or 0)
            entry = by_id.get(mid)
            if not entry or not entry.sources:
                continue
            row = dict(f); row["available"] = True
            row["sources"] = [{"name": s.name, "link": s.link, "color": s.color or "", "video_src": s.video_src or ""}
                              for s in entry.sources]
            if entry.title:
                row["source_title"] = entry.title
            if entry.image:
                row["image"] = entry.image or row.get("image") or ""
            out.append(row)
        return out

    def browse_by_genre(self, genre: str, *, page: int = 1, per_page: int = 12,
                        max_candidates: int = 16) -> dict:
        catalog = self.catalog_by_genre(genre, page=page, per_page=max(max_candidates, per_page))
        if catalog.get("error") and not catalog.get("items"):
            return {"genre": genre, "label": catalog.get("label") or genre, "page": page,
                    "per_page": per_page, "has_next": False, "items": [], "error": catalog.get("error")}
        candidates = (catalog.get("items") or [])[:max_candidates]
        found = self._catalog_resolver.resolve(candidates)[:per_page]
        return {"genre": catalog.get("genre") or genre, "label": catalog.get("label") or genre,
                "page": catalog.get("page") or page, "per_page": per_page,
                "has_next": bool(catalog.get("has_next")), "anilist_total": catalog.get("anilist_total"),
                "candidates_checked": len(candidates), "items": found}


def _episode_map_for_source_link(sd: ISourceDiscovery, get_enabled_list,
                                  source_name: str, anime_link: str) -> dict[str, dict]:
    if not anime_link or not source_name:
        return {}
    entry = next((e for e in get_enabled_list() if e.has_details and e.name == source_name), None)
    if not entry:
        return {}
    try:
        reader = sd.get_reader(entry.identifier)
        if not reader:
            return {}
        anime = reader.get_anime_details(anime_link)
    except Exception as e:
        logger.debug("detalhes %s @ %s: %s", source_name, anime_link[:60], e)
        return {}
    if not anime or not anime.seasons:
        return {}
    ep_map: dict[str, dict] = {}
    for season in anime.seasons:
        for ep in season.episodes or []:
            num = normalize_ep_number(ep.number)
            if not num:
                num = normalize_ep_number(extract_episode_number(ep.title, ep.link, default=""))
            if not num or num in ep_map:
                continue
            ep_map[num] = {"link": ep.link or "", "title": ep.title or "",
                           "video_src": ep.video_src or "", "image": ep.image or "", "number": num}
    return ep_map
