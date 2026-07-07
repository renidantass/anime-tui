from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Checkbox

from app.application import (
    is_enabled,
    set_enabled,
    get_all_source_entries,
    is_source_available,
)


class SourceManagerScreen(Screen):
    BINDINGS = [("escape", "back", "Voltar")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Gerenciar Fontes[/]", id="title")
        with Static(id="sources-container"):
            for entry in get_all_source_entries():
                avail = is_source_available(entry.source.identifier)
                status = "[green]● ONLINE[/]" if avail else "[red]● OFFLINE[/]"
                name = f"{entry.source.name} {status}"
                if not avail and entry.error:
                    name += f" [dim]({entry.error})[/]"
                cb = Checkbox(
                    label=name,
                    value=is_enabled(entry.source.identifier),
                    disabled=not avail,
                )
                yield cb
        yield Footer()

    def action_back(self) -> None:
        self.dismiss()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        label = event.checkbox.label
        raw = label.plain if hasattr(label, 'plain') else str(label)
        name = raw.split(" ")[0].strip()

        for entry in get_all_source_entries():
            if entry.source.name == name:
                set_enabled(entry.source.identifier, event.checkbox.value)
                break
