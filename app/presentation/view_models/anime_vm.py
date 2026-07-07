from dataclasses import dataclass

from app.presentation.view_models.season_vm import SeasonVM


@dataclass(slots=True)
class AnimeVM:
    title: str
    rating: str
    link: str
    image: str = ''
    description: str | None = None
    seasons: list[SeasonVM] | None = None

    @property
    def display_title(self) -> str:
        return f"{self.title} [yellow]({self.rating})[/]"
