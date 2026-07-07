from dataclasses import dataclass
from typing import Optional
from app.domain.season import Season


@dataclass(slots=True)
class Anime:
    title: str
    rating: str
    link: str
    image: str = ''
    description: Optional[str] = None
    seasons: Optional[list[Season]] = None

    def get_season(self, number: int) -> Season | None:
        if not self.seasons:
            return None
        for s in self.seasons:
            if s.number == number:
                return s
        return None

    def total_episodes(self) -> int:
        if not self.seasons:
            return 0
        return sum(len(s.episodes) for s in self.seasons)

    @property
    def display_title(self) -> str:
        rating = f" ({self.rating})" if self.rating else ""
        return f"{self.title}{rating}"
