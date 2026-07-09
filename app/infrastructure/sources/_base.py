from app.application.interfaces import IAnimeFeedReader
from app.domain import PlayContext


class AnimeSource(IAnimeFeedReader):
    name: str = ""
    identifier: str = ""
    base_url: str = ""
    color: str = ""
    has_search: bool = True
    has_details: bool = True
    # html.parser (stdlib) — evita dependência nativa do lxml no binário
    default_analyzer: str = "html.parser"

    def get_play_context(self, episode_link: str) -> PlayContext:
        """Default: abre a própria página do episódio (não é stream direto)."""
        return PlayContext.page(episode_link)
