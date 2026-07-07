from abc import ABC, abstractmethod
from app.domain import Anime, Episode


class IAnimeFeedReader(ABC):
    name: str = ""
    identifier: str = ""
    color: str = ""
    has_search: bool = True
    has_details: bool = True

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
    def get_video_src(self, episode_link: str) -> str:
        pass
