from dataclasses import dataclass


@dataclass(slots=True)
class Episode:
    number: str
    title: str
    link: str
    video_src: str
    image: str = ''
    date: str = '00/00'

    def has_video(self) -> bool:
        return bool(self.video_src)

    @property
    def display_number(self) -> str:
        return f"Episódio {self.number}"