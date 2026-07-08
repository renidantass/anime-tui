from dataclasses import dataclass, field, fields
from datetime import datetime, timezone


@dataclass(slots=True)
class WatchHistoryEntry:
    anime_title: str
    episode_title: str
    episode_number: str
    episode_link: str
    source_name: str
    anime_image: str = ""
    watched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    season_number: int = 1
    source_color: str = ""
    # Progresso de reprodução (segundos)
    progress_seconds: float = 0.0
    duration_seconds: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "WatchHistoryEntry":
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)

    def progress_ratio(self) -> float:
        if self.duration_seconds and self.duration_seconds > 0:
            return min(1.0, max(0.0, self.progress_seconds / self.duration_seconds))
        return 0.0

    def is_finished(self, threshold: float = 0.92) -> bool:
        return self.progress_ratio() >= threshold
