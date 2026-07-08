# Phase 03: UI Polish & Enhanced Features

This phase polishes the TUI with a help overlay, search improvements, better error handling, and performance optimizations. It refines the user experience with smoother navigation, visual feedback, and reduced friction.

## Tasks

- [x] Create a keyboard help overlay screen:
  - New file `app/presentation/screens/help_screen.py`
  - Shows all keyboard bindings grouped by screen (Home, Search, Anime Detail, Watchlist, History)
  - Rendered as a `RichTable` or formatted `Static` with sections
  - Binding: `("escape", "dismiss", "Fechar")`
  - Add `("h", "help", "Ajuda")` binding to all main screens (HomeScreen, SearchScreen, AnimeDetailScreen, WatchlistScreen, HistoryScreen)
  - Register in `app/presentation/screens/__init__.py`

- [x] Add search debounce to `SearchScreen`:
  - Instead of searching on Enter immediately, use `textual`'s `Timer` or `set_interval` to debounce 300ms after the last keystroke
  - Auto-trigger search as the user types (remove the need to press Enter)
  - Show previous searches from history as suggestions when search input is focused but empty

- [ ] Improve error handling across all screens:
  - In `HomeScreen._initial_load` and `_load_episodes`: add retry logic (retry up to 2 times with 2s delay for network errors)
  - In `SearchScreen._search`: wrap in try/except and show meaningful Portuguese error messages
  - In `AnimeDetailScreen._fetch_video`: show `self.app.notify("[red]✗ Erro ao carregar vídeo[/]")` on failure
  - Add a global exception handler in `main.py` that logs unhandled exceptions to `~/.animes-tui/error.log`

- [ ] Add connection timeout management:
  - In `AnimeService`, add a `timeout: int = 10` parameter (seconds) for all scraper HTTP requests
  - Create `app/infrastructure/sources/_http.py` that provides a shared `requests.Session` with default timeout, user-agent, and retry adapter
  - Update all scrapers (`animesonlinecc.py`, `topanimes.py`, `goyabu.py`) to use the shared session from `_http.py` instead of creating their own `requests.get` calls

- [ ] Performance optimization pass:
  - Audit `image_cache.py`: add LRU eviction with `maxsize=200` using `@functools.lru_cache` or a `collections.OrderedDict`
  - In `SourceDiscovery`, move HTTP availability checks to be fully async (use `asyncio.to_thread` or `aiohttp`) to avoid blocking the UI during source initialization
  - Add `functools.lru_cache(maxsize=5)` to `AnimeService.get_anime_details` to avoid re-fetching recently viewed anime details

- [ ] Visual polish pass:
  - Review all screens for consistent styling (colors, spacing, borders)
  - Add a subtle border/panel around the "Continue Watching" section in HomeScreen
  - Add emoji-free visual indicators: use `▶` for play, `★` for watchlist, `⏎` for history
  - Ensure all `DEFAULT_CSS` is consistent and uses the same color palette

- [ ] Final integration verification:
  - Run `python main.py` and exercise all screens
  - Test all keyboard shortcuts across every screen
  - Verify help overlay shows accurate bindings
  - Test search with debounce (type quickly, confirm only one search fires)
  - Verify error messages appear correctly when sources are unreachable
  - Run `ruff check .` to confirm zero linting errors
