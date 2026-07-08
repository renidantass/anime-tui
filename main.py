from app.application.anime_service import AnimeService
from app.application.watch_history_service import WatchHistoryService
from app.infrastructure.sources import SourceDiscovery
from app.presentation.screens import HomeScreen, HistoryScreen
from app.presentation.view_models.history_vm import HistoryVM
from textual.app import App


class AnimeTUI(App):
    def __init__(
        self,
        service: AnimeService,
        history_service: WatchHistoryService,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._service = service
        self._history_service = history_service

    BINDINGS = [
        ("q", "quit", "Sair"),
        ("h", "history", "Histórico"),
    ]

    def on_mount(self) -> None:
        hs = self._history_service
        self.push_screen(
            HomeScreen(
                self._service,
                on_watch=hs.add_entry,
                get_progress=hs.get_progress,
                on_progress=lambda link, pos, dur: hs.update_progress(link, pos, dur),
            )
        )

    def action_quit(self) -> None:
        self.exit()

    def action_history(self) -> None:
        hs = self._history_service
        self.push_screen(
            HistoryScreen(
                load_history=lambda: [
                    HistoryVM.from_entity(e) for e in hs.get_all_deduped()
                ],
                clear_history=hs.clear_all,
                service=self._service,
                on_progress=lambda link, pos, dur: hs.update_progress(link, pos, dur),
            )
        )


def main():
    service = AnimeService(source_discovery=SourceDiscovery())
    history_service = WatchHistoryService()
    app = AnimeTUI(service=service, history_service=history_service)
    app.run()


if __name__ == "__main__":
    main()
