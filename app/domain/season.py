from dataclasses import dataclass
from app.domain.episode import Episode


@dataclass(slots=True)
class Season:
    number: int
    episodes: list[Episode]

    def get_episode(self, number: str) -> Episode | None:
        for ep in self.episodes:
            if ep.number == number:
                return ep
        return None

    def add_episode(self, episode: Episode) -> None:
        if not any(ep.number == episode.number for ep in self.episodes):
            self.episodes.append(episode)