import asyncio
from datetime import datetime, timezone
from typing import Callable

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, ListView, ListItem, LoadingIndicator

from app.presentation.view_models.history_vm import HistoryVM
from app.presentation.utils.badge import badge_tag
from app.presentation.utils.image_cache import get_image


def _relative_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return f"há {seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"há {minutes}min"
        hours = minutes // 60
        if hours < 24:
            return f"há {hours}h"
        days = hours // 24
        if days < 30:
            return f"há {days}d"
        months = days // 30
        if months == 1:
            return "há 1 mês"
        if months < 12:
            return f"há {months} meses"
        years = months // 12
        if years == 1:
            return "há 1 ano"
        return f"há {years} anos"
    except (ValueError, TypeError):
        return iso_str


class HistoryScreen(Screen):
    DEFAULT_CSS = """
    #loading {
        height: 1;
        width: 100%;
        content-align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "back", "Voltar"),
        ("r", "refresh", "Atualizar"),
        ("c", "clear", "Limpar"),
    ]

    def __init__(
        self,
        load_history: Callable[[], list[HistoryVM]],
        clear_history: Callable[[], None],
        open_url: Callable[[str], None],
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._load_history = load_history
        self._clear_history = clear_history
        self._open_url = open_url
        self._confirming_clear = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Histórico de Assistidos[/]", id="title")
        loading = LoadingIndicator(id="loading")
        loading.display = False
        yield loading
        yield Static("[dim]Carregando histórico...[/]", id="status")
        yield ListView(id="history-list")
        yield Footer()

    def on_mount(self) -> None:
        self._all_history: list[HistoryVM] = []
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#status", Static).update("[yellow]Carregando histórico...[/]")
        asyncio.create_task(self._do_load())

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self._confirming_clear = False
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#status", Static).update("[yellow]Atualizando...[/]")
        self.query_one("#history-list", ListView).clear()
        asyncio.create_task(self._do_load())

    def action_clear(self) -> None:
        if self._confirming_clear:
            self._confirming_clear = False
            self.query_one("#loading", LoadingIndicator).display = True
            self.query_one("#status", Static).update("[yellow]Limpando histórico...[/]")
            asyncio.create_task(self._do_clear())
        else:
            self._confirming_clear = True
            self.query_one("#status", Static).update("[red]Pressione 'c' novamente para confirmar[/]")

    async def _do_load(self) -> None:
        try:
            entries = await asyncio.to_thread(self._load_history)
            self._all_history = entries
            self._rebuild_list(entries)
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update(
                f"[dim]{len(entries)} registro(s) carregado(s)[/]"
            )
        except Exception as e:
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update(f"[red]Erro: {e}[/]")
            self.query_one("#history-list", ListView).append(
                ListItem(Static(f"[red]{e}[/]"))
            )

    async def _do_clear(self) -> None:
        try:
            await asyncio.to_thread(self._clear_history)
            self._all_history = []
            self.query_one("#history-list", ListView).clear()
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update("[green]Histórico limpo[/]")
        except Exception as e:
            self.query_one("#loading", LoadingIndicator).display = False
            self.query_one("#status", Static).update(f"[red]Erro ao limpar: {e}[/]")

    def _rebuild_list(self, history: list[HistoryVM]) -> None:
        list_view = self.query_one("#history-list", ListView)
        list_view.clear()
        for entry in history:
            content = self._build_item(entry)
            item = ListItem(content)
            item.meta = {"entry": entry}
            list_view.append(item)

    def _build_item(self, entry: HistoryVM) -> Static:
        ansi = get_image(entry.anime_image, max_width=40) if entry.anime_image else None

        table = Table.grid(padding=(0, 2))
        table.add_column(width=ansi.width if ansi else 1)
        table.add_column(ratio=1)

        badge = badge_tag(entry.source_name, entry.source_color)
        time_str = _relative_time(entry.watched_at)

        text = f"[bold]{entry.anime_title or entry.episode_title}[/]"
        text += f"\n{entry.episode_number} - {entry.episode_title}"
        text += f"\n{badge} [dim]{time_str}[/]"

        if ansi:
            table.add_row(ansi, Text.from_markup(text))
        else:
            table.add_row(Text.from_markup(text))

        return Static(table)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        entry: HistoryVM | None = event.item.meta.get("entry")
        if entry and entry.episode_link:
            self._open_url(entry.episode_link)
