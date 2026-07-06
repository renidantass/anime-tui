from abc import ABC, abstractmethod
from app.domain import Anime, Episode



class IAnimeFeedReader(ABC):
    @abstractmethod
    def get_last_episodes(self) -> list[Episode]:
        pass

    @abstractmethod
    def search_by(self, name: str) -> Anime:
        pass