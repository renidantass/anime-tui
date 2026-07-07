import webbrowser

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, ListView, ListItem, LoadingIndicator

from app.application import (
    EpisodeEntry,
    init_sources,
    get_last_episodes,
    get_video_src,
)
from app.presentation.screens.search_screen import SearchScreen
from app.presentation.screens.source_select_screen import SourceSelectScreen
from app.presentation.screens.source_manager_screen import SourceManagerScreen
from app.presentation.utils.image_cache import get_image
from app.presentation.utils.badge import badge_tag


class HomeScreen(Screen):
    BINDINGS = [
        ("s", "search", "Buscar Anime"),
        ("r", "refresh", "Atualizar"),
        ("f", "filter", "Filtrar"),
        ("F", "sources", "Fontes"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Últimos Episódios[/]", id="title")
        filter_label = Static("", id="filter-label")
        filter_label.display = False
        yield filter_label
        loading = LoadingIndicator(id="loading")
        loading.display = False
        yield loading
        yield Static("[dim]Carregando...[/]", id="status")
        yield ListView(id="episodes-list")
        yield Footer()

    def on_mount(self) -> None:
        self._all_entries: list[EpisodeEntry] = []
        self._filter_query: str = ""
        init_sources()
        self._load_episodes()

    def action_search(self) -> None:
        self.app.push_screen(SearchScreen())

    def action_sources(self) -> None:
        self.app.push_screen(SourceManagerScreen())

    def action_refresh(self) -> None:
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#status", Static).update("[dim]Atualizando...[/]")
        self.query_one("#episodes-list", ListView).clear()
        self.call_after_refresh(self._load_episodes)

    def action_filter(self) -> None:
        label = self.query_one("#filter-label", Static)
        if label.display:
            self._filter_query = ""
            label.display = False
            self._rebuild_list(self._all_entries)
            self.query_one("#status", Static).update(
                f"[dim]{len(self._all_entries)} episódio(s) carregado(s)[/]"
            )
        else:
            self._filter_query = ""
            label.display = True
            self._update_filter_label()
            self._rebuild_list(self._all_entries)

    def _update_filter_label(self):
        self.query_one("#filter-label", Static).update(
            f"[yellow]Filtrar: {self._filter_query}▌[/]"
        )

    def on_key(self, event) -> None:
        label = self.query_one("#filter-label", Static)
        if not label.display:
            return

        if event.key == "escape":
            self._filter_query = ""
            label.display = False
            self._rebuild_list(self._all_entries)
            self.query_one("#status", Static).update(
                f"[dim]{len(self._all_entries)} episódio(s) carregado(s)[/]"
            )
            event.stop()
        elif event.key == "enter":
            label.display = False
            self._rebuild_list(self._all_entries)
            self.query_one("#status", Static).update(
                f"[dim]{len(self._all_entries)} episódio(s) carregado(s)[/]"
            )
            event.stop()
        elif event.key == "backspace":
            self._filter_query = self._filter_query[:-1]
            self._update_filter_label()
            self._apply_filter()
            event.stop()
        elif len(event.key) == 1:
            self._filter_query += event.key
            self._update_filter_label()
            self._apply_filter()
            event.stop()

    def _apply_filter(self):
        query = self._filter_query.lower().strip()
        if query:
            filtered = [
                e for e in self._all_entries
                if query in e.title.lower()
            ]
        else:
            filtered = self._all_entries
        self._rebuild_list(filtered)
        self.query_one("#status", Static).update(
            f"[dim]{len(filtered)}/{len(self._all_entries)} episódio(s)[/]"
        )

    def _rebuild_list(self, entries: list[EpisodeEntry]) -> None:
        list_view = self.query_one("#episodes-list", ListView)
        list_view.clear()
        for entry in entries:
            content = self._build_item(entry)
            item = ListItem(content)
            item.meta = {"entry": entry}
            list_view.append(item)

    def _build_item(self, entry: EpisodeEntry) -> Static:
        ansi = get_image(entry.image, max_width=40) if entry.image else None

        table = Table.grid(padding=(0, 2))
        table.add_column(width=ansi.width if ansi else 1)
        table.add_column(ratio=1)

        text = f"[bold]{entry.title}[/]"
        if entry.sources:
            badges = " ".join(badge_tag(s.name, s.color) for s in entry.sources)
            text += f"\n{badges}"

        if ansi:
            table.add_row(ansi, Text.from_markup(text))
        else:
            table.add_row(Text.from_markup(text))

        return Static(table)

    def _load_episodes(self) -> None:
        try:
            entries = get_last_episodes()
            self._all_entries = entries
            list_view = self.query_one("#episodes-list", ListView)
            list_view.clear()

            from concurrent.futures import ThreadPoolExecutor, as_completed
            urls = [(entry.image, 40) for entry in entries if entry.image]
            if urls:
                with ThreadPoolExecutor(max_workers=8) as ex:
                    futures = {ex.submit(get_image, url, w): url for url, w in urls}
                    for future in as_completed(futures):
                        pass

            self._rebuild_list(entries)
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update(
                f"[dim]{len(entries)} episódio(s) carregado(s)[/]"
            )
        except Exception as e:
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update(f"[red]Erro: {e}[/]")
            self.query_one("#episodes-list", ListView).append(
                ListItem(Static(f"[red]{e}[/]"))
            )

    def _open_episode(self, entry: EpisodeEntry) -> None:
        if len(entry.sources) == 1:
            src = entry.sources[0]
            if src.video_src:
                webbrowser.open(src.video_src)
            else:
                try:
                    vs = get_video_src(src.link, src.name)
                    if vs:
                        webbrowser.open(vs)
                except Exception:
                    pass
        elif len(entry.sources) > 1:
            def do_open(selected):
                if selected.video_src:
                    webbrowser.open(selected.video_src)
                else:
                    try:
                        vs = get_video_src(selected.link, selected.name)
                        if vs:
                            webbrowser.open(vs)
                    except Exception:
                        pass

            self.app.push_screen(
                SourceSelectScreen(entry.sources, do_open)
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        entry: EpisodeEntry | None = event.item.meta.get("entry")
        if entry:
            self._open_episode(entry)
