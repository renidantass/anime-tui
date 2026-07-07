from app.application.interfaces import IAnimeFeedReader


class AnimeSource(IAnimeFeedReader):
    name: str = ""
    identifier: str = ""
    base_url: str = ""
    color: str = ""
    has_search: bool = True
    has_details: bool = True
