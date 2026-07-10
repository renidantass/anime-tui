"""Interface TUI (Terminal User Interface) para animes-tui."""

from app.presentation.tui.screens import HistoryScreen, HomeScreen
from app.presentation.tui.view_models.history_vm import HistoryVM

__all__ = ["HistoryScreen", "HistoryVM", "HomeScreen"]
