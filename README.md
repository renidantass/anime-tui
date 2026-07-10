# animes-tui / anishelf

Cliente **TUI** (terminal) e **Web** (navegador) para assistir animes de múltiplas fontes, com histórico, favoritos, player integrado e metadados do AniList.

A interface web — **anishelf** — é a principal forma de uso hoje. Oferece navegação estilo Netflix, busca, catálogo por gênero, calendário de lançamentos, página de detalhes com temporadas, player no navegador com HLS, atalhos de teclado, pulo de abertura/fechamento (AniSkip) e sincronia automática de progresso.

A interface TUI continua disponível para quem prefere o terminal.

---

## Requisitos

- Python ≥ 3.11
- [`uv`](https://docs.astral.sh/uv/) (recomendado) ou `pip`

---

## Instalação rápida

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/renidantass/anime-tui@main/install.sh | bash
```

Isso clona o repositório, gera o binário com PyInstaller e instala em `~/.local/bin/animes-tui`.

Se `~/.local/bin` não estiver no `PATH`:

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

### Instalação local (desenvolvimento)

```bash
git clone https://github.com/renidantass/anime-tui.git
cd anime-tui
uv sync
```

---

## Uso

### Interface Web (recomendado)

```bash
uv run python web_main.py
```

Abra [http://127.0.0.1:8765](http://127.0.0.1:8765).

Opções:

```bash
uv run python web_main.py --host 0.0.0.0 --port 8765
uv run animes-web --reload
```

### Interface TUI (terminal)

```bash
uv run python main.py
# ou
animes-tui
```

---

## Funcionalidades da Web (anishelf)

- **Home** — hero em destaque, fila "Continuar", fila "Favoritos", grade de episódios recém-lançados
- **Busca** — resultados em tempo real por nome de anime
- **Gêneros / Explorar** — navegação por gênero com metadados do AniList
- **Calendário** — lançamentos da semana com opcional cruzamento contra fontes ativas
- **Continuar** — histórico de visualização com progresso salvo, agrupado por anime
- **Favoritos** — salvar animes para assistir depois, acessível da home e página dedicada
- **Detalhes do anime** — sinopse, nota, estúdios, gêneros, banner, temporadas e lista de episódios
- **Player** — vídeo no navegador via HLS.js, com:
  - Pular abertura/fechamento (AniSkip)
  - Controle de velocidade
  - Picture-in-Picture
  - Download do stream
  - Progresso sincronizado automaticamente
  - Atalhos de teclado (`S`, `M`, `←`, `→`, `↑`, `↓`, `F`, `Esc`, `?`)
- **Fontes** — ativar/desativar fontes, verificar saúde (online/offline), fallback automático entre fontes
- **Proxy de imagens** — posters carregados via backend para evitar bloqueios de CORS/referer

---

## Arquitetura

- **Backend** — FastAPI com rotas REST (`/api/*`)
- **Frontend** — JavaScript vanilla com ES modules, sem framework externo
- **Metadados** — AniList GraphQL API (sinopse, capa, nota, gêneros, temporada, franquia)
- **Skip times** — AniSkip API proxy via backend
- **Stream** — resolução de links, HLS proxy, suporte a Blogger/BloggerPlayer
- **Persistência** — JSON local:
  - `~/.anime-feed-reader/watch_history.json` — histórico e progresso
  - `~/.anime-feed-reader/watch_later.json` — favoritos
  - `~/.config/animes-tui/` — configuração de fontes
  - `~/.cache/animes-tui/` — cache de imagens e vídeos

---

## API REST

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/health` | Health check |
| `GET /api/episodes` | Episódios recém-lançados das fontes ativas |
| `GET /api/search?q=` | Busca por nome |
| `GET /api/genres` | Lista de gêneros do AniList |
| `GET /api/genres/catalog` | Catálogo por gênero (com metadados) |
| `GET /api/genres/browse` | Browse paginado por gênero |
| `GET /api/calendar` | Calendário de lançamentos |
| `GET /api/anime?link=` | Detalhes e episódios de uma fonte |
| `POST /api/play` | Resolve link de stream para um episódio |
| `GET /api/skip-times` | Timestamps de OP/ED (AniSkip) |
| `GET /api/history` | Histórico de visualização |
| `POST /api/history` | Adicionar entrada ao histórico |
| `GET /api/watch-later` | Lista de favoritos |
| `POST /api/watch-later` | Adicionar aos favoritos |
| `DELETE /api/watch-later/{title}` | Remover dos favoritos |
| `GET /api/sources` | Fontes disponíveis e status |
| `GET /api/image?url=` | Proxy de imagem |

---

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
- `~/.anime-feed-reader/` — histórico de visualização e favoritos

---

## Desenvolvimento

```bash
uv sync                    # instala dependências
uv run python web_main.py  # modo web
uv run python main.py      # modo TUI
uv run pytest              # testes
uv run ruff check .        # linter
uv run mypy .              # type check
```

---

## Licença

MIT
