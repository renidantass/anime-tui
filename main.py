"""Entrypoint TUI — animes-tui."""

from textual.app import App

from bootstrap import (
    build_tui_wiring,
    build_player_deps,
    build_image_deps,
    open_video,
)
from app.presentation.tui import HistoryVM, HomeScreen, HistoryScreen
from app.presentation.tui.utils.image_cache import configure as configure_images


class AnimeTUI(App):
    def __init__(self, service, history_service, player_deps):
        super().__init__()
        self._service = service
        self._history_service = history_service
        self._player_deps = player_deps

    BINDINGS = [
        ("q", "quit", "Sair"),
        ("h", "history", "Histórico"),
    ]

    def on_mount(self) -> None:
        hs = self._history_service
        self.push_screen(
            HomeScreen(
                self._service,
                self._player_deps,
                open_video,
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
                open_video=open_video,
                on_progress=lambda link, pos, dur: hs.update_progress(link, pos, dur),
            )
        )


def main():
    configure_images(**build_image_deps())
    service, history_service = build_tui_wiring()
    player_deps = build_player_deps()
    app = AnimeTUI(service, history_service, player_deps)
    app.run()


if __name__ == "__main__":
    main()
