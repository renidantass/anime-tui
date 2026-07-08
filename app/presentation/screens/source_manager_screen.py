from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Checkbox

from app.application.anime_service import AnimeService


class SourceManagerScreen(Screen):
    def __init__(self, service: AnimeService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service

    BINDINGS = [("escape", "back", "Voltar")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Gerenciar Fontes[/]", id="title")
        with Static(id="sources-container"):
            for entry in self._service.get_all_source_entries():
                avail = self._service.is_source_available(entry.identifier)
                status = "[white on #27ae60] ONLINE [/]" if avail else "[white on #c0392b] OFFLINE [/]"
                label = f"{entry.name} {status}"
                if not avail and entry.error:
                    label += f" [dim]({entry.error})[/]"
                cb = Checkbox(
                    label=label,
                    value=self._service.is_enabled(entry.identifier),
                    disabled=not avail,
                    id=f"source-{entry.identifier}",
                )
                yield cb
        yield Footer()

    def action_back(self) -> None:
        self.dismiss()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        cb_id = event.checkbox.id or ""
        if not cb_id.startswith("source-"):
            return
        identifier = cb_id[len("source-"):]
        self._service.set_enabled(identifier, event.checkbox.value)
