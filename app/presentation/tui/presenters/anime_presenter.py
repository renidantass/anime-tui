from app.application.dtos import AnimeDetail
from app.presentation.tui.presenters.episode_presenter import present_many
from app.presentation.tui.view_models import AnimeVM, SeasonVM


def present_anime(anime: AnimeDetail) -> AnimeVM:
    seasons = None
    if anime.seasons:
        seasons = [
            SeasonVM(
                number=s.number,
                episodes=present_many(s.episodes),
            )
            for s in anime.seasons
        ]
    return AnimeVM(
        title=anime.title,
        rating=anime.rating,
        link=anime.link,
        image=anime.image,
        description=anime.description,
        seasons=seasons,
    )