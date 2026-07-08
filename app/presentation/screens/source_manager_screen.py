from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Checkbox, RadioSet, RadioButton

from app.application.anime_service import AnimeService
from app.infrastructure.config import (
    PLAYER_AUTO,
    PLAYER_BROWSER,
    PLAYER_GSTREAMER,
    PLAYER_LABELS,
    PLAYER_MPV,
    PLAYER_VLC,
    Config,
    load as load_config,
    save as save_config,
)
from app.infrastructure.player import is_player_available

_PLAYER_OPTIONS = (
    PLAYER_AUTO,
    PLAYER_MPV,
    PLAYER_VLC,
    PLAYER_GSTREAMER,
    PLAYER_BROWSER,
)

_INSTALL_HINT = {
    PLAYER_MPV: "sudo apt install mpv",
    PLAYER_VLC: "sudo apt install vlc",
    PLAYER_GSTREAMER: "sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good",
}


class SourceManagerScreen(Screen):
    """Opções: fontes habilitadas e player padrão de vídeo."""

    DEFAULT_CSS = """
    #sources-container {
        height: auto;
        margin-bottom: 1;
    }
    #player-section {
        height: auto;
        border-top: solid $primary;
        padding-top: 1;
        margin-top: 1;
    }
    #player-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    #player-radios {
        height: auto;
        width: 100%;
        margin: 0 1 1 1;
        background: transparent;
        border: none;
    }
    #player-radios > RadioButton {
        width: 100%;
        margin: 0 0 0 0;
    }
    #player-status {
        margin: 0 1 1 1;
    }
    """

    BINDINGS = [("escape", "back", "Voltar")]

    def __init__(self, service: AnimeService, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service
        self._config: Config = load_config()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[bold]Opções[/]", id="title")
        yield Static("[bold]Fontes[/]", id="sources-heading")
        with Vertical(id="sources-container"):
            for entry in self._service.get_all_source_entries():
                avail = self._service.is_source_available(entry.identifier)
                status = "[white on #27ae60] ONLINE [/]" if avail else "[white on #c0392b] OFFLINE [/]"
                label = f"{entry.name} {status}"
                if not avail and entry.error:
                    label += f" [dim]({entry.error})[/]"
                yield Checkbox(
                    label=label,
                    value=self._service.is_enabled(entry.identifier),
                    disabled=not avail,
                    id=f"source-{entry.identifier}",
                )

        with Vertical(id="player-section"):
            yield Static("[bold]Player de vídeo[/]", id="player-title")
            yield Static(
                "[dim]Escolha o player padrão. mpv, VLC e GStreamer precisam estar instalados.[/]",
                id="player-hint",
            )
            with RadioSet(id="player-radios"):
                for key in _PLAYER_OPTIONS:
                    available = is_player_available(key)
                    if key in (PLAYER_BROWSER, PLAYER_AUTO):
                        suffix = (
                            ""
                            if key == PLAYER_BROWSER or available
                            else " [dim](nenhum detectado)[/]"
                        )
                    else:
                        suffix = "" if available else " [red](não instalado)[/]"
                    label = f"{PLAYER_LABELS[key]}{suffix}"
                    yield RadioButton(
                        label,
                        value=(self._config.player == key),
                        id=f"player-{key}",
                    )
            yield Static(self._player_status_text(), id="player-status")

        yield Footer()

    def _player_status_text(self) -> str:
        p = self._config.player
        label = PLAYER_LABELS.get(p, p)
        if p not in (PLAYER_AUTO, PLAYER_BROWSER) and not is_player_available(p):
            return f"[yellow]Padrão: {label} — instale o pacote para usar[/]"
        return f"[green]Padrão: {label}[/]"

    def action_back(self) -> None:
        self.dismiss()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        cb_id = event.checkbox.id or ""
        if not cb_id.startswith("source-"):
            return
        identifier = cb_id[len("source-"):]
        self._service.set_enabled(identifier, event.checkbox.value)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        pressed = event.pressed
        if pressed is None:
            return
        btn_id = pressed.id or ""
        if not btn_id.startswith("player-"):
            return
        player = btn_id[len("player-"):]
        self._config.player = player
        save_config(self._config)
        try:
            self.query_one("#player-status", Static).update(self._player_status_text())
        except Exception:
            pass
        if player not in (PLAYER_AUTO, PLAYER_BROWSER) and not is_player_available(player):
            hint = _INSTALL_HINT.get(player, f"instale {player}")
            self.notify(
                f"{PLAYER_LABELS.get(player, player)} não está instalado. {hint}",
                severity="warning",
                timeout=5,
            )
        else:
            self.notify(f"Player padrão: {PLAYER_LABELS.get(player, player)}", timeout=2)
