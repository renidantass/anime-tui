from __future__ import annotations

from dataclasses import dataclass


def _fmt_time(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


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
    source_color: str = ""
    progress_seconds: float = 0.0
    duration_seconds: float = 0.0

    @classmethod
    def from_entity(cls, entry) -> HistoryVM:
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
            progress_seconds=entry.progress_seconds,
            duration_seconds=entry.duration_seconds,
        )

    def progress_label(self) -> str:
        if self.duration_seconds and self.duration_seconds > 0:
            pct = min(100, int(self.progress_seconds * 100 / self.duration_seconds))
            return (
                f"{pct}% · {_fmt_time(self.progress_seconds)}"
                f" / {_fmt_time(self.duration_seconds)}"
            )
        if self.progress_seconds and self.progress_seconds > 0:
            return f"em {_fmt_time(self.progress_seconds)}"
        return ""

    def resume_at(self) -> float:
        """Segundos de onde retomar (0 se terminou ou vazio)."""
        if self.duration_seconds > 0 and self.progress_seconds / self.duration_seconds >= 0.92:
            return 0.0
        return max(0.0, float(self.progress_seconds or 0.0))
