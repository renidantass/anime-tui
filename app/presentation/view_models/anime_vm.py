from dataclasses import dataclass


@dataclass(slots=True)
class AnimeVM:
    title: str
    rating: str
    link: str
    image: str = ''
    description: str | None = None

    @property
    def display_title(self) -> str:
        return f"{self.title} [yellow]({self.rating})[/]"
