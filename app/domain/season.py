from dataclasses import dataclass
from app.domain.episode import Episode


@dataclass(slots=True)
class Season:
    number: int
    episodes: list[Episode]