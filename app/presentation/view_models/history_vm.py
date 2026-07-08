from __future__ import annotations

from dataclasses import dataclass

from app.domain.watch_history import WatchHistoryEntry


@dataclass(slots=True)
class HistoryVM:
    anime_title: str
    episode_title: str
    episode_number: str
    episode_link: str
    source_name: str
    anime_image: str
    watched_at: str
    season_number: int
    source_color: str = ''

    @classmethod
    def from_entity(cls, entry: WatchHistoryEntry) -> HistoryVM:
        return cls(
            anime_title=entry.anime_title,
            episode_title=entry.episode_title,
            episode_number=entry.episode_number,
            episode_link=entry.episode_link,
            source_name=entry.source_name,
            anime_image=entry.anime_image,
            watched_at=entry.watched_at,
            season_number=entry.season_number,
            source_color=entry.source_color,
        )
