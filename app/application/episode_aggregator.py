"""Agregação paralela de episódios e busca entre múltiplas fontes."""

from __future__ import annotations

import logging
from concurrent.futures import as_completed

from app.application._executor import get_executor
from app.application.dtos import AnimeEntry, EpisodeEntry, SourceEntry, SourceInfo
from app.application.interfaces import ISourceDiscovery
from app.application.title_matcher import anime_key, append_source, ep_key, titles_are_similar
from app.application.title_utils import (
    extract_episode_number,
    is_unknown_episode_number,
    prefer_display_title,
)
from app.domain import Anime, Episode

logger = logging.getLogger(__name__)


class EpisodeAggregator:
    def __init__(self, source_discovery: ISourceDiscovery, get_enabled_list):
        self._sd = source_discovery
        self._get_enabled_list = get_enabled_list

    def get_last_episodes(self) -> list[EpisodeEntry]:
        entries: dict[str, EpisodeEntry] = {}
        sources = self._get_enabled_list()
        if not sources:
            return []

        def fetch(entry: SourceEntry) -> tuple[str, list[Episode]]:
            reader = self._sd.get_reader(entry.identifier)
            return entry.name, reader.get_last_episodes() if reader else []

        futures = {get_executor().submit(fetch, e): e for e in sources}
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
                key = ep_key(ep)
                if key not in entries:
                    entries[key] = EpisodeEntry(title=ep.title, image=ep.image, date=ep.date, number=number)
                else:
                    existing = entries[key]
                    if is_unknown_episode_number(existing.number) and number:
                        existing.number = number
                    existing.title = prefer_display_title(existing.title, ep.title)
                    if not existing.image and ep.image:
                        existing.image = ep.image
                    if not existing.date and ep.date:
                        existing.date = ep.date
                append_source(entries[key].sources, name=name, video_src=ep.video_src,
                              link=ep.link, color=entry.color, title=ep.title)

        # ── Fuzzy merge: group entries with similar anime title + same episode number ──
        if len(entries) > 1:
            items = list(entries.items())
            merged_keys: set[str] = set()
            result: dict[str, EpisodeEntry] = {}
            for i, (ka, ea) in enumerate(items):
                if ka in merged_keys:
                    continue
                merged_keys.add(ka)
                base_a = ka.rsplit("|", 1)[0]
                num_a = ka.rsplit("|", 1)[1] if "|" in ka else ""
                for j, (kb, eb) in enumerate(items):
                    if kb in merged_keys or j <= i:
                        continue
                    base_b = kb.rsplit("|", 1)[0]
                    num_b = kb.rsplit("|", 1)[1] if "|" in kb else ""
                    if num_a and num_b and num_a == num_b and titles_are_similar(base_a, base_b):
                        merged_keys.add(kb)
                        ea.title = prefer_display_title(ea.title, eb.title)
                        if not ea.image and eb.image:
                            ea.image = eb.image
                        if not ea.date and eb.date:
                            ea.date = eb.date
                        for src in eb.sources:
                            append_source(ea.sources, name=src.name, video_src=src.video_src,
                                          link=src.link, color=src.color, title=src.title)
                result[ka] = ea
            entries = result

        return list(entries.values())

    def search_by(self, name: str) -> list[AnimeEntry]:
        entries: dict[str, AnimeEntry] = {}
        sources = [e for e in self._get_enabled_list() if e.has_search]
        if not sources:
            return []

        def fetch(entry: SourceEntry) -> tuple[str, list[Anime]]:
            reader = self._sd.get_reader(entry.identifier)
            return entry.name, reader.search_by(name) if reader else []

        futures = {get_executor().submit(fetch, e): e for e in sources}
        for future in as_completed(futures):
            entry = futures[future]
            source_name = entry.name
            try:
                _, animes = future.result()
            except Exception as e:
                logger.warning("Falha ao buscar em %s: %s", source_name, e)
                continue
            for anime in animes:
                key = anime_key(anime)
                if key not in entries:
                    entries[key] = AnimeEntry(title=anime.title, rating=anime.rating, image=anime.image)
                else:
                    existing = entries[key]
                    existing.title = prefer_display_title(existing.title, anime.title)
                    if not existing.image and anime.image:
                        existing.image = anime.image
                    if not existing.rating and anime.rating:
                        existing.rating = anime.rating
                append_source(entries[key].sources, name=source_name, video_src="",
                              link=anime.link, color=entry.color, title=anime.title)
        return list(entries.values())
