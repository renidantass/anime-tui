import webbrowser

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Tree

from app.application import get_video_src
from app.presentation.utils.image_cache import get_image
from app.presentation.view_models import AnimeVM, EpisodeVM


class AnimeDetailScreen(Screen):
    BINDINGS = [("escape", "back", "Voltar")]

    def __init__(self, anime_vm: AnimeVM, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._anime_vm = anime_vm

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"[bold]{self._anime_vm.title}[/]", id="anime-title")
        yield Static(id="anime-poster")
        yield Tree("Episódios", id="episodes-tree")
        yield Footer()

    def on_mount(self) -> None:
        poster = self.query_one("#anime-poster", Static)
        if self._anime_vm.image:
            ansi = get_image(self._anime_vm.image, max_width=60)
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
        try:
            video_src = get_video_src(ep_vm.link)
            if video_src:
                webbrowser.open(video_src)
        except Exception:
            pass
