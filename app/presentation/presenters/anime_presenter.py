from app.application.dtos import AnimeDetail
from app.presentation.presenters.episode_presenter import EpisodePresenter
from app.presentation.view_models import AnimeVM, SeasonVM


class AnimePresenter:
    @staticmethod
    def present(anime: AnimeDetail) -> AnimeVM:
        seasons = None
        if anime.seasons:
            seasons = [
                SeasonVM(
                    number=s.number,
                    episodes=EpisodePresenter.present_many(s.episodes),
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

    @staticmethod
    def present_many(animes: list[AnimeDetail]) -> list[AnimeVM]:
        return [AnimePresenter.present(a) for a in animes]