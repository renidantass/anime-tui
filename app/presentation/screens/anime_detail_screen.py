import asyncio
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Tree

from app.application.anime_service import AnimeService
from app.infrastructure.player import open_video
from app.presentation.utils.image_cache import get_image
from app.presentation.view_models import AnimeVM, EpisodeVM


class AnimeDetailScreen(Screen):
    DEFAULT_CSS = """
    #detail-body {
        height: 1fr;
    }
    #anime-poster {
        width: auto;
        margin-right: 2;
    }
    #episodes-tree {
        width: 1fr;
    }
    """

    BINDINGS = [("escape", "back", "Voltar")]

    def __init__(
        self,
        service: AnimeService,
        anime_vm: AnimeVM,
        source_name: str = "Detalhes",
        source_color: str = "",
        on_watch: Callable[..., None] | None = None,
        get_progress: Callable[[str], float] | None = None,
        on_progress: Callable[[str, float, float], None] | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._service = service
        self._anime_vm = anime_vm
        self._source_name = source_name
        self._source_color = source_color
        self._on_watch = on_watch
        self._get_progress = get_progress
        self._on_progress = on_progress

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"[bold]{self._anime_vm.title}[/]", id="anime-title")
        with Horizontal(id="detail-body"):
            yield Static(id="anime-poster")
            yield Tree("Episódios", id="episodes-tree")
        yield Footer()

    def on_mount(self) -> None:
        poster = self.query_one("#anime-poster", Static)
        if self._anime_vm.image:
            ansi = get_image(self._anime_vm.image, max_width=35)
            if ansi:
                poster.update(ansi)

        tree = self.query_one("#episodes-tree", Tree)

        if self._anime_vm.seasons:
            for season in self._anime_vm.seasons:
                season_node = tree.root.add(f"[bold]Temporada {season.number}[/]")
                for ep_vm in season.episodes:
                    leaf = season_node.add_leaf(
                        f"[bold]{ep_vm.number}[/] - {ep_vm.title}"
                    )
                    leaf.data = ep_vm
            tree.root.expand_all()
        else:
            tree.root.add("[yellow]Nenhum episódio encontrado[/]")

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        ep_vm: EpisodeVM | None = event.node.data
        if ep_vm is None:
            return
        self.loading = True
        asyncio.create_task(self._fetch_video(ep_vm))

    async def _fetch_video(self, ep_vm: EpisodeVM) -> None:
        try:
            video_src = await asyncio.to_thread(
                self._service.get_video_src, ep_vm.link, self._source_name
            )
            if not video_src:
                self.loading = False
                self.notify("Fonte de vídeo não encontrada", severity="error")
                return

            if self._on_watch:
                self._on_watch(
                    anime_title=self._anime_vm.title,
                    episode_title=ep_vm.title,
                    episode_number=ep_vm.number,
                    episode_link=ep_vm.link,
                    source_name=self._source_name,
                    anime_image=self._anime_vm.image,
                    source_color=self._source_color,
                )

            start_at = 0.0
            if self._get_progress:
                start_at = float(self._get_progress(ep_vm.link) or 0.0)

            def on_status(msg: str) -> None:
                self.app.call_from_thread(self.notify, msg, timeout=2)

            def on_position(pos: float, dur: float) -> None:
                if self._on_progress:
                    self._on_progress(ep_vm.link, pos, dur)

            ok = await asyncio.to_thread(
                open_video,
                video_src,
                status=on_status,
                start_at=start_at,
                on_position=on_position if self._on_progress else None,
            )
            self.loading = False
            if ok:
                if start_at > 1:
                    self.notify(f"Retomando em {int(start_at)}s", severity="information")
                else:
                    self.notify("Player aberto", severity="information")
            else:
                self.notify("Não foi possível abrir o vídeo", severity="error")
        except Exception as e:
            self.loading = False
            self.notify(f"Erro: {e}", severity="error")
