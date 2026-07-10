from dataclasses import dataclass

from app.presentation.tui.view_models.episode_vm import EpisodeVM


@dataclass(slots=True)
class SeasonVM:
    number: int
    episodes: list[EpisodeVM]
