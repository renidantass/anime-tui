from dataclasses import dataclass


@dataclass(slots=True)
class Episode:
    number: str
    title: str
    link: str
    video_src: str
    date: str = '00/00'