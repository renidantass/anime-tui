from dataclasses import dataclass

from app.domain.season import Season


@dataclass(slots=True)
class Anime:
    title: str
    rating: str
    link: str
    image: str = ""
    description: str | None = None
    seasons: list[Season] | None = None
