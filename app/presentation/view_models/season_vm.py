from dataclasses import dataclass

from app.presentation.view_models.episode_vm import EpisodeVM


@dataclass(slots=True)
class SeasonVM:
    number: int
    episodes: list[EpisodeVM]
