"""Serviço de anime — orquestra fontes, catálogo e playback."""

from __future__ import annotations

import logging
from concurrent.futures import as_completed

from app.application._executor import get_executor
from app.application.catalog_resolver import CatalogResolver
from app.application.catalog_service import CatalogService
from app.application.dtos import (
    AnimeDetail,
    AnimeEntry,
    EpisodeEntry,
    EpisodeItem,
    SeasonDetail,
    SourceEntry,
)
from app.application.episode_aggregator import EpisodeAggregator
from app.application.interfaces import ISourceDiscovery
from app.application.interfaces.ianilist_client import IAniListClient
from app.domain import Anime, Episode, PlayContext

logger = logging.getLogger(__name__)


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
        anilist: IAniListClient | None = None,
        genre_labels: dict | None = None,
    ):
        self._sd = source_discovery
        self._enabled: set[str] = set()
        self._anilist = anilist
        self._genre_labels = genre_labels or {}
        self._aggregator = EpisodeAggregator(source_discovery, self._get_enabled_list)
        self._resolver = CatalogResolver(source_discovery, self._get_enabled_list)
        self._catalog = CatalogService(
            external_api=anilist,
            genre_labels=self._genre_labels,
            sd=source_discovery,
            get_enabled_list=self._get_enabled_list,
            catalog_resolver=self._resolver,
        )

    # ── Source management ──────────────────────────────────────────────────

    def init_sources(self):
        self._sd.discover()
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
        sd = self._sd
        if hasattr(sd, "check_one") and identifier:
            entry = sd.check_one(identifier)
            return [entry] if entry else []
        if hasattr(sd, "check_all"):
            return list(sd.check_all(mark_checking=True))
        return self.get_all_source_entries()

    def _get_enabled_list(self) -> list[SourceEntry]:
        return [
            e for e in self._sd.get_all_entries() if e.identifier in self._enabled and e.available
        ]

    # ── Episodes / Search ───────────────────────────────────────────────────

    def get_last_episodes(self) -> list[EpisodeEntry]:
        return self._aggregator.get_last_episodes()

    def search_by(self, name: str) -> list[AnimeEntry]:
        return self._aggregator.search_by(name)

    # ── AniList catalog ─────────────────────────────────────────────────────

    def get_genres(self) -> list[dict[str, str]]:
        return self._catalog.get_genres()

    def catalog_by_genre(self, genre: str, *, page: int = 1, per_page: int = 24) -> dict:
        return self._catalog.catalog_by_genre(genre, page=page, per_page=per_page)

    def get_anilist_meta(self, *, title: str = "", anilist_id: int | None = None) -> dict | None:
        return self._catalog.get_meta(title=title, external_id=anilist_id)

    def get_release_calendar(self, *, days: int = 7, check_sources: bool = False) -> dict:
        return self._catalog.get_release_calendar(days=days, check_sources=check_sources)

    def resolve_catalog_items(
        self, items: list[dict], *, timeout: float = 14.0
    ) -> list[AnimeEntry]:
        return self._resolver.resolve(items, timeout=timeout)

    def browse_by_genre(
        self, genre: str, *, page: int = 1, per_page: int = 12, max_candidates: int = 16
    ) -> dict:
        return self._catalog.browse_by_genre(
            genre, page=page, per_page=per_page, max_candidates=max_candidates
        )

    # ── Anime details ───────────────────────────────────────────────────────

    def get_anime_details(self, link: str) -> AnimeDetail:
        sources = [e for e in self._get_enabled_list() if e.has_details]
        if not sources:
            return AnimeDetail(title="", rating="", link=link)

        link_l = (link or "").lower()
        ordered = sorted(
            sources,
            key=lambda e: (
                0
                if e.base_url
                and e.base_url.replace("https://", "").replace("http://", "").split("/")[0].lower()
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

        owner = ordered[0] if ordered else None
        if (
            owner
            and owner.base_url
            and owner.base_url.split("//")[-1].split("/")[0].lower() in link_l
        ):
            result = fetch(owner)
            if result and result.title:
                return self._anime_to_detail(result)

        futures = {get_executor().submit(fetch, e): e for e in ordered}
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
                SeasonDetail(number=s.number, episodes=[_episode_to_item(ep) for ep in s.episodes])
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

    # ── Playback ────────────────────────────────────────────────────────────

    def get_play_context_from_source(
        self, episode_link: str, source_name: str
    ) -> PlayContext | None:
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
                logger.warning("Falha ao obter play_context de %s: %s", source_name, ex)
                return None
        return None

    def get_play_context(
        self, episode_link: str, preferred_source: str | None = None
    ) -> PlayContext | None:
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
            only = self.get_play_context_from_source(episode_link, preferred_source)
            if only:
                return only

        futures = {get_executor().submit(fetch, e): e for e in sources}
        for future in as_completed(futures):
            result = future.result()
            if result:
                return result
        return None

    def get_video_src(self, episode_link: str, preferred_source: str | None = None) -> str:
        ctx = self.get_play_context(episode_link, preferred_source)
        return ctx.url if ctx else ""
