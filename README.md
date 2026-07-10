# animes-tui

Cliente TUI para assistir animes no terminal.

## Instalação rápida

Requisitos: `git`, [`uv`](https://docs.astral.sh/uv/) e Python ≥ 3.11.

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/renidantass/anime-tui@main/install.sh | bash
```

Isso clona o repositório, gera o binário com PyInstaller e instala em `~/.local/bin/animes-tui`.

Depois rode:

```bash
animes-tui
```

Se `~/.local/bin` não estiver no `PATH`, adicione no `~/.bashrc` (ou equivalente):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Opções de instalação

| Comando | Efeito |
|--------|--------|
| `./install.sh` | Build + instala em `~/.local/bin` |
| `./install.sh --build-only` | Só gera o binário em `dist/` |
| `./install.sh --install-only` | Instala o binário já existente em `dist/` |
| `./install.sh --prefix ~/bin` | Instala em outro diretório |

### Instalação local (já clonou o repo)

```bash
git clone https://github.com/renidantass/anime-tui.git
cd anime-tui
./install.sh
```

## Desinstalação

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/renidantass/anime-tui@main/uninstall.sh | bash
```

Ou, no repositório:

```bash
./uninstall.sh
```

| Comando | Efeito |
|--------|--------|
| `./uninstall.sh` | Remove o binário de `~/.local/bin` |
| `./uninstall.sh --prefix ~/bin` | Remove de outro diretório |
| `./uninstall.sh --purge` | Remove binário + config, cache e histórico |

Dados preservados sem `--purge`:

- `~/.config/animes-tui/` — configuração
- `~/.cache/animes-tui/` — cache de vídeos
- `~/.anime-feed-reader/` — histórico de visualização

### Desenvolvimento (sem binário)

```bash
uv sync
uv run python main.py
```

## Interface Web (estilo Netflix)

Além do TUI, há uma UI web escura com hero, carrosséis, busca, histórico e player no navegador.

```bash
uv sync
uv run python web_main.py
```

Abra [http://127.0.0.1:8765](http://127.0.0.1:8765).

Opções:

```bash
uv run python web_main.py --host 0.0.0.0 --port 8765
uv run animes-web --reload   # se o script estiver instalado no ambiente
```

A API REST fica em `/api/*` (episódios, busca, play, proxy de stream, histórico e fontes). O histórico é o mesmo arquivo do TUI (`~/.anime-feed-reader/watch_history.json`).
