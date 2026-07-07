from app.domain import Anime
from app.presentation.view_models import AnimeVM


class AnimePresenter:
    @staticmethod
    def present(anime: Anime) -> AnimeVM:
        return AnimeVM(
            title=anime.title,
            rating=anime.rating,
            link=anime.link,
            description=anime.description,
        )

    @staticmethod
    def present_many(animes: list[Anime]) -> list[AnimeVM]:
        return [AnimePresenter.present(a) for a in animes]
