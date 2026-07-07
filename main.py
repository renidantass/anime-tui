from app.presentation.screens import HomeScreen
from textual.app import App


class AnimeTUI(App):
    BINDINGS = [("q", "quit", "Sair")]

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())

    def action_quit(self) -> None:
        self.exit()


def main():
    app = AnimeTUI()
    app.run()


if __name__ == "__main__":
    main()
