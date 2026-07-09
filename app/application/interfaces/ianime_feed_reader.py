from abc import ABC, abstractmethod

from app.domain import Anime, Episode, PlayContext


class IAnimeFeedReader(ABC):
    @abstractmethod
    def get_last_episodes(self) -> list[Episode]:
        pass

    @abstractmethod
    def search_by(self, name: str) -> list[Anime]:
        pass

    @abstractmethod
    def get_anime_details(self, link: str) -> Anime:
        pass

    @abstractmethod
    def get_play_context(self, episode_link: str) -> PlayContext:
        """Resolve URL + headers de anti-leech para o player (sem heurística global)."""

    def get_video_src(self, episode_link: str) -> str:
        """Compat: só a URL. Prefira :meth:`get_play_context`."""
        ctx = self.get_play_context(episode_link)
        return ctx.url if ctx and ctx.url else ""
