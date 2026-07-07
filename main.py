from app.application.anime_service import AnimeService
from app.infrastructure.sources import SourceDiscovery
from app.presentation.screens import HomeScreen
from textual.app import App


class AnimeTUI(App):
    def __init__(self, service: AnimeService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service

    BINDINGS = [("q", "quit", "Sair")]

    def on_mount(self) -> None:
        self._service.init_sources()
        self.push_screen(HomeScreen(self._service))

    def action_quit(self) -> None:
        self.exit()


def main():
    service = AnimeService(source_discovery=SourceDiscovery())
    app = AnimeTUI(service=service)
    app.run()


if __name__ == "__main__":
    main()
