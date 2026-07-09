from app.application.interfaces import IAnimeFeedReader
from app.domain import PlayContext


class AnimeSource(IAnimeFeedReader):
    name: str = ""
    identifier: str = ""
    base_url: str = ""
    color: str = ""
    has_search: bool = True
    has_details: bool = True
    default_analyzer: str = "lxml"

    def get_play_context(self, episode_link: str) -> PlayContext:
        """Default: abre a própria página do episódio (não é stream direto)."""
        return PlayContext.page(episode_link)
