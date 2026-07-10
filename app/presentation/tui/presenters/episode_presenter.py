from app.application.dtos import EpisodeItem
from app.presentation.tui.view_models import EpisodeVM


def present_episode(episode: EpisodeItem) -> EpisodeVM:
    return EpisodeVM(
        number=episode.number,
        title=episode.title,
        link=episode.link,
        video_src=episode.video_src,
        date=episode.date,
        image=episode.image,
    )


def present_many(episodes: list[EpisodeItem]) -> list[EpisodeVM]:
    return [present_episode(ep) for ep in episodes]