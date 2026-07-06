from dataclasses import dataclass
from app.domain.season import Season


@dataclass(slots=True)
class Anime:
    title: str
    description: str
    rating: str
    seasons: list[Season]