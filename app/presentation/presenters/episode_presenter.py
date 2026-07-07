from app.domain import Episode
from app.presentation.view_models import EpisodeVM


class EpisodePresenter:
    @staticmethod
    def present(episode: Episode) -> EpisodeVM:
        return EpisodeVM(
            number=episode.number,
            title=episode.title,
            link=episode.link,
            video_src=episode.video_src,
            date=episode.date,
            image=episode.image,
        )

    @staticmethod
    def present_many(episodes: list[Episode]) -> list[EpisodeVM]:
        return [EpisodePresenter.present(ep) for ep in episodes]
