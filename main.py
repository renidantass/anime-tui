from app.application.anime_service import AnimeService
from app.application.service_facade import set_service
from app.infrastructure.sources import SourceDiscovery
from app.presentation.screens import HomeScreen
from textual.app import App


service = AnimeService(source_discovery=SourceDiscovery())
set_service(service)


class AnimeTUI(App):
    BINDINGS = [("q", "quit", "Sair")]

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())

    def action_quit(self) -> None:
        self.exit()


def main():
    app = AnimeTUI()
    app.run()


if __name__ == "__main__":
    main()
