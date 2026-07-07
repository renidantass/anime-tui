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
                status = "[green]● ONLINE[/]" if avail else "[red]● OFFLINE[/]"
                label = f"{entry.name} {status}"
                if not avail and entry.error:
                    label += f" [dim]({entry.error})[/]"
                cb = Checkbox(
                    label=label,
                    value=self._service.is_enabled(entry.identifier),
                    disabled=not avail,
                )
                yield cb
        yield Footer()

    def action_back(self) -> None:
        self.dismiss()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        label = event.checkbox.label
        raw = label.plain if hasattr(label, 'plain') else str(label)
        source_name = raw.split(" ")[0].strip()

        for entry in self._service.get_all_source_entries():
            if entry.name == source_name:
                self._service.set_enabled(entry.identifier, event.checkbox.value)
                break
