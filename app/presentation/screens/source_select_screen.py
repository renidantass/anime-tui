from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static, ListView, ListItem

from app.application import SourceInfo


class SourceSelectScreen(Screen):
    BINDINGS = [("escape", "cancel", "Cancelar")]

    def __init__(self, sources: list[SourceInfo], callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sources = sources
        self._callback = callback

    def compose(self) -> ComposeResult:
        yield Static("[bold]Escolha a fonte:[/]")
        with ListView(id="source-list"):
            for s in self._sources:
                yield ListItem(Static(f"[bold]{s.name}[/]"))

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        for idx, child in enumerate(self.query_one("#source-list", ListView).children):
            if child is event.item:
                selected = self._sources[idx]
                self.app.pop_screen()
                self._callback(selected)
                return
