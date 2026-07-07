from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, ListView, ListItem, Label, Input, Static

from app.application import AnimeService
from app.presentation.presenters import AnimePresenter


class SearchScreen(Screen):
    def __init__(self, service: AnimeService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Buscar Anime[/]", id="title")
        yield Input(placeholder="Digite o nome do anime...", id="search-input")
        yield ListView(id="results-list")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._search(event.value)

    def _search(self, name: str) -> None:
        if not name.strip():
            return
        try:
            animes = self._service.search_by(name.strip())
            vms = AnimePresenter.present_many(animes)
            list_view = self.query_one("#results-list", ListView)
            list_view.clear()
            for vm in vms:
                list_view.append(ListItem(Label(vm.display_title)))
        except Exception as e:
            self.query_one("#results-list", ListView).append(
                ListItem(Label(f"Erro na busca: {e}"))
            )
