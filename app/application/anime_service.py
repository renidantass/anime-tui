from app.application.interfaces import IAnimeFeedReader


class AnimeService():
    __reader: IAnimeFeedReader = None

    def __init__(self, anime_feed_reader: IAnimeFeedReader) -> None:
        self.__reader = anime_feed_reader

    def get_last_episodes(self):
        return self.__reader.get_last_episodes()
    
    def search_by(self, name: str):
        return self.__reader.search_by(name)