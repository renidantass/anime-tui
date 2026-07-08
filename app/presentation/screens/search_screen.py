import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, ListView, ListItem, Input, Static, LoadingIndicator

from app.application import AnimeEntry, SourceInfo
from app.application.anime_service import AnimeService
from app.presentation.presenters.anime_presenter import present_anime
from app.presentation.screens.anime_detail_screen import AnimeDetailScreen
from app.presentation.screens.source_select_screen import SourceSelectScreen
from app.presentation.utils.image_cache import get_image
from app.presentation.utils.badge import badge_tag

_SEARCH_IMAGE_EXECUTOR = ThreadPoolExecutor(max_workers=8)


class SearchScreen(Screen):
    def __init__(
        self,
        service: AnimeService,
        on_watch: Callable[..., None] | None = None,
        get_progress: Callable[[str], float] | None = None,
        on_progress: Callable[[str, float, float], None] | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._service = service
        self._on_watch = on_watch
        self._get_progress = get_progress
        self._on_progress = on_progress
        self._debounce_timer = None
        self._search_history: list[str] = []
        self._search_task: asyncio.Task | None = None

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

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._debounce_timer:
            self._debounce_timer.reset()

        if not event.value.strip():
            self._show_suggestions()
            return

        self._debounce_timer = self.set_timer(0.3, self._do_search)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._debounce_timer:
            self._debounce_timer.reset()
        if event.value.strip():
            self._do_search()

    def on_input_focused(self, event: Input.Focused) -> None:
        inp = self.query_one("#search-input", Input)
        if not inp.value.strip():
            self._show_suggestions()

    def _show_suggestions(self) -> None:
        list_view = self.query_one("#results-list", ListView)
        list_view.clear()
        if not self._search_history:
            list_view.append(
                ListItem(Static("[dim]Digite para buscar...[/]"))
            )
            return
        for term in reversed(self._search_history):
            item = ListItem(Static(f"\u23ce {term}"))
            item.meta = {"suggestion": term}
            list_view.append(item)

    def _do_search(self) -> None:
        inp = self.query_one("#search-input", Input)
        query = inp.value.strip()
        if not query:
            return
        if self._search_task and not self._search_task.done():
            self._search_task.cancel()
        self.query_one("#search-loading", LoadingIndicator).display = True
        self.query_one("#results-list", ListView).clear()
        self._search_task = asyncio.create_task(self._search(query))

    def _build_item(self, entry: AnimeEntry) -> Static:
        ansi = get_image(entry.image, max_width=35) if entry.image else None

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

    async def _search(self, name: str) -> None:
        if not name.strip():
            return

        list_view = self.query_one("#results-list", ListView)
        list_view.clear()

        try:
            entries = await asyncio.to_thread(self._service.search_by, name.strip())
            list_view.clear()
            if not entries:
                list_view.append(
                    ListItem(Static("[yellow]Nenhum resultado encontrado[/]"))
                )
                self.query_one("#search-loading", LoadingIndicator).display = False
                return

            if name.strip() not in self._search_history:
                self._search_history.append(name.strip())
                if len(self._search_history) > 20:
                    self._search_history = self._search_history[-20:]

            urls = [(entry.image, 35) for entry in entries if entry.image]
            if urls:
                futures = [_SEARCH_IMAGE_EXECUTOR.submit(get_image, url, w) for url, w in urls]
                await asyncio.gather(*(asyncio.wrap_future(f) for f in futures))

            for entry in entries:
                content = self._build_item(entry)
                item = ListItem(content)
                item.meta = {"entry": entry}
                list_view.append(item)
            self.query_one("#search-loading", LoadingIndicator).display = False
            list_view.focus()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.query_one("#search-loading", LoadingIndicator).display = False
            list_view.clear()
            list_view.append(ListItem(Static(f"[red]Erro na busca: {e}[/]")))

    def _open_anime(self, entry: AnimeEntry) -> None:
        if not entry.sources:
            return

        def _do_open(source: SourceInfo) -> None:
            self.loading = True
            asyncio.create_task(self._open_anime_details(source))

        if len(entry.sources) == 1:
            _do_open(entry.sources[0])
        else:
            self.app.push_screen(SourceSelectScreen(entry.sources, _do_open))

    async def _open_anime_details(self, source: SourceInfo) -> None:
        try:
            anime = await asyncio.to_thread(self._service.get_anime_details, source.link)
            self.loading = False
            if anime.title:
                anime_vm = present_anime(anime)
                self.app.push_screen(AnimeDetailScreen(
                    self._service,
                    anime_vm,
                    source_name=source.name,
                    source_color=source.color,
                    on_watch=self._on_watch,
                    get_progress=self._get_progress,
                    on_progress=self._on_progress,
                ))
        except Exception:
            self.loading = False

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        suggestion = event.item.meta.get("suggestion")
        if suggestion:
            inp = self.query_one("#search-input", Input)
            inp.value = suggestion
            self._do_search()
            return
        entry: AnimeEntry | None = event.item.meta.get("entry")
        if entry:
            self._open_anime(entry)
