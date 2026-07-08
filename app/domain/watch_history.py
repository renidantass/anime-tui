from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class WatchHistoryEntry:
    anime_title: str
    episode_title: str
    episode_number: str
    episode_link: str
    source_name: str
    anime_image: str = ''
    watched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    season_number: int = 1
    source_color: str = ''
