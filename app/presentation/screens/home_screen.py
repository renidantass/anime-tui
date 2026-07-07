from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, ListView, ListItem, Label, Static

from app.application import AnimeService
from app.presentation.presenters import EpisodePresenter


class HomeScreen(Screen):
    def __init__(self, service: AnimeService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Últimos Episódios[/]", id="title")
        yield ListView(id="episodes-list")
        yield Footer()

    def on_mount(self) -> None:
        self._load_episodes()

    def _load_episodes(self) -> None:
        try:
            episodes = self._service.get_last_episodes()
            vms = EpisodePresenter.present_many(episodes)
            list_view = self.query_one("#episodes-list", ListView)
            list_view.clear()
            for vm in vms:
                list_view.append(ListItem(Label(vm.display_title)))
        except Exception as e:
            self.query_one("#episodes-list", ListView).append(
                ListItem(Label(f"Erro ao carregar: {e}"))
            )
