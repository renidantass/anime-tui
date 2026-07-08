import webbrowser

from app.application.anime_service import AnimeService
from app.application.watch_history_service import WatchHistoryService
from app.infrastructure.sources import SourceDiscovery
from app.presentation.screens import HomeScreen, HistoryScreen
from app.presentation.view_models.history_vm import HistoryVM
from textual.app import App


class AnimeTUI(App):
    def __init__(self, service: AnimeService, history_service: WatchHistoryService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service
        self._history_service = history_service

    BINDINGS = [
        ("q", "quit", "Sair"),
        ("h", "history", "Histórico"),
    ]

    def on_mount(self) -> None:
        self.push_screen(HomeScreen(
            self._service,
            on_watch=self._history_service.add_entry,
        ))

    def action_quit(self) -> None:
        self.exit()

    def action_history(self) -> None:
        self.push_screen(HistoryScreen(
            load_history=lambda: [HistoryVM.from_entity(e) for e in self._history_service.get_all()],
            clear_history=self._history_service.clear_all,
            open_url=webbrowser.open,
        ))


def main():
    service = AnimeService(source_discovery=SourceDiscovery())
    history_service = WatchHistoryService()
    app = AnimeTUI(service=service, history_service=history_service)
    app.run()


if __name__ == "__main__":
    main()
