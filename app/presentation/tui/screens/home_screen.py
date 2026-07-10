import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, LoadingIndicator, Static

from app.application import EpisodeEntry, SourceInfo
from app.application.anime_service import AnimeService
from app.infrastructure.player import open_video
from app.presentation.tui.screens.search_screen import SearchScreen
from app.presentation.tui.screens.source_manager_screen import SourceManagerScreen
from app.presentation.tui.screens.source_select_screen import SourceSelectScreen
from app.presentation.tui.utils.badge import badge_tag
from app.presentation.tui.utils.image_cache import get_image

_IMAGE_EXECUTOR = ThreadPoolExecutor(max_workers=8)


class HomeScreen(Screen):
    def __init__(
        self,
        service: AnimeService,
        player_deps,
        open_video,
        on_watch: Callable[..., None] | None = None,
        get_progress: Callable[[str], float] | None = None,
        on_progress: Callable[[str, float, float], None] | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._service = service
        self._player_deps = player_deps
        self._open_video = open_video
        self._on_watch = on_watch
        self._get_progress = get_progress
        self._on_progress = on_progress

    BINDINGS = [
        ("s", "search", "Buscar Anime"),
        ("r", "refresh", "Atualizar"),
        ("f", "filter", "Filtrar"),
        ("o", "sources", "Opções"),
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

    async def on_mount(self) -> None:
        self._all_entries: list[EpisodeEntry] = []
        self._filter_query: str = ""
        self._filter_active: bool = False
        self._filter_debounce: asyncio.Task | None = None
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#status", Static).update("[yellow]Carregando fontes...[/]")
        asyncio.create_task(self._initial_load())

    async def _initial_load(self) -> None:
        try:
            await asyncio.to_thread(self._service.init_sources)
        except Exception as e:
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update(f"[red]Erro ao carregar fontes: {e}[/]")
            return
        self.query_one("#status", Static).update("[yellow]Carregando episódios...[/]")
        await self._load_episodes()

    def action_search(self) -> None:
        self.app.push_screen(
            SearchScreen(
                self._service,
                on_watch=self._on_watch,
                get_progress=self._get_progress,
                on_progress=self._on_progress,
            )
        )

    def action_sources(self) -> None:
        self.app.push_screen(SourceManagerScreen(self._service))

    def action_refresh(self) -> None:
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#status", Static).update("[yellow]Atualizando...[/]")
        self.query_one("#episodes-list", ListView).clear()
        asyncio.create_task(self._load_episodes())

    def action_filter(self) -> None:
        label = self.query_one("#filter-label", Static)
        if label.display:
            self._filter_query = ""
            label.display = False
            if self._filter_active:
                self._rebuild_list(self._all_entries)
                self._filter_active = False
            self.query_one("#status", Static).update(
                f"[dim]{len(self._all_entries)} episódio(s) carregado(s)[/]"
            )
        else:
            self._filter_query = ""
            self._filter_active = False
            label.display = True
            self._update_filter_label()

    def _update_filter_label(self):
        self.query_one("#filter-label", Static).update(f"[yellow]Filtrar: {self._filter_query}▌[/]")

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
        if self._filter_debounce and not self._filter_debounce.done():
            self._filter_debounce.cancel()
        self._filter_debounce = asyncio.create_task(self._apply_filter_debounced())

    async def _apply_filter_debounced(self):
        await asyncio.sleep(0.15)
        query = self._filter_query.lower().strip()
        if query:
            filtered = [e for e in self._all_entries if query in e.title.lower()]
            self._filter_active = True
        else:
            filtered = self._all_entries
            self._filter_active = False
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
        try:
            ansi = get_image(entry.image, max_width=55) if entry.image else None
        except Exception:
            ansi = None

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

    async def _load_episodes(self) -> None:
        try:
            entries = await asyncio.to_thread(self._service.get_last_episodes)
            self._all_entries = entries
            list_view = self.query_one("#episodes-list", ListView)
            list_view.clear()

            urls = [(entry.image, 55) for entry in entries if entry.image]
            if urls:
                try:
                    futures = [_IMAGE_EXECUTOR.submit(get_image, url, w) for url, w in urls]
                    await asyncio.gather(*(asyncio.wrap_future(f) for f in futures))
                except Exception:
                    pass

            self._rebuild_list(entries)
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update(
                f"[dim]{len(entries)} episódio(s) carregado(s)[/]"
            )
        except Exception as e:
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update(f"[red]Erro: {e}[/]")
            self.query_one("#episodes-list", ListView).append(ListItem(Static(f"[red]{e}[/]")))

    def _open_episode(self, entry: EpisodeEntry) -> None:
        if len(entry.sources) == 1:
            src = entry.sources[0]
            asyncio.create_task(self._play_source(src, entry))
        elif len(entry.sources) > 1:

            def do_open(selected):
                asyncio.create_task(self._play_source(selected, entry))

            self.app.push_screen(SourceSelectScreen(entry.sources, do_open))

    def _record_history(self, entry: EpisodeEntry, src: SourceInfo) -> None:
        if not self._on_watch:
            return
        from app.application.title_utils import (
            extract_episode_number,
            normalize_watch_titles,
        )

        number = getattr(entry, "number", "") or ""
        if not number or number in {"?", "0"}:
            number = extract_episode_number(entry.title, src.link)
        anime_t, ep_t, ep_n = normalize_watch_titles(entry.title, entry.title, number)
        self._on_watch(
            anime_title=anime_t,
            episode_title=ep_t,
            episode_number=ep_n,
            episode_link=src.link,
            source_name=src.name,
            anime_image=entry.image,
            source_color=src.color,
        )

    def _set_play_status(self, msg: str) -> None:
        with suppress(Exception):
            self.query_one("#status", Static).update(msg)

    def _status_from_worker(self, msg: str) -> None:
        """Atualiza status a partir de thread do player (não bloqueia o worker)."""
        try:
            loop = getattr(self.app, "_loop", None)
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self._set_play_status, msg)
            else:
                self._set_play_status(msg)
        except Exception:
            pass

    async def _play_source(self, src: SourceInfo, entry: EpisodeEntry) -> None:
        # NÃO usar self.loading: cobre a tela inteira e esconde o status.
        self._set_play_status("[yellow]Preparando vídeo…[/]")
        try:
            self._set_play_status("[yellow]Buscando fonte do vídeo…[/]")
            play_ctx = await asyncio.to_thread(self._service.get_play_context, src.link, src.name)
            if not play_ctx or not play_ctx.url:
                self._set_play_status("[red]Fonte de vídeo não encontrada[/]")
                return

            # registra no histórico antes de tocar (para progresso)
            self._record_history(entry, src)
            start_at = 0.0
            if self._get_progress:
                start_at = float(self._get_progress(src.link) or 0.0)

            def on_status(msg: str) -> None:
                self._status_from_worker(f"[yellow]{msg}[/]")

            def on_position(pos: float, dur: float) -> None:
                if self._on_progress:
                    self._on_progress(src.link, pos, dur)

            ok = await asyncio.to_thread(
                open_video,
                play_ctx,
                status=on_status,
                start_at=start_at,
                on_position=on_position if self._on_progress else None,
            )
            if ok:
                msg = "[green]Player aberto[/]"
                if start_at > 1:
                    msg += f" [dim](retomando {int(start_at)}s)[/]"
                self._set_play_status(msg)
            else:
                self._set_play_status("[red]Não foi possível abrir o vídeo[/]")
        except Exception as e:
            self._set_play_status(f"[red]Erro: {e}[/]")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        entry: EpisodeEntry | None = event.item.meta.get("entry")
        if entry:
            self._open_episode(entry)
