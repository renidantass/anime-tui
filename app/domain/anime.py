from dataclasses import dataclass
from typing import Optional
from app.domain.season import Season


@dataclass(slots=True)
class Anime:
    title: str
    rating: str
    link: str
    description: Optional[str] = None
    seasons: Optional[list[Season]] = None
