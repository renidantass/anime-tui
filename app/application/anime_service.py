from __future__ import annotations

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.application.dtos import AnimeDetail, AnimeEntry, EpisodeEntry, EpisodeItem, SeasonDetail, SourceEntry, SourceInfo
from app.application.interfaces import ISourceDiscovery
from app.domain import Anime, Episode, PlayContext
from app.infrastructure.sources._utils import (
    extract_episode_number,
    is_unknown_episode_number,
)

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=8)
    return _executor


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
    def __init__(self, source_discovery: ISourceDiscovery):
        self._sd = source_discovery
        self._enabled: set[str] = set()

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

    @staticmethod
    def _ep_key(ep: Episode) -> str:
        base = AnimeService._normalize(ep.title)
        if ep.number and ep.number not in ('0', '?', ''):
            return f"{base}|{ep.number}"
        return base

    @staticmethod
    def _anime_key(a: Anime) -> str:
        return AnimeService._normalize(a.title)

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
                key = self._ep_key(ep)
                number = ep.number if not is_unknown_episode_number(ep.number) else ""
                if not number:
                    number = extract_episode_number(ep.title, ep.link, default="")
                if key not in entries:
                    entries[key] = EpisodeEntry(
                        title=ep.title,
                        image=ep.image,
                        date=ep.date,
                        number=number,
                    )
                else:
                    # preenche número se a primeira fonte não tinha
                    if is_unknown_episode_number(entries[key].number) and number:
                        entries[key].number = number
                if not any(s.name == name for s in entries[key].sources):
                    entries[key].sources.append(
                        SourceInfo(name=name, video_src=ep.video_src, link=ep.link, color=entry.color)
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
                if not any(s.name == source_name for s in entries[key].sources):
                    entries[key].sources.append(
                        SourceInfo(name=source_name, video_src="", link=anime.link, color=entry.color)
                    )

        return list(entries.values())

    def get_anime_details(self, link: str) -> AnimeDetail:
        sources = [e for e in self._get_enabled_list() if e.has_details]
        if not sources:
            return AnimeDetail(title="", rating="", link=link)

        def fetch(entry: SourceEntry) -> Anime | None:
            try:
                reader = self._sd.get_reader(entry.identifier)
                return reader.get_anime_details(link) if reader else None
            except Exception as e:
                logger.warning("Falha ao obter detalhes de %s: %s", entry.name, e)
                return None

        futures = {_get_executor().submit(fetch, e): e for e in sources}
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
