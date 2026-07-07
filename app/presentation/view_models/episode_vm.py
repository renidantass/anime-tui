from dataclasses import dataclass


@dataclass(slots=True)
class EpisodeVM:
    number: str
    title: str
    link: str
    video_src: str
    date: str

    @property
    def display_title(self) -> str:
        return f"{self.number} - {self.title}"
