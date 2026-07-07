from app.application import AnimeService
from app.infrastructure import AnimesOnlineFeedReader
from app.presentation.screens import HomeScreen
from textual.app import App


class AnimeTUI(App):
    def __init__(self, service: AnimeService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service

    def on_mount(self) -> None:
        self.push_screen(HomeScreen(self._service))


def main():
    feed_reader = AnimesOnlineFeedReader()
    service = AnimeService(feed_reader)
    app = AnimeTUI(service)
    app.run()


if __name__ == "__main__":
    main()
