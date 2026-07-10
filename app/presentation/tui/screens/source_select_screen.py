from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import ListItem, ListView, Static

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
            for idx, s in enumerate(self._sources):
                item = ListItem(Static(f"[bold]{s.name}[/]"))
                item.meta = {"index": idx}
                yield item

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.item.meta.get("index")
        if idx is not None:
            self.app.pop_screen()
            self._callback(self._sources[idx])
