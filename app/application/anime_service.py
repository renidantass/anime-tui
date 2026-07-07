from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from app.application.dtos import AnimeDetail, EpisodeItem, SeasonDetail
from app.application.interfaces import ISourceDiscovery
from app.application.models import EpisodeEntry, AnimeEntry, SourceInfo, SourceEntry
from app.domain import Anime, Episode


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

    def init_sources(self):
        self._sd.discover()
        self._reset_enabled()

    def _reset_enabled(self):
        self._enabled: set[str] = set()
        for e in self._sd.get_enabled_entries():
            self._enabled.add(e.source.identifier)

    def set_enabled(self, identifier: str, enabled: bool):
        if enabled:
            self._enabled.add(identifier)
        else:
            self._enabled.discard(identifier)

    def is_enabled(self, identifier: str) -> bool:
        return identifier in self._enabled

    def get_enabled_source_names(self) -> list[str]:
        return [entry.source.name for entry in self._sd.get_enabled_entries()]

    def get_all_source_entries(self) -> list[SourceEntry]:
        return self._sd.get_all_entries()

    def is_source_available(self, identifier: str) -> bool:
        return self._sd.is_available(identifier)

    def _get_enabled_list(self) -> list[SourceEntry]:
        return [e for e in self._sd.get_enabled_entries() if e.source.identifier in self._enabled]

    @staticmethod
    def _ep_key(ep: Episode) -> str:
        return ep.title.lower().strip()

    @staticmethod
    def _anime_key(a: Anime) -> str:
        return a.title.lower().strip()

    def get_last_episodes(self) -> list[EpisodeEntry]:
        entries: dict[str, EpisodeEntry] = {}
        sources = self._get_enabled_list()
        if not sources:
            return []

        def fetch(entry: SourceEntry) -> tuple[str, list[Episode]]:
            return entry.source.name, entry.source.get_last_episodes()

        with ThreadPoolExecutor(max_workers=len(sources)) as ex:
            futures = {ex.submit(fetch, e): e for e in sources}
            for future in as_completed(futures):
                entry = futures[future]
                name = entry.source.name
                try:
                    _, episodes = future.result()
                except Exception:
                    continue
                for ep in episodes:
                    key = self._ep_key(ep)
                    if key not in entries:
                        entries[key] = EpisodeEntry(
                            title=ep.title,
                            image=ep.image,
                            date=ep.date,
                        )
                    if not any(s.name == name for s in entries[key].sources):
                        entries[key].sources.append(
                            SourceInfo(name=name, video_src=ep.video_src, link=ep.link, color=entry.source.color)
                        )

        return list(entries.values())

    def search_by(self, name: str) -> list[AnimeEntry]:
        entries: dict[str, AnimeEntry] = {}
        sources = [e for e in self._get_enabled_list() if e.source.has_search]
        if not sources:
            return []

        def fetch(entry: SourceEntry) -> tuple[str, list[Anime]]:
            return entry.source.name, entry.source.search_by(name)

        with ThreadPoolExecutor(max_workers=len(sources)) as ex:
            futures = {ex.submit(fetch, e): e for e in sources}
            for future in as_completed(futures):
                entry = futures[future]
                source_name = entry.source.name
                try:
                    _, animes = future.result()
                except Exception:
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
                            SourceInfo(name=source_name, video_src="", link=anime.link, color=entry.source.color)
                        )

        return list(entries.values())

    def get_anime_details(self, link: str) -> AnimeDetail:
        sources = [e for e in self._get_enabled_list() if e.source.has_details]
        if not sources:
            return AnimeDetail(title="", rating="", link=link)

        def fetch(entry: SourceEntry) -> Anime | None:
            try:
                return entry.source.get_anime_details(link)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=len(sources)) as ex:
            futures = [ex.submit(fetch, e) for e in sources]
            for future in as_completed(futures):
                result = future.result()
                if result and result.title:
                    return self._anime_to_detail(result)
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

    def get_video_src(self, episode_link: str, preferred_source: str | None = None) -> str:
        sources = self._get_enabled_list()
        if not sources:
            return ""

        def fetch(entry: SourceEntry) -> str:
            try:
                return entry.source.get_video_src(episode_link)
            except Exception:
                return ""

        if preferred_source:
            for e in sources:
                if e.source.name == preferred_source:
                    result = fetch(e)
                    if result:
                        return result

        with ThreadPoolExecutor(max_workers=len(sources)) as ex:
            futures = {ex.submit(fetch, e): e for e in sources}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    return result
        return ""
