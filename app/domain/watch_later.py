from dataclasses import dataclass, field, fields
from datetime import UTC, datetime


@dataclass(slots=True)
class WatchLaterEntry:
    anime_title: str
    anime_image: str = ""
    source_name: str = ""
    source_link: str = ""
    source_color: str = ""
    added_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def from_dict(cls, data: dict) -> "WatchLaterEntry":
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        return cls(**kwargs)
