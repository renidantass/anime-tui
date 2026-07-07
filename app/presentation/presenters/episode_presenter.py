from app.application.dtos import EpisodeItem
from app.presentation.view_models import EpisodeVM


class EpisodePresenter:
    @staticmethod
    def present(episode: EpisodeItem) -> EpisodeVM:
        return EpisodeVM(
            number=episode.number,
            title=episode.title,
            link=episode.link,
            video_src=episode.video_src,
            date=episode.date,
            image=episode.image,
        )

    @staticmethod
    def present_many(episodes: list[EpisodeItem]) -> list[EpisodeVM]:
        return [EpisodePresenter.present(ep) for ep in episodes]