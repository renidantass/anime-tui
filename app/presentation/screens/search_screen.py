from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, ListView, ListItem, Input, Static, LoadingIndicator

from app.application import (
    AnimeEntry,
    search_by,
    get_anime_details,
)
from app.presentation.presenters.anime_presenter import AnimePresenter
from app.presentation.screens.anime_detail_screen import AnimeDetailScreen
from app.presentation.utils.image_cache import get_image
from app.presentation.utils.badge import badge_tag


class SearchScreen(Screen):
    BINDINGS = [("escape", "back", "Voltar")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Buscar Anime[/]", id="title")
        yield Input(placeholder="Digite o nome do anime...", id="search-input")
        loading = LoadingIndicator(id="search-loading")
        loading.display = False
        yield loading
        yield ListView(id="results-list")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()
        self._search_query = ""

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._search_query = event.value
        self.query_one("#search-loading", LoadingIndicator).display = True
        self.query_one("#results-list", ListView).clear()
        self.call_after_refresh(self._do_search)

    def _do_search(self):
        self._search(self._search_query)

    def _build_item(self, entry: AnimeEntry) -> Static:
        ansi = get_image(entry.image, max_width=30) if entry.image else None

        table = Table.grid(padding=(0, 2))
        table.add_column(width=ansi.width if ansi else 1)
        table.add_column(ratio=1)

        text = f"[bold]{entry.title}[/]"
        if entry.rating:
            text += f"\n[dim]Nota: {entry.rating}[/]"
        if entry.sources:
            badges = " ".join(badge_tag(s.name, s.color) for s in entry.sources)
            text += f"\n{badges}"

        if ansi:
            table.add_row(ansi, Text.from_markup(text))
        else:
            table.add_row(Text.from_markup(text))

        return Static(table)

    def _search(self, name: str) -> None:
        if not name.strip():
            return

        list_view = self.query_one("#results-list", ListView)
        list_view.clear()

        try:
            entries = search_by(name.strip())
            list_view.clear()
            if not entries:
                list_view.append(
                    ListItem(Static("[yellow]Nenhum resultado encontrado[/]"))
                )
                self.query_one("#search-loading", LoadingIndicator).display = False
                return

            from concurrent.futures import ThreadPoolExecutor, as_completed
            urls = [(entry.image, 30) for entry in entries if entry.image]
            if urls:
                with ThreadPoolExecutor(max_workers=8) as ex:
                    futures = {ex.submit(get_image, url, w): url for url, w in urls}
                    for future in as_completed(futures):
                        pass

            for entry in entries:
                content = self._build_item(entry)
                item = ListItem(content)
                item.meta = {"entry": entry}
                list_view.append(item)
            self.query_one("#search-loading", LoadingIndicator).display = False
            list_view.focus()
        except Exception as e:
            self.query_one("#search-loading", LoadingIndicator).display = False
            list_view.clear()
            list_view.append(ListItem(Static(f"[red]Erro na busca: {e}[/]")))

    def _open_anime(self, entry: AnimeEntry) -> None:
        link = entry.sources[0].link if entry.sources else ""
        if not link:
            return
        anime = get_anime_details(link)
        if anime.title:
            anime_vm = AnimePresenter.present(anime)
            self.app.push_screen(AnimeDetailScreen(anime_vm))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        entry: AnimeEntry | None = event.item.meta.get("entry")
        if entry:
            self._open_anime(entry)
