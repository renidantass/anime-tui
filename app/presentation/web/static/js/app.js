/**
 * anishelf — UI web pensada pra quem assiste anime
 */

import { api, imgUrl } from "./api.js";
import { initPlayer, openPlayer, closePlayer } from "./player.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const PLACEHOLDER_POSTER =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="300" viewBox="0 0 200 300">' +
    '<rect width="100%" height="100%" fill="#090a12"/>' +
    '<line x1="0" y1="0" x2="200" y2="300" stroke="#00f0ff" stroke-width="0.5" opacity="0.15"/>' +
    '<line x1="200" y1="0" x2="0" y2="300" stroke="#00f0ff" stroke-width="0.5" opacity="0.15"/>' +
    '<rect x="20" y="20" width="160" height="260" fill="none" stroke="#00f0ff" stroke-width="1" stroke-dasharray="4,4" opacity="0.25"/>' +
    '<text x="50%" y="48%" dominant-baseline="middle" text-anchor="middle" font-family="monospace" font-size="10" fill="#ff0055" font-weight="bold" letter-spacing="2">[ NO SIGNAL ]</text>' +
    '<text x="50%" y="56%" dominant-baseline="middle" text-anchor="middle" font-family="monospace" font-size="8" fill="#00f0ff" opacity="0.7">SIGNAL LOST</text>' +
    "</svg>"
  );

const state = {
  episodes: [],
  history: [],
  heroItem: null,
  detail: null,
  detailMeta: null,
  /** map epNumber -> { title, thumbnail } da AniList */
  detailEpisodeMeta: {},
  detailSources: [],
  detailPreferred: "",
  detailLink: "",
  detailSeq: 0,
  searchTimer: null,
  route: "home",
  /** Catálogo precisa ser buscado de novo (ex.: fontes mudaram). */
  catalogDirty: true,
  loadingCatalog: false,
  /** Reload do catálogo agendado após mudança de fontes. */
  catalogReloadSeq: 0,
  /** Gêneros AniList { id, name, label }. */
  genres: [],
  selectedGenre: "",
  genreItems: [],
  genreCatalog: [],
  genreLoading: false,
  genreSeq: 0,
  /** pick = escolher gênero; results = lista de animes */
  genreStep: "pick",
  /** Cache client: genre → { items, at } */
  genreCache: {},
  /** Paginação */
  genrePage: 1,
  genreHasNext: false,
  genreCurrentGenre: "",
  /** Calendário de lançamentos */
  calendarDays: 7,
  /** Cruzar episódios com fontes (desligado por padrão — mais rápido) */
  calendarCheckSources: false,
  calendarItems: [],
  calendarLoading: false,
  calendarCache: null,
};

// ── Toast ────────────────────────────────────────────────────────────────────

let toastTimer;
function toast(msg, isError = false) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 3200);
}

// ── Routing ──────────────────────────────────────────────────────────────────

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "") || "home";
  const [path, ...rest] = h.split("?");
  const params = new URLSearchParams(rest.join("?") || "");
  return { path, params };
}

function navigate(path) {
  location.hash = `#/${path}`;
}

function setActiveNav(route) {
  $$(".rail-link, .nav-link").forEach((a) => {
    a.classList.toggle("active", a.dataset.nav === route);
  });
}

function setTopbar(eyebrow, title) {
  const e = $("#topbar-eyebrow");
  const t = $("#topbar-title");
  if (e) {
    e.textContent = eyebrow || "";
    e.hidden = !eyebrow;
  }
  if (t) t.textContent = title || "";
}

function showView(id) {
  $$(".view").forEach((v) => {
    v.hidden = v.id !== id;
  });
}

async function onRoute() {
  const { path, params } = parseHash();
  closeSearch(false);

  if (path.startsWith("anime")) {
    const link = params.get("link") || "";
    const source = params.get("source") || "";
    const al = params.get("al") || "";
    const titleHint = params.get("title") || "";
    state.route = "detail";
    setActiveNav("home");
    setTopbar("", "Detalhes");
    showView("view-detail");
    await loadDetail(link, source, {
      anilistId: al ? Number(al) : null,
      titleHint,
    });
    return;
  }

  if (path === "genres" || path === "explore") {
    state.route = "genres";
    setActiveNav("genres");
    setTopbar("", "Gêneros");
    showView("view-genres");
    await loadGenresPage();
    return;
  }

  if (path === "calendar") {
    state.route = "calendar";
    setActiveNav("calendar");
    setTopbar("", "Calendário");
    showView("view-calendar");
    await loadCalendarPage();
    return;
  }

  if (path === "history") {
    state.route = "history";
    setActiveNav("history");
    setTopbar("", "Continuar");
    showView("view-history");
    await loadHistoryPage();
    return;
  }

  if (path === "sources") {
    state.route = "sources";
    setActiveNav("sources");
    setTopbar("", "Fontes");
    showView("view-sources");
    await loadSources();
    return;
  }

  state.route = "home";
  setActiveNav("home");
  setTopbar("", "Início");
  showView("view-home");
  if (state.catalogDirty || !state.episodes.length) {
    await loadHome();
  } else {
    await renderContinueRow();
  }
}

// ── Cards ────────────────────────────────────────────────────────────────────

function pillHtml(sources) {
  const seen = new Set();
  const unique = [];
  for (const s of sources || []) {
    const name = s?.name || "";
    if (!name || seen.has(name)) continue;
    seen.add(name);
    unique.push(s);
    if (unique.length >= 3) break;
  }
  return unique
    .map((s) => {
      const color = s.color || "#666";
      return `<span class="source-pill" style="--pill:${color}" data-color>${escapeHtml(s.name)}</span>`;
    })
    .join("");
}

/**
 * Badge quando dublado + legendado estão disponíveis.
 * @param {"poster"|"inline"|"cal"} [place="inline"]
 */
function audioChoiceBadge(sources, place = "inline") {
  if (!hasAudioChoice(sources)) return "";
  const title = "Dublado e legendado disponíveis — toque para escolher";
  if (place === "poster") {
    return `
      <span class="card-audio-badge" title="${title}">
        <i class="card-audio-pill is-leg">LEG</i>
        <i class="card-audio-pill is-dub">DUB</i>
      </span>`;
  }
  if (place === "cal") {
    return `
      <span class="cal-badge cal-badge-audio" title="${title}">
        <i class="card-audio-pill is-leg">LEG</i>
        <i class="card-audio-pill is-dub">DUB</i>
      </span>`;
  }
  return "";
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function playIcon(size = 16) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>`;
}

function posterStyle(url) {
  if (!url) return "";
  return `background-image:url('${url}')`;
}

function skeletonShelf(count = 8) {
  return Array.from({ length: count }, (_, i) => `
    <article class="skel-card" style="animation-delay:${(i * 0.04).toFixed(2)}s">
      <div class="skel-card-poster"></div>
      <div class="skel-card-body">
        <div class="skel-line skel-line--mid"></div>
        <div class="skel-line skel-line--narrow"></div>
      </div>
    </article>
  `).join("");
}

function episodeCard(item, { progressRatio } = {}) {
  const poster = imgUrl(item.image);
  const progress =
    progressRatio > 0.02 && progressRatio < 0.95
      ? `<div class="card-progress"><i style="width:${Math.round(progressRatio * 100)}%"></i></div>`
      : "";
  const links = (item.sources || []).map((s) => s.link).filter(Boolean);
  const labels = normalizeWatchTitles(
    item.title,
    item.title,
    resolveEpisodeNumber(item.number, item.title, ...links)
  );
  const corner =
    labels.number && labels.number !== "?"
      ? `<span class="card-ep-corner">${escapeHtml(formatEpLabel(labels.number))}</span>`
      : "";

  const el = document.createElement("article");
  el.className = "card" + (hasAudioChoice(item.sources) ? " has-audio-choice" : "");
  const imgSrc = poster || PLACEHOLDER_POSTER;
  el.innerHTML = `
    <div class="card-poster has-img">
      <img class="card-poster-img" src="${imgSrc}" alt="" loading="lazy" onerror="this.onerror=null; this.src='${PLACEHOLDER_POSTER}';" />
      ${corner}
      ${audioChoiceBadge(item.sources, "poster")}
      <div class="card-play">
        <button type="button" class="btn-play-sm" aria-label="Assistir">${playIcon(18)}</button>
      </div>
      ${progress}
    </div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(labels.animeTitle || item.title)}</div>
      <div class="card-meta">
        ${pillHtml(item.sources)}
      </div>
    </div>
  `;
  el.addEventListener("click", (e) => {
    e.preventDefault();
    onEpisodeClick(item);
  });
  return el;
}

function animeCard(item) {
  const poster = imgUrl(item.image);
  const score =
    item.rating ||
    (item.score != null ? (item.score / 10).toFixed(1) : "");
  const metaBits = [
    item.season_line || (item.year ? String(item.year) : ""),
    item.format_label || "",
    item.status_label || "",
    item.episodes ? `${item.episodes} eps` : "",
  ].filter(Boolean);
  const el = document.createElement("article");
  el.className = "card" + (hasAudioChoice(item.sources) ? " has-audio-choice" : "");
  const imgSrc = poster || PLACEHOLDER_POSTER;
  el.innerHTML = `
    <div class="card-poster has-img">
      <img class="card-poster-img" src="${imgSrc}" alt="" loading="lazy" onerror="this.onerror=null; this.src='${PLACEHOLDER_POSTER}';" />
      ${audioChoiceBadge(item.sources, "poster")}
      <div class="card-play">
        <button type="button" class="btn-play-sm" aria-label="Abrir">${playIcon(18)}</button>
      </div>
    </div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(stripTitleVariants(item.title) || item.title)}</div>
      <div class="card-meta">
        ${score ? `<span class="ep-badge">★ ${escapeHtml(String(score))}</span>` : ""}
        ${audioChoiceBadge(item.sources, "inline")}
        ${pillHtml(item.sources)}
      </div>
      ${
        metaBits.length
          ? `<div class="card-meta-line">${metaBits
              .map((b) => `<span class="meta-mini">${escapeHtml(b)}</span>`)
              .join("<span class='meta-mini'>·</span>")}</div>`
          : ""
      }
    </div>
  `;
  el.addEventListener("click", () => onAnimeClick(item));
  return el;
}

function openAnimeFromSource(item, src) {
  if (!src?.link) {
    toast("Este item não tem link de detalhes", true);
    return;
  }
  const q = [
    `link=${encodeURIComponent(src.link)}`,
    `source=${encodeURIComponent(src.name || "")}`,
  ];
  if (item.anilist_id) q.push(`al=${encodeURIComponent(item.anilist_id)}`);
  const title = stripTitleVariants(item.title) || item.title;
  if (title) q.push(`title=${encodeURIComponent(title)}`);
  navigate(`anime?${q.join("&")}`);
}

function onAnimeClick(item) {
  const sources = (item.sources || []).filter((s) => s?.link);
  if (!sources.length) {
    toast("Este item não tem link de detalhes", true);
    return;
  }
  // Dublado + Legendado → menu; senão abre direto (1ª fonte)
  if (hasAudioChoice(sources)) {
    openAudioChoiceModal(item.title, sources, (picked) => {
      openAnimeFromSource(item, picked[0]);
    });
    return;
  }
  openAnimeFromSource(item, sources[0]);
}

function historyCard(item) {
  const poster = imgUrl(item.anime_image);
  const ratio = item.progress_ratio || 0;
  const progress =
    ratio > 0.02
      ? `<div class="card-progress"><i style="width:${Math.round(ratio * 100)}%"></i></div>`
      : "";
  const labels = normalizeWatchTitles(
    item.anime_title,
    item.episode_title,
    item.episode_number
  );
  const corner =
    labels.number && labels.number !== "?"
      ? `<span class="card-ep-corner">${escapeHtml(formatEpLabel(labels.number))}</span>`
      : "";
  const el = document.createElement("article");
  el.className = "card";
  const imgSrc = poster || PLACEHOLDER_POSTER;
  el.innerHTML = `
    <div class="card-poster has-img">
      <img class="card-poster-img" src="${imgSrc}" alt="" loading="lazy" onerror="this.onerror=null; this.src='${PLACEHOLDER_POSTER}';" />
      ${corner}
      <div class="card-play">
        <button type="button" class="btn-play-sm" aria-label="Continuar">${playIcon(18)}</button>
      </div>
      ${progress}
    </div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(labels.animeTitle)}</div>
      <div class="card-meta">
        <span class="ep-badge">${escapeHtml(labels.episodeLine)}</span>
        ${item.source_name ? `<span class="source-pill">${escapeHtml(item.source_name)}</span>` : ""}
      </div>
    </div>
  `;
  el.addEventListener("click", () => playFromHistory(item));
  return el;
}

// ── Home ─────────────────────────────────────────────────────────────────────

let _sourcesReadyPromise = null;

async function waitSourcesReady() {
  if (_sourcesReadyPromise) return _sourcesReadyPromise;
  _sourcesReadyPromise = (async () => {
    const maxMs = 45000;
    const start = Date.now();
    while (Date.now() - start < maxMs) {
      try {
        const h = await api.health();
        if (h.sources_ready) return;
      } catch {
        /* retry */
      }
      await sleep(400);
    }
  })();
  return _sourcesReadyPromise;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function hasAnyEnabledSource() {
  try {
    const data = await api.sources();
    return (data.items || []).some((s) => s.enabled);
  } catch {
    return true; // em caso de erro, assume que há fontes para não bloquear
  }
}

async function loadHome({ silent = false } = {}) {
  const seq = ++state.catalogReloadSeq;
  state.loadingCatalog = true;
  state.catalogDirty = true;

  // Se o hero estava em modo onboarding, restaura a estrutura original
  // para que renderHero() encontre #hero-title, #hero-bg etc.
  restoreHeroStructure();

  const scroller = $("#episodes-scroller");
  if (scroller) {
    scroller.innerHTML = skeletonShelf(4);
  }
  try {
    await waitSourcesReady();
    const data = await api.episodes();
    if (seq !== state.catalogReloadSeq) return;
    state.episodes = data.items || [];
    state.catalogDirty = false;

    // Sort episodes newest first for consistent ordering
    state.episodes.sort((a, b) => {
      const da = a.date || ""; const db = b.date || "";
      if (da && db) return db.localeCompare(da);
      if (da) return -1; if (db) return 1;
      // Fallback: sort by number desc if available
      const na = parseFloat(a.number) || 0;
      const nb = parseFloat(b.number) || 0;
      return nb - na;
    });

    // Se não há episódios, verificar se é por falta de fontes ativas
    if (!state.episodes.length) {
      const anyEnabled = await hasAnyEnabledSource();
      if (!anyEnabled) {
        showNoSourcesOnboarding();
        if (count) count.textContent = "0";
        return;
      }
    }

    renderHero();
    renderEpisodesRow();
    await renderContinueRow();
  } catch (e) {
    if (seq !== state.catalogReloadSeq) return;
    toast(e.message || "Não foi possível carregar", true);
    if (scroller) {
      scroller.innerHTML = `<div class="empty-state"><strong>Não carregou</strong>Confira a internet e as fontes ativas.</div>`;
    }
    if (count) count.textContent = "0";
  } finally {
    if (seq === state.catalogReloadSeq) {
      state.loadingCatalog = false;
    }
  }
}

function restoreHeroStructure() {
  const viewHome = $("#view-home");
  if (!viewHome || !viewHome.querySelector(".onboarding-hero")) return;

  // Restaura o .home-layout original no lugar do onboarding
  viewHome.innerHTML = `
    <div class="home-layout">
      <article class="spotlight" id="hero">
        <div class="spotlight-art" id="hero-bg"></div>
        <div class="spotlight-shade"></div>
        <div class="spotlight-body">
          <span class="tag tag-hot" id="hero-badge">Em destaque</span>
          <h2 class="spotlight-title" id="hero-title">Carregando…</h2>
          <p class="spotlight-meta" id="hero-meta"></p>
          <p class="spotlight-desc" id="hero-desc"></p>
          <div class="spotlight-actions">
            <button type="button" class="btn btn-accent" id="hero-play">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              Assistir
            </button>
            <button type="button" class="btn btn-ghost" id="hero-info">Outras fontes</button>
          </div>
        </div>
        <div class="spotlight-hud-code">SYS-DECK // SEC-A</div>
      </article>

      <section class="queue-panel" id="row-continue" hidden>
        <div class="section-head">
          <div><h3>Continuar</h3></div>
          <a href="#/history" class="section-link">Ver tudo →</a>
        </div>
        <div class="queue-scroller" id="continue-scroller"></div>
      </section>

      <section class="shelf-section">
        <div class="section-head">
          <div><h3>Recém-lançados</h3></div>
          <span class="count-pill" id="episodes-count">—</span>
        </div>
        <div class="shelf-grid" id="episodes-scroller"></div>
      </section>
    </div>
  `;

  // Rebinda os eventos do hero
  $("#hero-play")?.addEventListener("click", () => {
    if (state.heroItem) onEpisodeClick(state.heroItem);
  });
  $("#hero-info")?.addEventListener("click", () => {
    const item = state.heroItem;
    if (!item) return;
    const sources = (item.sources || []).filter((s) => s?.link);
    if (hasAudioChoice(sources)) {
      openAudioChoiceModal(item.title, sources, (picked) => {
        if (picked.length > 1) {
          openSourceModal(item.title, picked, (src) => playEpisodeFromSources(item, [src]));
          return;
        }
        playEpisodeFromSources(item, picked);
      });
      return;
    }
    if (sources.length > 1) {
      openSourceModal(item.title, sources, (src) => playEpisodeFromSources(item, [src]));
      return;
    }
    // Single source — show it as the only option instead of auto-playing
    openSourceModal(item.title, sources, (src) => playEpisodeFromSources(item, [src]));
  });
}

function showNoSourcesOnboarding() {
  const viewHome = $("#view-home");
  if (!viewHome) return;

  // Substitui o .home-layout inteiro por uma tela centralizada
  // (evita ficar preso nas restrições de grid do .spotlight)
  viewHome.innerHTML = `
    <div class="onboarding-hero">
      <div class="onboarding-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="6" rx="7" ry="2.5"/>
          <path d="M5 6v4c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6"/>
          <path d="M5 10v4c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-4"/>
          <path d="M5 14v4c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-4"/>
        </svg>
      </div>
      <h2 class="onboarding-title">Nenhuma fonte ativa</h2>
      <p class="onboarding-desc">
        Escolha pelo menos uma fonte para começar a ver os episódios disponíveis.
      </p>
      <a href="#/sources" class="btn btn-accent onboarding-cta">
        Configurar fontes
      </a>
      <p class="onboarding-hint">Você pode ativar e desativar fontes a qualquer momento nas configurações.</p>
    </div>
  `;
}


/** Após mudar fontes: recarrega catálogo (e busca aberta, se houver). */
async function reloadAfterSourcesChange() {
  // cache de gênero depende das fontes ativas
  state.genreCache = {};
  await loadHome({ silent: true });
  if (state.route === "genres" && state.selectedGenre) {
    await loadGenreBrowse(state.selectedGenre, { silent: true, force: true });
  }
  const q = $("#search-input")?.value?.trim();
  if (q && q.length >= 2 && !$("#search-overlay")?.hidden) {
    await runSearch(q);
  }
}

// ── Gêneros (passo 1: escolher · passo 2: resultados) ────────────────────────

const GENRE_CACHE_MS = 8 * 60 * 1000;

/** Ordem dos gêneros “populares” no passo 1 (ids AniList). */
const GENRE_POPULAR_ORDER = [
  "Action",
  "Adventure",
  "Comedy",
  "Drama",
  "Fantasy",
  "Romance",
  "Sci-Fi",
  "Slice of Life",
  "Horror",
  "Mystery",
  "Sports",
  "Supernatural",
];

async function loadGenresPage() {
  // volta ao passo 1 se ainda não escolheu / não está carregando resultados
  if (!state.selectedGenre) {
    setGenreStep("pick");
  }
  try {
    await waitSourcesReady();
    await loadGenresIfNeeded();

    if (state.selectedGenre) {
      setGenreStep("results");
      const cached = state.genreCache[state.selectedGenre];
      if (cached?.items?.length && !state.genreLoading) {
        showGenreLoading(false);
        setExploreHead(genreLabel(state.selectedGenre), "Nas suas fontes");
        renderGenreAvailable(cached.items, {
          label: genreLabel(state.selectedGenre),
          animated: false,
        });
        return;
      }
      if (!state.genreLoading) {
        await loadGenreBrowse(state.selectedGenre, { silent: true });
      }
    } else {
      setGenreStep("pick");
      showGenreLoading(false);
    }
  } catch {
    setGenreStep("pick");
    showGenreLoading(false);
  }
}

async function loadGenresIfNeeded() {
  if (state.genres.length) {
    renderGenrePickers();
    return state.genres;
  }
  const grid = $("#genre-grid");
  if (grid) {
    grid.innerHTML = Array.from(
      { length: 6 },
      () => `<div class="skel-card" style="min-height:5.8rem;border-radius:var(--radius)">
        <div class="skel-card-poster" style="aspect-ratio:auto;height:100%;position:absolute;inset:0"></div>
        <div style="position:relative;z-index:1;padding:1rem;display:flex;flex-direction:column;justify-content:space-between;height:100%;min-height:5.8rem">
          <div class="skel-line" style="width:50%"></div>
          <div class="skel-line skel-line--narrow"></div>
        </div>
      </div>`
    ).join("");
  }
  try {
    const data = await api.genres();
    state.genres = data.items || [];
    renderGenrePickers();
    return state.genres;
  } catch (e) {
    if (popular) {
      popular.innerHTML = `<div class="empty-state" style="grid-column:1/-1">Não deu para carregar os gêneros.</div>`;
    }
    return [];
  }
}

function splitGenres() {
  const byId = new Map(
    (state.genres || []).map((g) => [g.id || g.name, g])
  );
  const popular = [];
  const used = new Set();
  for (const id of GENRE_POPULAR_ORDER) {
    const g = byId.get(id);
    if (g) {
      popular.push(g);
      used.add(id);
    }
  }
  // se a API trouxe poucos dos “populares”, completa com o resto
  if (popular.length < 8) {
    for (const g of state.genres) {
      const id = g.id || g.name;
      if (used.has(id)) continue;
      popular.push(g);
      used.add(id);
      if (popular.length >= 12) break;
    }
  }
  const others = state.genres.filter((g) => !used.has(g.id || g.name));
  return { popular, others };
}

function renderGenrePickers() {
  // All genres in a single grid, popular first then the rest
  const { popular, others } = splitGenres();
  fillGenreGrid($("#genre-grid"), [...popular, ...others], { showGo: true });
}

const GENRE_HUD_GRAPHICS = {
  action: {
    color: "#ff0055",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><line x1='0' y1='0' x2='100' y2='100' stroke='%23ff0055' stroke-width='0.5' opacity='0.3'/><circle cx='50' cy='50' r='30' fill='none' stroke='%23ff0055' stroke-dasharray='4,2'/><circle cx='50' cy='50' r='5' fill='%23ff0055'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 2v20M2 12h20"/></svg>`
  },
  adventure: {
    color: "#00f0ff",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><path d='M10,90 L50,20 L90,90 Z' fill='none' stroke='%2300f0ff' stroke-width='0.8'/><circle cx='50' cy='35' r='10' fill='none' stroke='%2300f0ff' stroke-dasharray='2,2'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M16.2 7.8l-2 6.3-6.4 2 2-6.3z"/></svg>`
  },
  fantasy: {
    color: "#8b5cf6",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><polygon points='50,10 60,40 90,50 60,60 50,90 40,60 10,50 40,40' fill='none' stroke='%238b5cf6' stroke-width='0.8'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`
  },
  scifi: {
    color: "#00ff66",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><rect x='20' y='20' width='60' height='60' fill='none' stroke='%2300ff66' stroke-width='0.8'/><line x1='20' y1='50' x2='80' y2='50' stroke='%2300ff66' stroke-width='0.5'/><line x1='50' y1='20' x2='50' y2='80' stroke='%2300ff66' stroke-width='0.5'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><path d="M8 21h8M12 17v4M6 8l3 3-3 3"/></svg>`
  },
  romance: {
    color: "#ff4b82",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><path d='M12,30 A15,15 0 0,1 50,30 A15,15 0 0,1 88,30 Q90,60 50,90 Q10,60 12,30 Z' fill='none' stroke='%23ff4b82' stroke-width='0.8'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`
  },
  drama: {
    color: "#a3aed0",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><path d='M10,50 Q30,10 50,50 T90,50' fill='none' stroke='%23a3aed0' stroke-width='0.8'/><line x1='0' y1='50' x2='100' y2='50' stroke='%23a3aed0' stroke-width='0.3' stroke-dasharray='2,2'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M16 16s-1.5-2-4-2-4 2-4 2M9 9h.01M15 9h.01"/></svg>`
  },
  mystery: {
    color: "#ffb800",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><circle cx='45' cy='45' r='20' fill='none' stroke='%23ffb800' stroke-width='0.8'/><line x1='59' y1='59' x2='85' y2='85' stroke='%23ffb800' stroke-width='1.5'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/></svg>`
  },
  comedy: {
    color: "#eab308",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='35' fill='none' stroke='%23eab308' stroke-width='0.8'/><path d='M30,60 Q50,80 70,60' fill='none' stroke='%23eab308' stroke-width='1.2'/><circle cx='40' cy='40' r='3' fill='%23eab308'/><circle cx='60' cy='40' r='3' fill='%23eab308'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/></svg>`
  },
  supernatural: {
    color: "#8b5cf6",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='none' stroke='%238b5cf6' stroke-width='0.8'/><circle cx='50' cy='50' r='20' fill='none' stroke='%238b5cf6' stroke-width='0.5' stroke-dasharray='5,5'/><path d='M35,35 L65,65 M65,35 L35,65' stroke='%238b5cf6' stroke-width='0.5'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>`
  },
  horror: {
    color: "#ff003c",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><rect x='15' y='15' width='70' height='70' fill='none' stroke='%23ff003c' stroke-width='0.8'/><line x1='15' y1='15' x2='85' y2='85' stroke='%23ff003c' stroke-width='0.8'/><line x1='85' y1='15' x2='15' y2='85' stroke='%23ff003c' stroke-width='0.8'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>`
  },
  mecha: {
    color: "#00f0ff",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><path d='M30,20 L70,20 L80,50 L50,80 L20,50 Z' fill='none' stroke='%2300f0ff' stroke-width='0.8'/><circle cx='50' cy='40' r='8' fill='none' stroke='%2300f0ff'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4M8 15h.01M16 15h.01"/></svg>`
  },
  slice: {
    color: "#a8e6cf",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><rect x='20' y='20' width='60' height='60' rx='6' fill='none' stroke='%23a8e6cf' stroke-width='0.8'/><line x1='30' y1='40' x2='70' y2='40' stroke='%23a8e6cf' stroke-width='0.5'/><line x1='30' y1='55' x2='55' y2='55' stroke='%23a8e6cf' stroke-width='0.5'/><circle cx='65' cy='55' r='5' fill='none' stroke='%23a8e6cf' stroke-width='0.6'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`
  },
  sports: {
    color: "#00ff66",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='30' fill='none' stroke='%2300ff66' stroke-width='0.8'/><path d='M30,35 Q50,10 70,35' fill='none' stroke='%2300ff66' stroke-width='0.8'/><path d='M30,65 Q50,90 70,65' fill='none' stroke='%2300ff66' stroke-width='0.8'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M2.1 13.4A10 10 0 0 0 13.4 2.1M21.9 10.6a10 10 0 0 0-11.3 11.3M5.1 5.1a10 10 0 0 0 13.8 13.8"/></svg>`
  },
  ecchi: {
    color: "#ff7eb3",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><circle cx='35' cy='35' r='15' fill='none' stroke='%23ff7eb3' stroke-width='0.8'/><circle cx='65' cy='35' r='15' fill='none' stroke='%23ff7eb3' stroke-width='0.8'/><path d='M25,70 Q50,85 75,70' fill='none' stroke='%23ff7eb3' stroke-width='0.8' stroke-linecap='round'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M4 7v10l8 3V4z"/><path d="M20 4v16"/></svg>`
  },
  psychological: {
    color: "#c084fc",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='35' r='18' fill='none' stroke='%23c084fc' stroke-width='0.8'/><line x1='50' y1='53' x2='50' y2='75' stroke='%23c084fc' stroke-width='0.8'/><line x1='30' y1='65' x2='70' y2='65' stroke='%23c084fc' stroke-width='0.6'/><path d='M35,25 Q50,15 65,25' fill='none' stroke='%23c084fc' stroke-width='0.5' stroke-dasharray='2,2'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/><path d="M4.93 4.93l14.14 14.14"/></svg>`
  },
  thriller: {
    color: "#f97316",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><path d='M50,15 L85,85 L15,85 Z' fill='none' stroke='%23f97316' stroke-width='0.8'/><circle cx='50' cy='55' r='6' fill='none' stroke='%23f97316' stroke-width='0.6'/><line x1='50' y1='40' x2='50' y2='49' stroke='%23f97316' stroke-width='0.8'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`
  },
  mahou_shoujo: {
    color: "#f472b6",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><path d='M50,10 L58,30 L80,32 L63,48 L68,70 L50,58 L32,70 L37,48 L20,32 L42,30 Z' fill='none' stroke='%23f472b6' stroke-width='0.8'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 2l2.5 5.5L20 8.5l-4 4.2L17 19l-5-3-5 3 1-6.3-4-4.2 5.5-1z"/></svg>`
  },
  music: {
    color: "#22d3ee",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><circle cx='35' cy='65' r='15' fill='none' stroke='%2322d3ee' stroke-width='0.8'/><path d='M50,65 L50,25 L80,30 L70,55 L50,50' fill='none' stroke='%2322d3ee' stroke-width='0.8'/><circle cx='65' cy='55' r='10' fill='none' stroke='%2322d3ee' stroke-width='0.6'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`
  },
  slice: {
    color: "#a8e6cf",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><rect x='20' y='20' width='60' height='60' rx='6' fill='none' stroke='%23a8e6cf' stroke-width='0.8'/><line x1='30' y1='40' x2='70' y2='40' stroke='%23a8e6cf' stroke-width='0.5'/><line x1='30' y1='55' x2='55' y2='55' stroke='%23a8e6cf' stroke-width='0.5'/><circle cx='65' cy='55' r='5' fill='none' stroke='%23a8e6cf' stroke-width='0.6'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`
  }
};

function getGenreConfig(genreId) {
  const norm = String(genreId || "").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  if (norm.includes("acao") || norm === "action") return GENRE_HUD_GRAPHICS.action;
  if (norm.includes("aventura") || norm === "adventure") return GENRE_HUD_GRAPHICS.adventure;
  if (norm.includes("fantasia") || norm === "fantasy") return GENRE_HUD_GRAPHICS.fantasy;
  if (norm.includes("ficcao") || norm.includes("scifi") || norm === "sci-fi") return GENRE_HUD_GRAPHICS.scifi;
  if (norm.includes("romance")) return GENRE_HUD_GRAPHICS.romance;
  if (norm.includes("drama")) return GENRE_HUD_GRAPHICS.drama;
  if (norm.includes("misterio") || norm === "mystery") return GENRE_HUD_GRAPHICS.mystery;
  if (norm.includes("comedia") || norm === "comedy") return GENRE_HUD_GRAPHICS.comedy;
  if (norm.includes("sobrenatural") || norm === "supernatural") return GENRE_HUD_GRAPHICS.supernatural;
  if (norm.includes("terror") || norm === "horror") return GENRE_HUD_GRAPHICS.horror;
  if (norm === "mecha") return GENRE_HUD_GRAPHICS.mecha;
  if (norm.includes("esportes") || norm === "sports") return GENRE_HUD_GRAPHICS.sports;
  if (norm.includes("slice")) return GENRE_HUD_GRAPHICS.slice;
  if (norm.includes("ecchi")) return GENRE_HUD_GRAPHICS.ecchi;
  if (norm.includes("psicologico") || norm === "psychological") return GENRE_HUD_GRAPHICS.psychological;
  if (norm === "thriller") return GENRE_HUD_GRAPHICS.thriller;
  if (norm.includes("mahou") || norm.includes("shoujo")) return GENRE_HUD_GRAPHICS.mahou_shoujo;
  if (norm.includes("musica") || norm === "music") return GENRE_HUD_GRAPHICS.music;
  return {
    color: "#64748b",
    svg: `<svg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'><circle cx='50' cy='50' r='25' fill='none' stroke='%2364748b' stroke-width='0.6'/><line x1='15' y1='50' x2='85' y2='50' stroke='%2364748b' stroke-width='0.4' stroke-dasharray='2,2'/></svg>`,
    icon: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>`
  };
}

function fillGenreGrid(el, list, { showGo = true } = {}) {
  if (!el) return;
  if (!list.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const g of list) {
    const id = g.id || g.name;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "genre-tile";
    btn.role = "option";
    btn.dataset.genre = id;
    btn.disabled = state.genreLoading;
    const config = getGenreConfig(id);
    const bgData = 'data:image/svg+xml;utf8,' + encodeURIComponent(config.svg);
    btn.style.setProperty("--genre-color", config.color);
    btn.innerHTML = `
      <div class="genre-tile-art" style="background-image:url('${bgData}')"></div>
      <div class="genre-tile-body">
        <span class="genre-tile-title">
          ${config.icon || ""}
          <span class="genre-tile-label">${escapeHtml(g.label || g.name)}</span>
        </span>
        ${showGo ? `<span class="genre-tile-go">Ver animes →</span>` : ""}
      </div>
    `;
    btn.addEventListener("click", () => selectGenre(id));
    frag.appendChild(btn);
  }
  el.appendChild(frag);
}

function selectGenre(id) {
  if (state.genreLoading || !id) return;
  state.selectedGenre = id;
  state.genreStep = "results";
  setGenreStep("results");
  loadGenreBrowse(id);
}

function setGenreStep(step) {
  state.genreStep = step;
  const pick = $("#genre-step-pick");
  const results = $("#genre-step-results");
  if (pick) pick.hidden = step !== "pick";
  if (results) results.hidden = step !== "results";
  // topbar já diz "Gêneros"; no passo 2 mostra o nome do gênero escolhido
  if (step === "results" && state.selectedGenre) {
    setTopbar("", genreLabel(state.selectedGenre));
  } else {
    setTopbar("", "Gêneros");
  }
}

function backToGenrePick() {
  state.genreSeq++; // cancela browse em andamento
  state.genreLoading = false;
  state.selectedGenre = "";
  state.genreItems = [];
  state.genreCatalog = [];
  showGenreLoading(false);
  setGenreStatus(false);
  setGenreStep("pick");
  renderGenrePickers();
}

function setGenreStatus(visible, text = "Buscando…") {
  const box = $("#genre-status");
  const label = $("#genre-status-text");
  if (label) label.textContent = text;
  if (box) box.hidden = !visible;
}

/**
 * Overlay de loading da tela de gêneros.
 * @param {boolean} visible
 * @param {{ title?: string, sub?: string, progress?: number|null, indeterminate?: boolean }} opts
 */
function showGenreLoading(visible, opts = {}) {
  const el = $("#genre-loading");
  const panel = $("#explore-panel");
  const titleEl = $("#genre-loading-title");
  const subEl = $("#genre-loading-sub");
  const barWrap = $(".genre-loading-bar");
  const bar = $("#genre-loading-bar");

  if (el) el.hidden = !visible;
  panel?.classList.toggle("is-loading", !!visible);

  if (!visible) {
    setGenreStatus(false);
    return;
  }

  const title = opts.title || "Carregando…";
  const sub = opts.sub || "Aguarde um instante";
  if (titleEl) titleEl.textContent = title;
  if (subEl) subEl.textContent = sub;
  setGenreStatus(true, title);

  const hasProgress =
    typeof opts.progress === "number" && !Number.isNaN(opts.progress);
  if (barWrap && bar) {
    if (hasProgress) {
      barWrap.classList.add("is-progress");
      bar.style.width = `${Math.max(4, Math.min(100, opts.progress))}%`;
    } else {
      barWrap.classList.remove("is-progress");
      bar.style.width = "";
    }
  }
}

function setExploreHead(title, kicker = "") {
  if (title) setTopbar("", title);
}

async function loadGenreBrowse(genre, { silent = false, force = false } = {}) {
  if (!genre) return;
  const seq = ++state.genreSeq;
  state.genreLoading = true;
  state.genreItems = [];
  state.genreCatalog = [];
  state.genrePage = 1;
  state.genreHasNext = false;
  state.genreCurrentGenre = genre;
  const moreWrap = $("#genre-load-more");
  if (moreWrap) moreWrap.hidden = true;
  setGenreStep("results");
  renderGenrePickers();

  const scroller = $("#genre-scroller");
  const count = $("#genre-count");
  const label = genreLabel(genre);
  setExploreHead(label);
  if (count) count.textContent = "…";

  // cache client (resultado já resolvido)
  const cached = state.genreCache[genre];
  if (!force && cached && Date.now() - cached.at < GENRE_CACHE_MS && cached.items?.length) {
    if (seq !== state.genreSeq) return;
    state.genrePage = 1;
    state.genreHasNext = true;
    state.genreCurrentGenre = genre;
    state.genreItems = cached.items;
    showGenreLoading(false);
    renderGenreAvailable(cached.items, { label, animated: false });
    state.genreLoading = false;
    return;
  }

  showGenreLoading(true, { title: `Carregando ${label}…` });

  try {
    await waitSourcesReady();
    if (seq !== state.genreSeq) return;

    // Preferência: catálogo rápido + resolve em lotes.
    // Fallback: /browse (servidor antigo ou rotas ausentes).
    let catalog;
    try {
      catalog = await api.genreCatalog(genre, 1, 20);
    } catch (catalogErr) {
      if (catalogErr.status === 404 || /not found/i.test(catalogErr.message || "")) {
        await loadGenreBrowseLegacy(genre, { seq, label, scroller, count });
        return;
      }
      throw catalogErr;
    }

    if (seq !== state.genreSeq) return;
    const candidates = catalog.items || [];
    state.genreCatalog = candidates;

    if (!candidates.length) {
      showGenreLoading(false);
      if (scroller) scroller.innerHTML = `<div class="empty-state"><strong>Nada neste gênero</strong>Não há títulos listados para ${escapeHtml(label)}.</div>`;
      if (count) count.textContent = "0";
      state.genreLoading = false;
      return;
    }

    // resolve em lotes — cards aparecem conforme chegam
    const batchSize = 5;
    const maxCheck = Math.min(candidates.length, 16);
    const queue = candidates.slice(0, maxCheck);
    const found = [];
    const seenTitles = new Set();
    if (count) count.textContent = `0 / ${queue.length}`;

    let resolveUnsupported = false;
    for (let i = 0; i < queue.length; i += batchSize) {
      if (seq !== state.genreSeq) return;
      const batch = queue.slice(i, i + batchSize);
      const done = Math.min(i + batch.length, queue.length);

      try {
        const res = await api.genreResolve(
          batch.map((c) => ({
            id: c.id, title: c.title, titles: c.titles || [c.title],
            image: c.image || "", score: c.score ?? null, banner: c.banner || "",
            season: c.season || "", season_label: c.season_label || "",
            season_line: c.season_line || "", year: c.year ?? null,
            format: c.format || "", format_label: c.format_label || "",
            status: c.status || "", status_label: c.status_label || "",
            episodes: c.episodes ?? null, studios: c.studios || [],
            genres: c.genres || [], genres_label: c.genres_label || [],
            description: c.description || "",
          }))
        );
        if (seq !== state.genreSeq) return;
        for (const item of res.items || []) {
          const key = (item.title || "").trim().toLowerCase();
          if (!key || seenTitles.has(key)) continue;
          seenTitles.add(key);
          found.push(item);
          appendGenreCard(item);
          if (count) count.textContent = `${found.length} / ${queue.length}`;
        }
      } catch (batchErr) {
        if (batchErr.status === 404 || batchErr.status === 405 || /not found|method not allowed/i.test(batchErr.message || "")) {
          resolveUnsupported = true;
          break;
        }
      }

      // Update loading text — stays visible until first card arrives
      if (!found.length) {
        showGenreLoading(true, { title: `Buscando… (${done}/${queue.length})` });
      } else {
        showGenreLoading(false);
      }
    }

    if (resolveUnsupported) {
      await loadGenreBrowseLegacy(genre, { seq, label, scroller, count });
      return;
    }

    if (seq !== state.genreSeq) return;
    state.genreItems = found;
    state.genreCache[genre] = { items: found, at: Date.now() };
    showGenreLoading(false);

    scroller?.querySelectorAll(".card.is-checking").forEach((n) => n.remove());

    if (!found.length) {
      if (scroller) scroller.innerHTML = `<div class="empty-state"><strong>Nada nas fontes</strong>Há ${queue.length} títulos de ${escapeHtml(label)} no catálogo, mas nenhum está nas fontes ativas.</div>`;
      if (count) count.textContent = "0";
    } else {
      if (count) count.textContent = `${found.length}`;
    }

    state.genrePage = Number(catalog.page) || 1;
    state.genreHasNext = Boolean(catalog.has_next);
  } catch (e) {
    if (seq !== state.genreSeq) return;
    showGenreLoading(false);
    if (!silent) toast(e.message || "Não foi possível buscar o gênero", true);
    if (scroller) scroller.innerHTML = `<div class="empty-state"><strong>Busca falhou</strong>${escapeHtml(e.message || "Tente outro gênero.")}</div>`;
    if (count) count.textContent = "0";
  } finally {
    if (seq === state.genreSeq) {
      state.genreLoading = false;
      showGenreLoading(false);
      renderGenrePickers();
      _renderGenreLoadMore();
    }
  }
}

/** Carrega a próxima página do mesmo gênero (via /browse) e anexa ao grid. */
async function loadMoreGenre() {
  const genre = state.genreCurrentGenre || state.selectedGenre;
  if (!genre || !state.genreHasNext) return;

  const btn = $("#genre-load-more-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Carregando…"; }

  const nextPage = state.genrePage + 1;
  try {
    const data = await api.browseGenre(genre, nextPage, 16);
    const items = data.items || [];
    if (!items.length) {
      state.genreHasNext = false;
      _renderGenreLoadMore();
      return;
    }
    state.genrePage = nextPage;
    state.genreHasNext = Boolean(data.has_next);
    const seen = new Set(state.genreItems.map((i) => (i.title || "").trim().toLowerCase()));
    for (const item of items) {
      const key = (item.title || "").trim().toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      state.genreItems.push(item);
      appendGenreCard(item);
    }
    const count = $("#genre-count");
    if (count) count.textContent = `${state.genreItems.length}`;
  } catch (e) {
    toast(e.message || "Falha ao carregar mais", true);
  } finally {
    _renderGenreLoadMore();
  }
}

function _renderGenreLoadMore() {
  const wrap = $("#genre-load-more");
  const btn = $("#genre-load-more-btn");
  if (wrap) wrap.hidden = !state.genreHasNext;
  if (btn) {
    btn.disabled = false;
    btn.textContent = "Carregar mais";
    btn.onclick = () => loadMoreGenre();
  }
}

/** Fallback único request: /api/genres/browse */
async function loadGenreBrowseLegacy(genre, { seq, label, scroller, count }) {
  showGenreLoading(true, { title: `Carregando ${label}…` });
  try {
    const data = await api.browseGenre(genre, 1, 16);
    if (seq !== state.genreSeq) return;
    const items = data.items || [];
    state.genreItems = items;
    state.genreCache[genre] = { items, at: Date.now() };
    state.genrePage = Number(data.page) || 1;
    state.genreHasNext = Boolean(data.has_next);
    renderGenreAvailable(items, { label: data.label || label, animated: true });
  } catch (e) {
    if (seq !== state.genreSeq) return;
    if (scroller) scroller.innerHTML = `<div class="empty-state"><strong>Busca falhou</strong>${escapeHtml(e.message || "Tente outro gênero.")}</div>`;
    if (count) count.textContent = "0";
  } finally {
    if (seq === state.genreSeq) {
      state.genreLoading = false;
      showGenreLoading(false);
      _renderGenreLoadMore();
    }
  }
}

function genreLabel(id) {
  const g = state.genres.find((x) => (x.id || x.name) === id);
  return g?.label || id;
}

// ── Calendário de lançamentos ────────────────────────────────────────────────

const CALENDAR_CACHE_MS = 5 * 60 * 1000;

function loadCalendarCheckPref() {
  try {
    return localStorage.getItem("anishelf.calendarCheckSources") === "1";
  } catch {
    return false;
  }
}

function saveCalendarCheckPref(on) {
  try {
    localStorage.setItem("anishelf.calendarCheckSources", on ? "1" : "0");
  } catch {
    /* ignore */
  }
}

async function loadCalendarPage({ force = false } = {}) {
  const board = $("#calendar-board");
  const status = $("#calendar-status");
  const statusText = $("#calendar-status-text");
  const checkEl = $("#calendar-check-sources");

  if (checkEl && checkEl.checked !== !!state.calendarCheckSources) {
    checkEl.checked = !!state.calendarCheckSources;
  }

  const cached = state.calendarCache;
  if (
    !force &&
    cached &&
    cached.days === state.calendarDays &&
    !!cached.check_sources === !!state.calendarCheckSources &&
    Date.now() - cached.at < CALENDAR_CACHE_MS
  ) {
    state.calendarItems = cached.items;
    renderCalendar(cached.items);
    return;
  }

  state.calendarLoading = true;
  if (status) status.hidden = false;
  if (statusText) {
    statusText.textContent = state.calendarCheckSources
      ? "Conferindo episódios nas fontes…"
      : "Carregando…";
  }
  if (board && !state.calendarItems.length) {
    board.innerHTML = `<div class="empty-state">Buscando próximos episódios…</div>`;
  }
  syncCalendarRangeButtons();

  try {
    if (state.calendarCheckSources) {
      await waitSourcesReady();
    }
    const data = await api.calendar(
      state.calendarDays,
      !!state.calendarCheckSources
    );
    const items = data.items || [];
    state.calendarItems = items;
    state.calendarCache = {
      days: state.calendarDays,
      check_sources: !!state.calendarCheckSources,
      items,
      at: Date.now(),
      total: data.total,
      available_total: data.available_total,
    };
    renderCalendar(items);
  } catch (e) {
    if (board) {
      board.innerHTML = `<div class="empty-state"><strong>Calendário indisponível</strong>${escapeHtml(
        e.message || "Tente novamente."
      )}</div>`;
    }
    toast(e.message || "Não foi possível carregar o calendário", true);
  } finally {
    state.calendarLoading = false;
    if (status) status.hidden = true;
  }
}

function syncCalendarRangeButtons() {
  $$("#calendar-range .range-btn").forEach((btn) => {
    const d = Number(btn.dataset.days);
    btn.classList.toggle("active", d === state.calendarDays);
  });
  const checkEl = $("#calendar-check-sources");
  if (checkEl) checkEl.checked = !!state.calendarCheckSources;
}

function renderCalendar(items) {
  const board = $("#calendar-board");
  if (!board) return;

  const checking = !!state.calendarCheckSources;
  const groups = groupAiringByLocalDay(items || [], state.calendarDays);
  const hasAny = groups.some((g) => g.items.length > 0);
  if (!hasAny) {
    board.innerHTML = `<div class="empty-state"><strong>Nada neste período</strong>Sem episódios nos próximos ${state.calendarDays} dias.</div>`;
    return;
  }

  board.innerHTML = "";
  const frag = document.createDocumentFragment();
  const todayKey = localDateKey(new Date());

  for (const g of groups) {
    if (!g.items.length) continue;
    const day = document.createElement("section");
    day.className = "calendar-day" + (g.key === todayKey ? " is-today" : "");
    const label = formatCalendarDayLabel(g.key, todayKey);
    const avail = g.items.filter((i) => i.available === true).length;
    const countLabel = checking
      ? `${g.items.length} ep · ${avail} disponíveis`
      : `${g.items.length} ep${g.items.length === 1 ? "" : "s"}`;
    day.innerHTML = `
      <div class="calendar-day-head">
        <div class="calendar-day-title">
          ${escapeHtml(label.title)}
          <small>${escapeHtml(label.sub)}</small>
        </div>
        <span class="calendar-day-count">${escapeHtml(countLabel)}</span>
      </div>
      <div class="calendar-list"></div>
    `;
    const list = day.querySelector(".calendar-list");
    for (const item of g.items) {
      list.appendChild(calendarRow(item, { checking }));
    }
    frag.appendChild(day);
  }
  board.appendChild(frag);
}

function localDateKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function groupAiringByLocalDay(items, days) {
  const map = new Map();
  for (const item of items) {
    const ts = Number(item.airing_at) * 1000;
    if (!ts) continue;
    const key = localDateKey(new Date(ts));
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(item);
  }

  // grade contínua de dias a partir de hoje
  const out = [];
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  for (let i = 0; i < days; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const key = localDateKey(d);
    const dayItems = (map.get(key) || []).slice().sort(
      (a, b) => Number(a.airing_at) - Number(b.airing_at)
    );
    out.push({ key, items: dayItems });
  }
  return out;
}

function formatCalendarDayLabel(key, todayKey) {
  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const weekday = date.toLocaleDateString("pt-BR", { weekday: "long" });
  const full = date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
  });
  const cap = weekday.charAt(0).toUpperCase() + weekday.slice(1);
  if (key === todayKey) {
    return { title: "Hoje", sub: `${cap} · ${full}` };
  }
  const tomorrow = new Date();
  tomorrow.setHours(0, 0, 0, 0);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (key === localDateKey(tomorrow)) {
    return { title: "Amanhã", sub: `${cap} · ${full}` };
  }
  return { title: cap, sub: full };
}

function calendarRow(item, { checking = false } = {}) {
  const btn = document.createElement("button");
  btn.type = "button";
  const available =
    checking &&
    item.available === true &&
    (item.sources || []).some((s) => s?.link || s?.episode_link);
  const unavailable = checking && item.available === false;
  btn.className =
    "calendar-row" +
    (available ? " is-available" : "") +
    (unavailable ? " is-unavailable" : "");
  const when = new Date(Number(item.airing_at) * 1000);
  const time = when.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const relative = formatTimeUntil(item.airing_at);
  const poster = imgUrl(item.source_image || item.image);
  const sourceNames = (item.sources || []).map((s) => s.name).filter(Boolean);
  let unavailHint = "Episódio ainda não está nas fontes";
  if (item.unavailable_reason === "anime_only") {
    unavailHint = "Anime nas fontes, episódio ainda não";
  } else if (item.unavailable_reason === "episode_unknown") {
    unavailHint = "Sem número de episódio para conferir";
  } else if (unavailable) {
    unavailHint = "Não está nas fontes ativas";
  }
  const sub = [
    available ? sourceNames.slice(0, 2).join(" · ") : null,
    unavailable ? unavailHint : null,
    item.format_label,
    item.score != null ? `★ ${(item.score / 10).toFixed(1)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const ep =
    item.episode != null && item.episode !== ""
      ? `Ep ${item.episode}`
      : "Ep ?";
  const badges = [];
  if (checking) {
    badges.push(
      available
        ? `<span class="cal-badge cal-badge-ok">disponível</span>`
        : `<span class="cal-badge cal-badge-off">indisponível</span>`
    );
  }
  // fontes do calendário: link/episode_link + variant
  const audioSources = (item.sources || []).map((s) => ({
    ...s,
    link: s.link || s.episode_link || "",
    variant:
      s.variant ||
      detectAudioVariant(s.title || item.source_title || item.title || "", s.link || s.episode_link || ""),
  }));
  badges.push(audioChoiceBadge(audioSources, "cal"));

  btn.innerHTML = `
    <div class="calendar-time">
      ${relative ? `<strong>${escapeHtml(relative)}</strong>` : escapeHtml(time)}
      <small>${escapeHtml(time)}</small>
    </div>
    <div class="calendar-thumb" style="${
      poster ? `background-image:url('${poster}')` : ""
    }"></div>
    <div class="calendar-info">
      <div class="calendar-title-row">
        <div class="calendar-title">${escapeHtml(item.source_title || item.title || "Anime")}</div>
        <div class="calendar-badges">${badges.filter(Boolean).join("")}</div>
      </div>
      <div class="calendar-sub">${escapeHtml(sub)}</div>
    </div>
    <span class="calendar-ep">${escapeHtml(ep)}</span>
  `;
  btn.addEventListener("click", () => openCalendarItem(item, { checking }));
  return btn;
}

function formatTimeUntil(airingAt) {
  const ts = Number(airingAt) * 1000;
  if (!ts) return "";
  const diff = ts - Date.now();
  if (diff < 0) return "agora";
  const mins = Math.round(diff / 60000);
  if (mins < 60) return `em ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) {
    const rem = mins % 60;
    return rem ? `em ${hours} h ${rem} min` : `em ${hours} h`;
  }
  const days = Math.floor(hours / 24);
  return days === 1 ? "em 1 dia" : `em ${days} dias`;
}

function navigateToAnimeSource(src, { title = "", anilistId = "" } = {}) {
  if (!src?.link) {
    toast("Link inválido", true);
    return;
  }
  const q = [
    `link=${encodeURIComponent(src.link)}`,
    `source=${encodeURIComponent(src.name || "")}`,
  ];
  if (anilistId) q.push(`al=${encodeURIComponent(anilistId)}`);
  if (title) q.push(`title=${encodeURIComponent(stripTitleVariants(title) || title)}`);
  navigate(`anime?${q.join("&")}`);
}

function pickAnimeSourceThenOpen(title, sources, { anilistId = "" } = {}) {
  const linked = (sources || []).filter((s) => s?.link);
  if (!linked.length) {
    toast("Não achei nas fontes ativas", true);
    return;
  }
  if (hasAudioChoice(linked)) {
    openAudioChoiceModal(title, linked, (picked) => {
      navigateToAnimeSource(picked[0], { title, anilistId });
    });
    return;
  }
  navigateToAnimeSource(linked[0], { title, anilistId });
}

async function openCalendarItem(item, { checking = false } = {}) {
  const title = item.source_title || item.title || item.media?.title || "";
  const sources = item.sources || [];

  // com cruzamento: só abre se o episódio estiver disponível
  if (checking) {
    const linked = sources
      .map((s) => ({
        ...s,
        link: s.link || s.episode_link || "",
        variant:
          s.variant ||
          detectAudioVariant(s.title || title, s.link || s.episode_link || ""),
        title: s.title || title,
      }))
      .filter((s) => s.link);
    if (linked.length) {
      pickAnimeSourceThenOpen(title, linked, { anilistId: item.id || "" });
      return;
    }
    const ep =
      item.episode != null && item.episode !== "" ? ` ep ${item.episode}` : "";
    if (item.unavailable_reason === "anime_only") {
      toast(
        title
          ? `"${title}"${ep} ainda não está nas fontes`
          : "Episódio ainda não está nas fontes",
        true
      );
      return;
    }
    toast(
      title
        ? `"${title}"${ep} indisponível nas fontes`
        : "Indisponível nas fontes ativas",
      true
    );
    return;
  }

  // sem cruzamento: tenta achar o anime nas fontes ao clicar
  if (!title) {
    toast("Título inválido", true);
    return;
  }
  toast(`Procurando ${title}…`);
  try {
    await waitSourcesReady();
    const data = await api.search(title);
    const hit = (data.items || [])[0];
    pickAnimeSourceThenOpen(title, hit?.sources || [], {
      anilistId: item.id || "",
    });
  } catch (e) {
    toast(e.message || "Busca falhou", true);
  }
}

/** Placeholders com poster AniList enquanto checa fontes. */
function renderGenreChecking(candidates) {
  const scroller = $("#genre-scroller");
  if (!scroller) return;
  scroller.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const c of (candidates || []).slice(0, 12)) {
    frag.appendChild(catalogPlaceholderCard(c));
  }
  scroller.appendChild(frag);
}

function catalogPlaceholderCard(item) {
  const poster = imgUrl(item.image);
  const metaBits = [
    item.season_line || (item.year ? String(item.year) : ""),
    item.format_label || "",
    item.status_label || "",
  ].filter(Boolean);
  const el = document.createElement("article");
  el.className = "card is-checking";
  el.innerHTML = `
    <div class="card-poster ${poster ? "has-img" : ""}" style="${posterStyle(poster)}">
      <span class="card-badge-check">conferindo</span>
    </div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(item.title)}</div>
      <div class="card-meta">
        ${item.score ? `<span class="ep-badge">★ ${(item.score / 10).toFixed(1)}</span>` : ""}
      </div>
      ${
        metaBits.length
          ? `<div class="card-meta-line">${metaBits
              .map((b) => `<span class="meta-mini">${escapeHtml(b)}</span>`)
              .join("<span class='meta-mini'>·</span>")}</div>`
          : ""
      }
    </div>
  `;
  return el;
}

function appendGenreCard(item) {
  const scroller = $("#genre-scroller");
  if (!scroller) return;
  // remove empty-state se existir
  const empty = scroller.querySelector(".empty-state");
  if (empty) empty.remove();
  // remove placeholders "checando" quando o primeiro real chega
  scroller.querySelectorAll(".card.is-checking").forEach((n) => n.remove());
  const card = animeCard(item);
  card.classList.add("available-pop");
  scroller.appendChild(card);
}

function renderGenreAvailable(items, { label = "", animated = true } = {}) {
  const scroller = $("#genre-scroller");
  const count = $("#genre-count");
  if (!scroller) return;
  scroller.innerHTML = "";
  if (!items.length) {
    scroller.innerHTML = `<div class="empty-state"><strong>Nada nas fontes</strong>Nenhum anime de ${escapeHtml(label || "gênero")} nas fontes ativas.</div>`;
    if (count) count.textContent = "0";
    return;
  }
  if (count) count.textContent = `${items.length}`;
  const frag = document.createDocumentFragment();
  for (const anime of items) {
    const card = animeCard(anime);
    if (animated) card.classList.add("available-pop");
    frag.appendChild(card);
  }
  scroller.appendChild(frag);
}

function renderHero() {
  // usa a lista já deduplicada (dublado/legendado mesclados)
  const item = dedupeEpisodesByWork(state.episodes)[0];
  state.heroItem = item || null;
  if (!item) {
    $("#hero-title").textContent = "Nada por aqui";
    $("#hero-desc").textContent =
      "Ative ao menos uma fonte em Fontes para ver episódios.";
    const bg = $("#hero-bg");
    if (bg) bg.style.backgroundImage = "";
    $("#hero-meta").textContent = "Nenhum episódio no momento";
    return;
  }
  const bg = $("#hero-bg");
  if (bg) {
    const poster = imgUrl(item.image);
    if (poster) {
      const img = new Image();
      img.onload = () => { bg.style.backgroundImage = `url('${poster}')`; };
      img.onerror = () => { bg.style.backgroundImage = `url('${PLACEHOLDER_POSTER}')`; };
      img.src = poster;
    } else {
      bg.style.backgroundImage = `url('${PLACEHOLDER_POSTER}')`;
    }
  }
  const links = (item.sources || []).map((s) => s.link);
  const labels = normalizeWatchTitles(
    item.title,
    item.title,
    resolveEpisodeNumber(item.number, item.title, ...links)
  );
  $("#hero-title").textContent = labels.animeTitle || item.title;
  const metaBits = [
    labels.number && labels.number !== "?" ? labels.episodeLine : null,
    [...new Set((item.sources || []).map((s) => s.name).filter(Boolean))].join(" · ") || null,
  ].filter(Boolean);
  const heroMeta = $("#hero-meta");
  if (heroMeta) {
    const audio = audioChoiceBadge(item.sources, "inline");
    heroMeta.innerHTML = [
      audio,
      metaBits.length ? `<span>${escapeHtml(metaBits.join("  ·  "))}</span>` : "",
    ]
      .filter(Boolean)
      .join(" ");
    if (!heroMeta.innerHTML.trim()) {
      heroMeta.textContent = "";
    }
  }
  $("#hero-desc").textContent = "Pronto para assistir. Se uma fonte falhar, tentamos outra.";
}

function renderEpisodesRow() {
  const scroller = $("#episodes-scroller");
  if (!scroller) return;
  scroller.innerHTML = "";
  const count = $("#episodes-count");
  const episodes = dedupeEpisodesByWork(state.episodes);
  if (!episodes.length) {
    scroller.innerHTML = `<div class="empty-state"><strong>Lista vazia</strong>Nenhum episódio nas fontes ativas. Ative alguma em Fontes.</div>`;
    if (count) count.textContent = "0";
    return;
  }
  if (count) count.textContent = `${episodes.length}`;
  const frag = document.createDocumentFragment();
  for (const ep of episodes) {
    frag.appendChild(episodeCard(ep));
  }
  scroller.appendChild(frag);
}

/** Mescla "X" e "X Dublado" no mesmo ep (safety net se a API falhar). */
function dedupeEpisodesByWork(items) {
  const map = new Map();
  for (const ep of items || []) {
    const links = (ep.sources || []).map((s) => s.link).filter(Boolean);
    const labels = normalizeWatchTitles(
      ep.title,
      ep.title,
      resolveEpisodeNumber(ep.number, ep.title, ...links)
    );
    const base = (labels.animeTitle || "").trim().toLowerCase();
    const num =
      labels.number && labels.number !== "?"
        ? String(Number(labels.number) || labels.number)
        : "";
    const key = num ? `${base}|${num}` : base;
    if (!key) continue;
    if (!map.has(key)) {
      map.set(key, {
        ...ep,
        title: labels.animeTitle || ep.title,
        number: labels.number || ep.number,
        sources: [...(ep.sources || [])],
      });
      continue;
    }
    const cur = map.get(key);
    // prefer título limpo já vem de labels; preenche imagem/data
    if (!cur.image && ep.image) cur.image = ep.image;
    if (!cur.date && ep.date) cur.date = ep.date;
    for (const s of ep.sources || []) {
      // garante variant no merge client-side
      const enriched = {
        ...s,
        variant: s.variant || detectAudioVariant(s.title || ep.title || "", s.link || ""),
        title: s.title || ep.title || "",
      };
      const same = cur.sources.some(
        (x) =>
          (enriched.link && x.link === enriched.link) ||
          (x.name === enriched.name &&
            audioBucket(resolveSourceVariant(x)) ===
              audioBucket(resolveSourceVariant(enriched)))
      );
      if (!same) cur.sources.push(enriched);
    }
  }
  return [...map.values()];
}

/** Dedup client-side por anime (safety net se a API falhar). */
function dedupeHistoryByAnime(items) {
  const seen = new Set();
  const out = [];
  for (const h of items || []) {
    const labels = normalizeWatchTitles(
      h.anime_title,
      h.episode_title,
      h.episode_number
    );
    const key = (labels.animeTitle || h.anime_title || "").trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push({ ...h, anime_title: labels.animeTitle, episode_title: labels.episodeTitle, episode_number: labels.number });
  }
  return out;
}

async function renderContinueRow() {
  const row = $("#row-continue");
  const scroller = $("#continue-scroller");
  if (!row || !scroller) return;
  try {
    const data = await api.history(true);
    state.history = dedupeHistoryByAnime(data.items || []);
    const active = state.history.filter((h) => !h.is_finished);
    if (!active.length) {
      row.hidden = true;
      return;
    }
    row.hidden = false;
    scroller.innerHTML = "";
    const frag = document.createDocumentFragment();
    for (const h of active.slice(0, 20)) {
      frag.appendChild(historyCard(h));
    }
    scroller.appendChild(frag);
  } catch {
    row.hidden = true;
  }
}

// ── Play flow ────────────────────────────────────────────────────────────────

function sourcesToCandidates(sources) {
  return (sources || [])
    .filter((s) => s?.link)
    .map((s) => ({
      name: s.name || "",
      link: s.link,
      color: s.color || "",
      variant: s.variant || detectAudioVariant(s.title || "", s.link || ""),
      title: s.title || "",
    }));
}

/** dublado | legendado | original */
function detectAudioVariant(title = "", link = "") {
  const blob = `${title || ""} ${link || ""}`;
  if (
    /\bdublado\b/i.test(blob) ||
    /\b(?:pt[- ]?br\s+)?dub\b/i.test(blob) ||
    /[(\[]\s*dub\s*[)\]]/i.test(blob) ||
    /\/dub(?:lado)?(?:\/|$)/i.test(blob)
  ) {
    return "dublado";
  }
  if (
    /\blegendado\b/i.test(blob) ||
    /\bleg\b/i.test(blob) ||
    /[(\[]\s*leg\s*[)\]]/i.test(blob) ||
    /\/leg(?:endado)?(?:\/|$)/i.test(blob)
  ) {
    return "legendado";
  }
  return "original";
}

/** Agrupa em dublado vs legendado (original sem marcador conta como legendado). */
function audioBucket(variant) {
  return variant === "dublado" ? "dublado" : "legendado";
}

function resolveSourceVariant(s) {
  return s?.variant || detectAudioVariant(s?.title || "", s?.link || "");
}

function hasAudioChoice(sources) {
  const linked = (sources || []).filter((s) => s?.link);
  if (linked.length < 2) return false;
  const buckets = new Set(linked.map((s) => audioBucket(resolveSourceVariant(s))));
  return buckets.has("dublado") && buckets.has("legendado");
}

function sourcesForAudioBucket(sources, bucket) {
  return (sources || []).filter(
    (s) => s?.link && audioBucket(resolveSourceVariant(s)) === bucket
  );
}

function audioOptionMeta(bucket, sources) {
  const names = [...new Set(sources.map((s) => s.name).filter(Boolean))];
  if (bucket === "dublado") {
    return {
      key: "dublado",
      label: "Dublado",
      hint: names.length
        ? `Áudio em português · ${names.join(" · ")}`
        : "Áudio em português",
      accent: "var(--sakura)",
    };
  }
  return {
    key: "legendado",
    label: "Legendado",
    hint: names.length
      ? `Áudio original · ${names.join(" · ")}`
      : "Áudio original com legendas",
    accent: "var(--cyan)",
  };
}

/**
 * Menu de áudio quando há dublado e legendado.
 * onPick(sourcesDoBucket)
 */
function openAudioChoiceModal(workTitle, sources, onPick) {
  const dub = sourcesForAudioBucket(sources, "dublado");
  const sub = sourcesForAudioBucket(sources, "legendado");
  const options = [];
  if (sub.length) options.push({ ...audioOptionMeta("legendado", sub), sources: sub });
  if (dub.length) options.push({ ...audioOptionMeta("dublado", dub), sources: dub });

  openChoiceModal({
    heading: "Como prefere assistir?",
    subtitle: stripTitleVariants(workTitle) || workTitle || "",
    options: options.map((o) => ({
      label: o.label,
      hint: o.hint,
      accent: o.accent,
      data: o.sources,
    })),
    onPick,
  });
}

/**
 * Modal genérico de opções (áudio ou fonte).
 * options: [{ label, hint?, accent?, data }]
 */
function openChoiceModal({ heading, subtitle, options, onPick }) {
  const modal = $("#source-modal");
  const list = $("#source-options");
  const headingEl = $("#source-modal-heading");
  if (headingEl) headingEl.textContent = heading || "Escolha";
  $("#source-modal-title").textContent = subtitle || "";
  list.innerHTML = "";
  for (const opt of options || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "source-opt source-opt-rich";
    const accent = opt.accent || opt.color || "#888";
    btn.innerHTML = `
      <span class="source-dot" style="--dot:${accent};background:${accent}"></span>
      <span class="source-opt-text">
        <span class="source-opt-label">${escapeHtml(opt.label)}</span>
        ${
          opt.hint
            ? `<span class="source-opt-hint">${escapeHtml(opt.hint)}</span>`
            : ""
        }
      </span>
    `;
    btn.addEventListener("click", () => {
      modal.hidden = true;
      onPick(opt.data);
    });
    list.appendChild(btn);
  }
  modal.hidden = false;
}

function openSourceModal(title, sources, onPick) {
  openChoiceModal({
    heading: "Qual fonte?",
    subtitle: title || "",
    options: (sources || []).map((s) => ({
      label: s.name || "Fonte",
      hint: s.variant
        ? audioOptionMeta(audioBucket(resolveSourceVariant(s)), [s]).label
        : "",
      accent: s.color || "#888",
      color: s.color,
      data: s,
    })),
    onPick,
  });
}

function playEpisodeFromSources(item, sources) {
  const list = (sources || []).filter((s) => s?.link);
  if (!list.length) {
    toast("Nenhuma fonte disponível", true);
    return;
  }
  const links = list.map((s) => s.link).filter(Boolean);
  const num = resolveEpisodeNumber(item.number, item.title, ...links);
  const labels = normalizeWatchTitles(item.title, item.title, num);
  playEpisode({
    preferred_source: list[0].name,
    anime_title: labels.animeTitle,
    episode_title: labels.episodeTitle,
    episode_number: labels.number,
    anime_image: item.image,
    source_color: list[0].color,
    candidates: sourcesToCandidates(list),
  });
}

function onEpisodeClick(item) {
  const sources = (item.sources || []).filter((s) => s?.link);
  if (!sources.length) {
    toast("Nenhuma fonte disponível", true);
    return;
  }
  // Sempre que existirem dublado e legendado, o usuário escolhe
  if (hasAudioChoice(sources)) {
    openAudioChoiceModal(item.title, sources, (picked) => {
      playEpisodeFromSources(item, picked);
    });
    return;
  }
  // Uma só variante: fallback automático entre fontes
  playEpisodeFromSources(item, sources);
}

/** Extrai nº do episódio de título/URL (espelha o backend). */
function extractEpisodeNumber(...parts) {
  const patterns = [
    /\bs\d{1,2}\s*e\s*(\d{1,4})\b/i,
    /\b(?:epis[oó]dios?|episodes?|cap[ií]tulos?|capitulos?)\s*[#.:\-–—]?\s*(\d{1,4})\b/i,
    /\beps?\.?\s*[#.:\-–—]?\s*(\d{1,4})\b/i,
    /\bcap\.?\s*[#.:\-–—]?\s*(\d{1,4})\b/i,
    /(?:^|[\s\-–—|/])e\s*(\d{1,4})\b/i,
    /#\s*(\d{1,4})\b/,
    /[\-–—:|]\s*(\d{1,4})\s*$/,
    /^(\d{1,4})$/,
  ];
  const urlPatterns = [
    /(?:episodio|episode|episodios|episodes|ep)[_/\-]?(\d{1,4})/i,
    /\/e(\d{1,4})(?:\/|$)/i,
    /[_-](\d{1,4})(?:\/|$|\.)/,
  ];

  const clean = (raw) => {
    if (!raw) return null;
    const m = String(raw).match(/(\d+)/);
    if (!m) return null;
    const n = m[1];
    if (n.length === 4 && (n.startsWith("19") || n.startsWith("20"))) return null;
    return String(parseInt(n, 10));
  };

  for (const part of parts) {
    if (!part) continue;
    let text = String(part);
    try {
      text = decodeURIComponent(text);
    } catch {
      /* keep raw */
    }
    const isUrl = text.includes("://") || text.startsWith("/");
    if (isUrl) {
      let path = text;
      try {
        path = new URL(text, "https://x").pathname;
      } catch {
        /* keep */
      }
      for (const re of urlPatterns) {
        const all = [...path.matchAll(new RegExp(re.source, re.flags + "g"))];
        if (all.length) {
          const n = clean(all[all.length - 1][1]);
          if (n) return n;
        }
      }
      text = path.replace(/[/_-]+/g, " ");
    }
    for (const re of patterns) {
      const m = text.match(re);
      if (m) {
        const n = clean(m[1]);
        if (n) return n;
      }
    }
  }
  return "";
}

function resolveEpisodeNumber(known, ...parts) {
  const k = String(known ?? "").trim();
  if (k && k !== "?" && k !== "0") return k;
  return extractEpisodeNumber(...parts) || k || "?";
}

function formatEpLabel(number) {
  const n = String(number ?? "").trim();
  if (!n || n === "?" || n === "0") return "Ep";
  return `Ep ${n}`;
}

/** Remove "Episódio N" / "Ep N" do título (evita "Ep 1 · Episodio 1"). */
function stripEpisodeSuffix(text, number) {
  let t = String(text ?? "").trim();
  if (!t) return "";
  const patterns = [
    /\s*[\-–—:|·•]\s*(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}\s*$/i,
    /\s+(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}\s*$/i,
    /\s+s\d{1,2}\s*e\s*\d{1,4}\s*$/i,
    /\s*[\-–—:|]\s*\d{1,4}\s*$/,
  ];
  for (let i = 0; i < 3; i++) {
    const prev = t;
    for (const re of patterns) t = t.replace(re, "").trim();
    const n = String(number ?? "").trim();
    if (n && n !== "?" && n !== "0") {
      const esc = n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      t = t
        .replace(
          new RegExp(
            `\\s*[\\-–—:|·•]?\\s*(?:epis[oó]dios?|episodes?|eps?\\.?|cap\\.?)\\s*[#.:]?\\s*0*${esc}\\s*$`,
            "i"
          ),
          ""
        )
        .trim();
    }
    if (t === prev) break;
  }
  return t;
}

function isOnlyEpisodeLabel(text) {
  return /^(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}$/i.test(
    String(text ?? "").trim()
  );
}

/** Remove Dublado/Legendado/HD do título (sem mexer em temporada). */
function stripTitleVariants(title) {
  let t = String(title || "").trim();
  if (!t) return "";
  t = t
    .replace(/\b(?:dublado|legendado|audiodescrito)\b/gi, " ")
    .replace(/\b(?:dub|leg)\b/gi, " ")
    .replace(/[(\[]\s*(?:dub|leg|dublado|legendado|pt[- ]?br|ptbr)\s*[)\]]/gi, " ")
    .replace(/\b(?:full\s*)?hd\b/gi, " ")
    .replace(/\b\d{3,4}p\b/gi, " ")
    .replace(/\b(?:online|assistir|completo)\b/gi, " ")
    .replace(/\s*[\-|–—:]\s*$/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s\-–—|:]+|[\s\-–—|:]+$/g, "")
    .trim();
  return t;
}

/**
 * Títulos limpos pra UI/histórico.
 * @returns {{ animeTitle: string, episodeTitle: string, number: string, episodeLine: string }}
 */
function normalizeWatchTitles(animeTitle, episodeTitle, number) {
  const num = resolveEpisodeNumber(number, episodeTitle, animeTitle);
  let anime = stripTitleVariants(stripEpisodeSuffix(animeTitle, num));
  let ep = stripEpisodeSuffix(episodeTitle, num);
  // episódio com "Dublado" no meio do nome da obra — limpa só se for o mesmo base
  ep = stripTitleVariants(ep);

  if (isOnlyEpisodeLabel(episodeTitle) || isOnlyEpisodeLabel(ep)) ep = "";
  if (ep && anime && ep.toLowerCase() === anime.toLowerCase()) ep = "";

  if (!anime) {
    anime =
      stripTitleVariants(stripEpisodeSuffix(episodeTitle, num)) ||
      stripTitleVariants(String(animeTitle || episodeTitle || "Anime").trim()) ||
      "Anime";
    if (isOnlyEpisodeLabel(anime)) {
      anime = stripTitleVariants(String(animeTitle || "Anime").trim()) || "Anime";
    }
  }

  const epLabel = formatEpLabel(num);
  // "Ep 1" sozinho, ou "Ep 1 · Nome especial do episódio" — nunca "Ep 1 · Episodio 1"
  const episodeLine = ep ? `${epLabel} · ${ep}` : epLabel;

  return {
    animeTitle: anime,
    episodeTitle: ep,
    number: num,
    episodeLine,
  };
}

async function playEpisode(payload) {
  const candidates = payload.candidates?.length
    ? payload.candidates
    : payload.episode_link
      ? [
          {
            name: payload.preferred_source || "",
            link: payload.episode_link,
            color: payload.source_color || "",
          },
        ]
      : [];

  if (!candidates.length) {
    toast("Nenhuma fonte para reproduzir", true);
    return;
  }

  // loading fica só no player (spinner rosa) — sem toast duplicado
  if (candidates.length > 1) {
    toast(`Tentando ${candidates.length} fontes…`);
  }

  try {
    const labels = normalizeWatchTitles(
      payload.anime_title || "",
      payload.episode_title || "",
      payload.episode_number || ""
    );
    const body = {
      preferred_source: payload.preferred_source || candidates[0].name,
      anime_title: labels.animeTitle,
      episode_title: labels.episodeTitle,
      episode_number: labels.number || "0",
      anime_image: payload.anime_image || "",
      season_number: payload.season_number || 1,
      source_color: payload.source_color || candidates[0].color || "",
      episode_link: payload.episode_link || candidates[0].link,
      candidates,
    };
    const res = await api.play(body);
    const usedSource = res.source_name || body.preferred_source || "";

    if (res.switched) {
      const failed = (res.tried || [])
        .filter((t) => !t.ok)
        .map((t) => t.name)
        .filter(Boolean);
      toast(
        failed.length
          ? `${failed.join(", ")} falhou · usando ${usedSource}`
          : `Tocando em ${usedSource}`
      );
    }

    // IDs p/ AniSkip (timestamps reais da opening por episódio)
    let malId =
      payload.mal_id ||
      state.detailMeta?.mal_id ||
      null;
    const anilistId =
      payload.anilist_id ||
      state.detailMeta?.id ||
      null;
    // se ainda não tem MAL (play pela home), resolve antes de abrir o player
    if (!malId && labels.animeTitle) {
      try {
        const meta = await api.meta(labels.animeTitle);
        if (meta?.mal_id) malId = meta.mal_id;
      } catch {
        /* opcional */
      }
    }
    const epNum = Number(labels.number);
    await openPlayer({
      playable: res.playable,
      streamUrl: res.stream_url,
      isHls: res.is_hls,
      startAt: res.start_at,
      pageUrl: res.page_url,
      externalUrl: res.external_url,
      title: labels.animeTitle,
      episodeLabel: [labels.episodeLine, usedSource].filter(Boolean).join(" · "),
      episodeLink: res.episode_link || body.episode_link,
      episodeNumber: Number.isFinite(epNum) && epNum > 0 ? epNum : labels.number,
      malId: malId ? Number(malId) : null,
      anilistId: anilistId ? Number(anilistId) : null,
      // se o player falhar no load, tenta restantes no cliente
      fallbackCandidates: candidates.filter(
        (c) => c.link !== (res.episode_link || body.episode_link)
      ),
      playMeta: {
        anime_title: body.anime_title,
        episode_title: body.episode_title,
        episode_number: body.episode_number,
        anime_image: body.anime_image,
        season_number: body.season_number,
        mal_id: malId ? Number(malId) : null,
      },
    });
    if (!res.playable) {
      toast("Vídeo direto indisponível — abra no site");
    }
    renderContinueRow();
  } catch (e) {
    toast(e.message || "Não foi possível reproduzir", true);
  }
}

async function playFromHistory(item) {
  const labels = normalizeWatchTitles(
    item.anime_title,
    item.episode_title,
    item.episode_number
  );
  await playEpisode({
    episode_link: item.episode_link,
    preferred_source: item.source_name,
    anime_title: labels.animeTitle,
    episode_title: labels.episodeTitle,
    episode_number: labels.number,
    anime_image: item.anime_image,
    season_number: item.season_number,
    source_color: item.source_color,
    candidates: [
      {
        name: item.source_name || "",
        link: item.episode_link,
        color: item.source_color || "",
      },
    ],
  });
}

// ── Detail ───────────────────────────────────────────────────────────────────

function setText(sel, text) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (el) el.textContent = text ?? "";
}

function setHtml(sel, html) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (el) el.innerHTML = html ?? "";
}

function resetDetailShell() {
  setText("#detail-title", "Carregando…");
  setText("#detail-desc", "");
  setText("#detail-rating", "");
  setHtml("#detail-episodes", "");
  setHtml("#detail-meta-row", "");
  setHtml("#detail-tags", "");
  setHtml("#detail-sources", "");
  const select = $("#season-select");
  if (select) {
    select.innerHTML = "";
    select.onchange = null;
  }
  const alt = $("#detail-alt-title");
  if (alt) {
    alt.hidden = true;
    alt.textContent = "";
  }
  const next = $("#detail-next");
  if (next) {
    next.hidden = true;
    next.textContent = "";
  }
  const franchise = $("#detail-franchise");
  if (franchise) franchise.hidden = true;
  setHtml("#franchise-rail", "");
  setText("#detail-eyebrow", "Anime");
  const posterEl = $("#detail-poster");
  if (posterEl) {
    posterEl.removeAttribute("src");
    posterEl.alt = "";
    posterEl.style.display = "none";
  }
  const bg = $("#detail-bg");
  if (bg) bg.style.backgroundImage = "";
}

async function loadDetail(link, preferredSource, { anilistId = null, titleHint = "" } = {}) {
  if (!link) {
    toast("Link inválido", true);
    navigate("home");
    return;
  }
  const seq = ++state.detailSeq;
  state.detailLink = link;
  resetDetailShell();

  try {
    await waitSourcesReady();
    if (seq !== state.detailSeq) return;
    const detail = await api.anime(link);
    if (seq !== state.detailSeq) return;
    if (!detail?.title) {
      throw new Error("Anime não encontrado");
    }
    state.detail = detail;
    state.detailPreferred = preferredSource || "";
    state.detailMeta = null;
    state.detailEpisodeMeta = {};
    renderDetail(detail, preferredSource);

    // AniList é opcional e nunca bloqueia / limpa a ficha da fonte
    const title = titleHint || detail.title || "";
    enrichDetailWithAniList(title, anilistId, seq).catch(() => {});
  } catch (e) {
    if (seq !== state.detailSeq) return;
    toast(e.message || "Não foi possível abrir o anime", true);
    navigate("home");
  }
}

/** Remove ruído típico de título de fonte BR antes de consultar AniList. */
function cleanTitleForAniList(title) {
  let t = String(title || "").trim();
  if (!t) return "";
  const noise = [
    /\btodos\s+os\s+epis[oó]dios?\b.*$/i,
    /\ball\s+episodes?\b.*$/i,
    /\bonline\b.*$/i,
    /\bassistir\b.*$/i,
    /\bcompleto\b/gi,
    /\bdublado\b/gi,
    /\blegendado\b/gi,
    /\bhd\b/gi,
    /\bfull\s*hd\b/gi,
    /\b\d{3,4}p\b/gi,
  ];
  for (const re of noise) t = t.replace(re, " ");
  t = t.replace(/\s*[\-|–—:]\s*$/g, "").replace(/\s+/g, " ").trim();
  return t;
}

async function enrichDetailWithAniList(title, anilistId, seq) {
  const cleaned = cleanTitleForAniList(title);
  if (!cleaned && (anilistId == null || anilistId === "")) return;
  try {
    const meta = await api.meta(cleaned || title || "", anilistId);
    if (seq != null && seq !== state.detailSeq) return;
    if (!meta || !state.detail) return;
    // evita aplicar meta se o usuário já abriu outra ficha
    if (state.detailLink && state.detail.link && state.detailLink !== state.detail.link) {
      /* keep — link da fonte pode diferir do state */
    }
    state.detailMeta = meta;
    // mapa de thumbs/títulos por número de episódio
    const map = {};
    for (const ep of meta.episode_thumbs || []) {
      const n = String(ep.number ?? "").trim();
      if (!n) continue;
      map[n] = {
        title: ep.title || "",
        thumbnail: ep.thumbnail || "",
      };
    }
    state.detailEpisodeMeta = map;
    applyAniListMeta(meta);
    // re-render da lista pra aplicar thumbs/títulos únicos
    const select = $("#season-select");
    const seasons = state.detail?.seasons || [];
    if (seasons.length) {
      const idx = select ? Number(select.value) || 0 : 0;
      renderSeasonEpisodes(seasons[idx] || seasons[0]);
    }
  } catch {
    /* meta opcional — ficha da fonte já está renderizada */
  }
}

function applyAniListMeta(meta) {
  if (!meta || !state.detail) return;

  const eyebrow = $("#detail-eyebrow");
  if (eyebrow) {
    const bits = ["Catálogo"];
    if (meta.season_line) bits.push(meta.season_line);
    eyebrow.textContent = bits.join(" · ");
  }

  // fundo: banner AniList se existir
  const bg = $("#detail-bg");
  if (bg && meta.banner) {
    const bannerUrl = imgUrl(meta.banner);
    const img = new Image();
    img.onload = () => { bg.style.backgroundImage = `url('${bannerUrl}')`; };
    img.onerror = () => { bg.style.backgroundImage = ""; };
    img.src = bannerUrl;
  }

  // poster só se a fonte não trouxe imagem útil
  const posterEl = $("#detail-poster");
  const sourceImg = (state.detail.image || "").trim();
  if (posterEl && meta.image && !sourceImg) {
    // Delay poster swap — source image is already rendering, no rush
    setTimeout(() => {
      if (state.detailSeq !== seq) return;
      posterEl.onerror = () => { posterEl.src = PLACEHOLDER_POSTER; };
      posterEl.src = imgUrl(meta.image);
      posterEl.alt = state.detail.title || meta.title || "";
    }, 600);
  }

  const alt = $("#detail-alt-title");
  if (alt) {
    const base = state.detail.title || "";
    const alts = [meta.title_english, meta.title_romaji, meta.title_native]
      .filter(Boolean)
      .filter((t) => t.toLowerCase() !== base.toLowerCase());
    const unique = [...new Set(alts)];
    if (unique.length) {
      alt.hidden = false;
      alt.textContent = unique.slice(0, 2).join(" · ");
    }
  }

  // chips (só adiciona; não apaga título/eps da fonte)
  const row = $("#detail-meta-row");
  if (row) {
    const chips = [];
    if (meta.score != null) {
      chips.push(
        `<span class="meta-chip score">★ ${(Number(meta.score) / 10).toFixed(1)}</span>`
      );
    }
    if (meta.format_label) {
      chips.push(`<span class="meta-chip">${escapeHtml(meta.format_label)}</span>`);
    }
    if (meta.season_line) {
      chips.push(`<span class="meta-chip">${escapeHtml(meta.season_line)}</span>`);
    }
    if (meta.status_label) {
      const st = String(meta.status || "").toLowerCase();
      const cls =
        st === "releasing"
          ? "status-releasing"
          : st === "finished"
            ? "status-finished"
            : "";
      chips.push(
        `<span class="meta-chip ${cls}">${escapeHtml(meta.status_label)}</span>`
      );
    }
    if (meta.episodes) {
      chips.push(`<span class="meta-chip">${meta.episodes} eps</span>`);
    }
    if (meta.duration) {
      chips.push(`<span class="meta-chip">${meta.duration} min</span>`);
    }
    if (meta.studios?.length) {
      chips.push(
        `<span class="meta-chip">${escapeHtml(meta.studios.slice(0, 2).join(" · "))}</span>`
      );
    }
    row.innerHTML = chips.join("");
  }

  // sinopse AniList só se a fonte não tem
  const desc = $("#detail-desc");
  if (desc && meta.description) {
    const current = (desc.textContent || "").trim();
    if (!current || current === "Sem sinopse.") {
      desc.textContent = meta.description;
    }
  }

  // score AniList só se a fonte não tem rating
  const ratingEl = $("#detail-rating");
  if (ratingEl && meta.score != null) {
    const cur = (ratingEl.textContent || "").trim();
    if (!cur) {
      ratingEl.textContent = `★ ${(Number(meta.score) / 10).toFixed(1)}`;
    }
  }

  const tags = $("#detail-tags");
  if (tags && meta.genres_label?.length) {
    tags.innerHTML = meta.genres_label
      .slice(0, 8)
      .map((g) => `<span class="detail-tag">${escapeHtml(g)}</span>`)
      .join("");
  }

  const next = $("#detail-next");
  if (next && meta.next_episode && meta.next_airing_at) {
    const when = formatAiringAt(meta.next_airing_at);
    next.hidden = false;
    next.textContent = `Próximo episódio: ${meta.next_episode}${when ? ` · ${when}` : ""}`;
  } else if (next) {
    next.hidden = true;
    next.textContent = "";
  }

  renderFranchise(meta.franchise || meta.relations || []);
}

function formatAiringAt(unix) {
  if (!unix) return "";
  try {
    const d = new Date(Number(unix) * 1000);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function renderFranchise(items) {
  const section = $("#detail-franchise");
  const rail = $("#franchise-rail");
  if (!section || !rail) return;
  // backend já filtra: atual + só os que existem nas fontes
  const list = (items || []).filter(
    (x) => x && x.title && (x.is_current || x.relation_type === "CURRENT" || x.available)
  );
  // só mostra a seção se houver pelo menos um relacionado além do atual
  const related = list.filter(
    (x) => !(x.is_current || x.relation_type === "CURRENT")
  );
  if (!related.length) {
    section.hidden = true;
    rail.innerHTML = "";
    return;
  }
  section.hidden = false;
  rail.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const item of list.slice(0, 16)) {
    const card = document.createElement("article");
    const isCurrent = !!item.is_current || item.relation_type === "CURRENT";
    const hasSources = (item.sources || []).some((s) => s?.link);
    card.className =
      "franchise-card" +
      (isCurrent ? " is-current" : "") +
      (!isCurrent && hasSources ? " has-link" : "");
    const poster = imgUrl(item.image);
    const sourceNames = (item.sources || []).map((s) => s.name).filter(Boolean);
    const metaLine = [
      item.relation_label,
      sourceNames.slice(0, 2).join(" · "),
      item.season_label && item.year
        ? `${item.season_label} ${item.year}`
        : item.year || item.season_label || "",
      item.format_label,
    ]
      .filter(Boolean)
      .join(" · ");
    card.innerHTML = `
      <div class="franchise-poster" style="${poster ? `background-image:url('${poster}')` : ""}">
        <span class="franchise-rel">${escapeHtml(item.relation_label || "Relacionado")}</span>
      </div>
      <div class="franchise-body">
        <div class="franchise-title">${escapeHtml(item.source_title || item.title)}</div>
        <div class="franchise-meta">${escapeHtml(metaLine)}</div>
      </div>
    `;
    if (!isCurrent && hasSources) {
      card.addEventListener("click", () => {
        const src = item.sources[0];
        navigate(
          `anime?link=${encodeURIComponent(src.link)}&source=${encodeURIComponent(
            src.name || ""
          )}&al=${encodeURIComponent(item.id || "")}&title=${encodeURIComponent(
            item.source_title || item.title
          )}`
        );
      });
    }
    frag.appendChild(card);
  }
  rail.appendChild(frag);
}

function renderDetail(detail, preferredSource) {
  if (!detail) return;

  setText("#detail-title", detail.title || "Sem título");
  const rating = String(detail.rating || "").trim();
  setText("#detail-rating", rating ? `★ ${rating}` : "");
  setText("#detail-desc", detail.description || "Sem sinopse.");

  const poster = imgUrl(detail.image);
  const posterEl = $("#detail-poster");
  if (posterEl) {
    posterEl.alt = detail.title || "";
    posterEl.style.display = "";
    posterEl.loading = "lazy";
    // Defer image load to avoid hammering the proxy alongside other detail fetches
    requestAnimationFrame(() => {
      posterEl.onerror = () => { posterEl.src = PLACEHOLDER_POSTER; };
      posterEl.src = poster || PLACEHOLDER_POSTER;
    });
  }
  const bg = $("#detail-bg");
  if (bg) {
    if (poster) {
      const img = new Image();
      img.onload = () => { bg.style.backgroundImage = `url('${poster}')`; };
      img.onerror = () => { bg.style.backgroundImage = `url('${PLACEHOLDER_POSTER}')`; };
      img.src = poster;
    } else {
      bg.style.backgroundImage = `url('${PLACEHOLDER_POSTER}')`;
    }
  }

  const pills = $("#detail-sources");
  if (pills) {
    pills.innerHTML = preferredSource
      ? `<span class="source-pill">${escapeHtml(preferredSource)}</span>`
      : "";
  }

  const seasons = Array.isArray(detail.seasons) ? detail.seasons : [];
  const select = $("#season-select");
  if (select) {
    select.innerHTML = "";
    select.onchange = null;
  }

  if (!seasons.length) {
    setHtml(
      "#detail-episodes",
      `<div class="empty-state"><strong>Sem episódios</strong>A fonte não enviou a lista de episódios.</div>`
    );
    return;
  }

  if (select) {
    seasons.forEach((s, i) => {
      const opt = document.createElement("option");
      opt.value = String(i);
      const n = s.number ?? i + 1;
      const count = Array.isArray(s.episodes) ? s.episodes.length : 0;
      opt.textContent = count
        ? `Temporada ${n} · ${count} episódios`
        : `Temporada ${n}`;
      select.appendChild(opt);
    });
    select.onchange = () => {
      const idx = Number(select.value);
      renderSeasonEpisodes(seasons[idx]);
    };
  }
  renderSeasonEpisodes(seasons[0]);
}

function renderSeasonEpisodes(season) {
  const grid = $("#detail-episodes");
  if (!grid || !season) return;
  grid.innerHTML = "";
  grid.classList.add("episodes-list");
  const frag = document.createDocumentFragment();
  const epMeta = state.detailEpisodeMeta || {};

  for (const ep of season.episodes || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ep-card";

    const num = resolveEpisodeNumber(ep.number, ep.title, ep.link);
    const labels = normalizeWatchTitles(
      state.detail?.title || "",
      ep.title,
      num
    );
    const meta = epMeta[String(labels.number)] || epMeta[String(num)] || null;

    // thumb: 1) imagem do ep na fonte  2) AniList  3) placeholder (NÃO o poster do anime)
    const rawThumb = (ep.image || "").trim() || (meta?.thumbnail || "").trim();
    const thumb = rawThumb ? imgUrl(rawThumb) : "";

    // título legível
    const generic =
      isOnlyEpisodeLabel(ep.title) ||
      !labels.episodeTitle ||
      labels.episodeTitle.toLowerCase() === `episodio ${labels.number}` ||
      labels.episodeTitle.toLowerCase() === `episódio ${labels.number}`;
    const alTitle = (meta?.title || "").trim();
    let mainLine;
    let subLine = "";
    if (generic && alTitle) {
      mainLine = alTitle;
      subLine = `Episódio ${labels.number}`;
    } else if (generic) {
      mainLine = `Episódio ${labels.number && labels.number !== "?" ? labels.number : "?"}`;
      subLine = "";
    } else {
      mainLine = labels.episodeTitle;
      subLine = `Episódio ${labels.number}`;
    }

    const numLabel =
      labels.number && labels.number !== "?" ? String(labels.number) : "?";

    btn.innerHTML = `
      <div class="ep-thumb" data-thumb="${escapeHtml(thumb)}">
        ${
          thumb
            ? `<span class="ep-num">Ep ${escapeHtml(numLabel)}</span>`
            : `<span class="ep-placeholder-num">${escapeHtml(numLabel)}</span>`
        }
      </div>
      <div class="ep-info">
        <div class="ep-kicker">${escapeHtml(subLine || `Episódio ${numLabel}`)}</div>
        <div class="ep-title">${escapeHtml(mainLine)}</div>
        ${ep.date ? `<div class="ep-date">${escapeHtml(ep.date)}</div>` : ""}
      </div>
      <span class="ep-play-hint" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      </span>
    `;

    // Lazy-load episode thumb via IntersectionObserver
    const thumbEl = btn.querySelector(".ep-thumb");
    if (thumbEl && thumb) {
      const obs = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
          thumbEl.style.backgroundImage = `url('${thumb}')`;
          thumbEl.classList.add("has-img");
          obs.disconnect();
        }
      }, { rootMargin: "200px" });
      obs.observe(thumbEl);
    }
    // se main e kicker ficariam iguais ("Episódio 1" / "Episódio 1"), some o kicker
    if (!subLine && generic && !alTitle) {
      const k = btn.querySelector(".ep-kicker");
      if (k) k.hidden = true;
    } else if (subLine && mainLine === subLine) {
      const k = btn.querySelector(".ep-kicker");
      if (k) k.hidden = true;
    }

    btn.addEventListener("click", () => {
      playEpisode({
        episode_link: ep.link,
        preferred_source: state.detailPreferred,
        anime_title: labels.animeTitle,
        episode_title: alTitle || labels.episodeTitle,
        episode_number: labels.number,
        anime_image: rawThumb || state.detail?.image || "",
        season_number: season.number,
        candidates: [
          {
            name: state.detailPreferred || "",
            link: ep.link,
            color: "",
          },
        ],
      });
    });
    frag.appendChild(btn);
  }
  grid.appendChild(frag);
}

// ── History page ─────────────────────────────────────────────────────────────

async function loadHistoryPage() {
  const grid = $("#history-grid");
  if (!grid) return;
  grid.innerHTML = `<p class="empty-state">Carregando…</p>`;
  try {
    // 1 card por anime (mesma regra da fila da home) — sem duplicar fontes/eps
    const data = await api.history(true);
    const items = dedupeHistoryByAnime(data.items || []);
    if (!items.length) {
      grid.innerHTML = `<div class="empty-state"><strong>Nada aqui ainda</strong>Quando assistir um episódio, ele aparece com o progresso.</div>`;
      return;
    }
    grid.innerHTML = "";
    const frag = document.createDocumentFragment();
    for (const h of items) frag.appendChild(historyCard(h));
    grid.appendChild(frag);
  } catch (e) {
    grid.innerHTML = `<p class="empty-state">${escapeHtml(e.message)}</p>`;
  }
}

// ── Sources ──────────────────────────────────────────────────────────────────

function statusLabel(status, available) {
  const s = (status || (available ? "online" : "offline")).toLowerCase();
  if (s === "online") return { cls: "online", text: "Online" };
  if (s === "offline") return { cls: "offline", text: "Offline" };
  if (s === "checking") return { cls: "checking", text: "Testando" };
  return { cls: "unknown", text: "—" };
}

function formatLatency(ms) {
  if (ms == null || Number.isNaN(Number(ms))) return "—";
  const n = Number(ms);
  if (n < 1000) return `${Math.round(n)} ms`;
  return `${(n / 1000).toFixed(1)} s`;
}

function latencyClass(ms) {
  if (ms == null) return "";
  if (ms < 800) return "good";
  if (ms < 2500) return "warn";
  return "bad";
}

function hostFromUrl(url) {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url.replace(/^https?:\/\//, "").split("/")[0];
  }
}

function formatCheckTime(iso) {
  if (!iso) return "ainda não";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "—";
  }
}

/* ── Source emblem icons (generated dynamically from name + color) ─────────── */

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) { h = ((h << 5) - h) + s.charCodeAt(i); h |= 0; }
  return Math.abs(h);
}

function sourceEmblemSvg(id, color) {
  const c = color || "#666";
  const h = hashStr(id || "");
  // Pick an icon template based on hash, then colorize it
  const templates = [
    // Circle burst
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="6"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/>
    </svg>`,
    // Diamond
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2L2 12l10 10 10-10z"/><path d="M12 6l-4 4 4 4 4-4z"/><circle cx="12" cy="12" r="2"/>
    </svg>`,
    // Hexagon
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><circle cx="12" cy="12" r="3"/>
    </svg>`,
    // Cross with dots
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="5" r="2"/><circle cx="12" cy="19" r="2"/><circle cx="5" cy="12" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="12" cy="12" r="4"/>
    </svg>`,
    // Pulsar / target
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="1" fill="${c}"/>
    </svg>`,
    // Waves
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 12c2-2 4-4 6 0s4 4 6 0 4-4 6 0"/><path d="M3 18c2-2 4-4 6 0s4 4 6 0 4-4 6 0"/><circle cx="12" cy="6" r="2"/>
    </svg>`,
    // Layers
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2L2 7l10 5 10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
    </svg>`,
    // Compass
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="9"/><path d="M12 7v2"/><path d="M12 15v2"/><path d="M7 12h2"/><path d="M15 12h2"/><circle cx="12" cy="12" r="3" fill="${c}" opacity="0.3"/>
    </svg>`,
  ];

  const idx = h % templates.length;
  return templates[idx];
}

/* ── Signal strength bars ─────────────────────────────────────────────────── */

function signalBarsHtml(s) {
  const ms = s.latency_ms;
  const bars = [];
  const levels = ms == null ? [0, 0, 0, 0, 0]
    : ms < 200  ? [1, 1, 1, 1, 1]
    : ms < 500  ? [1, 1, 1, 1, 0]
    : ms < 1000 ? [1, 1, 1, 0, 0]
    : ms < 2500 ? [1, 1, 0, 0, 0]
    : [1, 0, 0, 0, 0];
  const heights = [6, 9, 12, 15, 18];
  for (let i = 0; i < 5; i++) {
    const on = levels[i] && s.available;
    const cls = !s.enabled ? "" : !on ? "is-bad" : ms < 500 ? "is-on" : ms < 1500 ? "is-warn" : "is-bad";
    bars.push(`<span class="signal-bar ${cls}" style="height:${heights[i]}px;opacity:${on ? 1 : s.enabled ? 0.2 : 0.08}"></span>`);
  }
  return `<span class="signal-bars">${bars.join("")}</span>`;
}

/* ── Dashboard ────────────────────────────────────────────────────────────── */

function renderSourcesDashboard(items) {
  const el = $("#sources-dashboard");
  if (!el) return;
  const total = items.length;
  const online = items.filter(s => s.enabled && s.available).length;
  const offline = items.filter(s => s.enabled && !s.available).length;
  const disabled = items.filter(s => !s.enabled).length;
  el.innerHTML = `
    <div class="dash-stat total"><span class="dash-stat-value">${total}</span><span class="dash-stat-label">Total</span></div>
    <div class="dash-stat online"><span class="dash-stat-value">${online}</span><span class="dash-stat-label">Online</span></div>
    <div class="dash-stat offline"><span class="dash-stat-value">${offline}</span><span class="dash-stat-label">Offline</span></div>
    <div class="dash-stat disabled"><span class="dash-stat-value">${disabled}</span><span class="dash-stat-label">Desativadas</span></div>
  `;
}

/* ── Source card ──────────────────────────────────────────────────────────── */

function updateSourceCard(card, updated) {
  const st = statusLabel(updated.status, updated.available);
  const dot = card.querySelector(".status-dot");
  if (dot) { dot.className = `status-dot ${st.cls}`; }

  // Update signal bars
  const barsWrap = card.querySelector(".signal-bars-wrap");
  if (barsWrap) barsWrap.innerHTML = signalBarsHtml(updated);

  const errEl = card.querySelector(".source-error");
  if (updated.error && !updated.available) {
    if (!errEl) {
      const p = document.createElement("p");
      p.className = "source-error";
      p.innerHTML = `${escapeHtml(updated.error)}`;
      card.appendChild(p);
    } else {
      errEl.innerHTML = `${escapeHtml(updated.error)}`;
    }
  } else if (errEl) {
    errEl.remove();
  }
  card.className = `source-card is-${st.cls}${updated.enabled === false ? " is-disabled" : ""}`;
  card.classList.remove("is-busy");
}

function renderSourceCard(s) {
  const st = statusLabel(s.status, s.available);
  const card = document.createElement("article");
  card.className = `source-card is-${st.cls}${s.enabled ? "" : " is-disabled"}`;
  card.dataset.id = s.identifier;

  const host = hostFromUrl(s.base_url);
  const capBadges = [
    s.has_search ? `<span class="source-cap-badge">Busca</span>` : "",
    s.has_details ? `<span class="source-cap-badge">Detalhes</span>` : "",
  ].filter(Boolean).join("");

  const emblem = sourceEmblemSvg(s.identifier, s.color || "#666");

  card.innerHTML = `
    <div class="source-card-body">
      <span class="source-emblem" style="--src-color:${s.color || "#666"}">${emblem}</span>

      <div class="source-card-titles">
        <div class="source-card-name">${escapeHtml(s.name)}</div>
        <div class="source-card-host">${escapeHtml(host || s.identifier)}</div>
        ${capBadges ? `<div class="source-caps">${capBadges}</div>` : ""}
      </div>

      <div class="signal-bars-wrap">${signalBarsHtml(s)}</div>

      <div class="source-card-controls">
        <span class="status-dot ${st.cls}"></span>
        <button type="button" class="btn-ping" data-ping="${escapeHtml(s.identifier)}" title="Testar agora" aria-label="Testar ${escapeHtml(s.name)}">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>
        </button>
        <label class="switch source-toggle" title="${s.enabled ? "Desativar" : "Ativar"} ${escapeHtml(s.name)}">
          <input type="checkbox" ${s.enabled ? "checked" : ""} data-id="${escapeHtml(s.identifier)}" />
          <span class="switch-slider"></span>
        </label>
      </div>
    </div>
    ${s.error && !s.available ? `<p class="source-error">${escapeHtml(s.error)}</p>` : ""}
  `;

  const input = card.querySelector("input[type=checkbox]");
  input?.addEventListener("change", async () => {
    const enabled = input.checked;
    input.disabled = true;
    card.classList.add("is-busy");
    try {
      await api.setSource(s.identifier, enabled);
      toast(`${s.name} ${enabled ? "ativada" : "desativada"} · atualizando…`);
      state.catalogDirty = true;
      state.episodes = [];
      await loadSources();
      reloadAfterSourcesChange();
    } catch (e) {
      input.checked = !enabled;
      toast(e.message || "Não foi possível alterar a fonte", true);
      input.disabled = false;
      card.classList.remove("is-busy");
    }
  });

  card.querySelector("[data-ping]")?.addEventListener("click", async (e) => {
    e.preventDefault(); e.stopPropagation();
    const btn = e.currentTarget; btn.disabled = true;
    card.classList.add("is-busy");
    const dot = card.querySelector(".status-dot");
    if (dot) dot.className = "status-dot checking";
    try {
      const updated = await api.refreshSourceHealth(s.identifier);
      updateSourceCard(card, updated);
      btn.disabled = false;
      toast(updated.available
        ? `${updated.name} online · ${formatLatency(updated.latency_ms)}`
        : `${updated.name} offline${updated.error ? ` (${updated.error})` : ""}`,
        !updated.available);
    } catch (err) {
      toast(err.message || "Teste falhou", true);
      btn.disabled = false;
      card.classList.remove("is-busy");
    }
  });

  return card;
}

/* ── Load sources ─────────────────────────────────────────────────────────── */

async function loadSources({ recheck = false } = {}) {
  const list = $("#sources-list");
  if (!list) return;
  list.innerHTML = `<div class="sources-empty">Carregando fontes…</div>`;
  try {
    await waitSourcesReady();
    let data;
    if (recheck) {
      toast("Testando fontes…");
      data = await api.refreshSourcesHealth();
    } else {
      data = await api.sources();
    }
    const items = data.items || [];
    if (!items.length) {
      list.innerHTML = `<div class="sources-empty"><strong>Nenhuma fonte</strong>Nenhum site foi encontrado.</div>`;
      $("#sources-dashboard").innerHTML = "";
      return;
    }

    renderSourcesDashboard(items);

    const groups = [
      { label: "Online", items: items.filter(s => s.enabled && s.available), cls: "group-online" },
      { label: "Com problema", items: items.filter(s => s.enabled && !s.available && s.status !== "unknown"), cls: "group-offline" },
      { label: "Não verificadas", items: items.filter(s => s.enabled && s.status === "unknown" && !s.available), cls: "group-unknown" },
      { label: "Desativadas", items: items.filter(s => !s.enabled), cls: "group-disabled" },
    ].filter(g => g.items.length > 0);

    list.innerHTML = "";
    for (const group of groups) {
      const section = document.createElement("div");
      section.className = `sources-group ${group.cls}`;
      section.innerHTML = `<h4 class="sources-group-label">${group.label} <span class="sources-group-count">${group.items.length}</span></h4>`;
      for (const s of group.items) {
        section.appendChild(renderSourceCard(s));
      }
      list.appendChild(section);
    }
  } catch (e) {
    list.innerHTML = `<div class="sources-empty"><strong>Erro</strong>${escapeHtml(e.message)}</div>`;
  }
}

// ── Search ───────────────────────────────────────────────────────────────────

function openSearch() {
  const ov = $("#search-overlay");
  if (!ov) return;
  ov.hidden = false;
  $("#search-input")?.focus();
  // Show enabled sources
  updateSearchSourceBar();
}

async function updateSearchSourceBar() {
  const el = $("#search-sources");
  if (!el) return;
  try {
    const data = await api.sources();
    const enabled = (data.items || []).filter(s => s.enabled);
    const online = enabled.filter(s => s.available);
    const count = enabled.length;
    if (!count) {
      el.innerHTML = `<span class="src-bar-none">Nenhuma fonte ativa</span>`;
      return;
    }
    const chips = enabled.map(s => {
      const cls = s.available ? "src-chip-on" : "src-chip-off";
      return `<span class="src-chip ${cls}" style="--src-color:${s.color || "#666"}">${escapeHtml(s.name)}</span>`;
    }).join("");
    el.innerHTML = `<span class="src-bar-label">Fontes ativas (${online.length}/${count})</span>${chips}`;
  } catch {
    el.innerHTML = "";
  }
}

function closeSearch(clear = true) {
  const ov = $("#search-overlay");
  if (!ov) return;
  ov.hidden = true;
  if (clear) {
    const input = $("#search-input");
    if (input) input.value = "";
    $("#search-results").innerHTML = "";
  }
}

async function runSearch(q) {
  const box = $("#search-results");
  if (!box) return;
  if (!q || q.length < 2) {
    box.innerHTML = `<p class="search-status">Digite pelo menos 2 letras</p>`;
    return;
  }
  box.innerHTML = `<p class="search-status">Buscando…</p>`;
  try {
    await waitSourcesReady();
    const data = await api.search(q);
    const items = data.items || [];
    if (!items.length) {
      box.innerHTML = `<p class="search-status">Nada para “${escapeHtml(q)}”</p>`;
      return;
    }
    box.innerHTML = "";
    const frag = document.createDocumentFragment();
    for (const a of items) frag.appendChild(animeCard(a));
    box.appendChild(frag);
  } catch (e) {
    box.innerHTML = `<p class="search-status">${escapeHtml(e.message)}</p>`;
  }
}

// ── Boot ─────────────────────────────────────────────────────────────────────

function bindUi() {
  initPlayer({
    onClose: () => {
      if (state.route === "home") renderContinueRow();
      if (state.route === "history") loadHistoryPage();
    },
  });

  window.addEventListener("hashchange", onRoute);

  for (const sel of ["#btn-search", "#btn-search-mobile"]) {
    $(sel)?.addEventListener("click", openSearch);
  }
  $("#search-close")?.addEventListener("click", () => closeSearch());
  $("#search-input")?.addEventListener("input", (e) => {
    clearTimeout(state.searchTimer);
    const q = e.target.value.trim();
    state.searchTimer = setTimeout(() => runSearch(q), 350);
  });

  $("#hero-play")?.addEventListener("click", () => {
    if (state.heroItem) onEpisodeClick(state.heroItem);
  });
  $("#hero-info")?.addEventListener("click", () => {
    const item = state.heroItem;
    if (!item) return;
    const sources = (item.sources || []).filter((s) => s?.link);
    // Mesma regra do card: áudio primeiro, depois fonte
    if (hasAudioChoice(sources)) {
      openAudioChoiceModal(item.title, sources, (picked) => {
        if (picked.length > 1) {
          openSourceModal(item.title, picked, (src) => {
            playEpisodeFromSources(item, [src]);
          });
          return;
        }
        playEpisodeFromSources(item, picked);
      });
      return;
    }
    if (sources.length > 1) {
      openSourceModal(item.title, sources, (src) => {
        playEpisodeFromSources(item, [src]);
      });
      return;
    }
    onEpisodeClick(item);
  });

  $("#detail-back")?.addEventListener("click", () => navigate("home"));
  $("#btn-genre-back")?.addEventListener("click", () => {
    backToGenrePick();
  });

  // preferência salva: cruzamento desligado por padrão
  state.calendarCheckSources = loadCalendarCheckPref();
  const checkSourcesEl = $("#calendar-check-sources");
  if (checkSourcesEl) {
    checkSourcesEl.checked = !!state.calendarCheckSources;
    checkSourcesEl.addEventListener("change", async () => {
      state.calendarCheckSources = !!checkSourcesEl.checked;
      saveCalendarCheckPref(state.calendarCheckSources);
      state.calendarCache = null;
      await loadCalendarPage({ force: true });
      toast(
        state.calendarCheckSources
          ? "Cruzamento com fontes ligado"
          : "Cruzamento com fontes desligado"
      );
    });
  }

  $("#btn-refresh-calendar")?.addEventListener("click", async () => {
    const btn = $("#btn-refresh-calendar");
    if (btn) btn.disabled = true;
    try {
      await loadCalendarPage({ force: true });
      toast("Calendário atualizado");
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  $$("#calendar-range .range-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const days = Number(btn.dataset.days) || 7;
      if (days === state.calendarDays && !state.calendarLoading) {
        await loadCalendarPage({ force: true });
        return;
      }
      state.calendarDays = days;
      state.calendarCache = null;
      syncCalendarRangeButtons();
      await loadCalendarPage({ force: true });
    });
  });

  $("#btn-clear-history")?.addEventListener("click", async () => {
    if (!confirm("Limpar todo o histórico?")) return;
    try {
      await api.clearHistory();
      toast("Histórico limpo");
      loadHistoryPage();
      renderContinueRow();
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#source-modal-cancel")?.addEventListener("click", () => {
    $("#source-modal").hidden = true;
  });
  $("#source-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "source-modal") e.target.hidden = true;
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "s" || e.key === "S") {
      if (e.target.matches("input, textarea, select")) return;
      if (!$("#player-modal")?.hidden) return;
      e.preventDefault();
      openSearch();
    }
    if (e.key === "Escape") {
      if (!$("#search-overlay")?.hidden) closeSearch();
      if (!$("#source-modal")?.hidden) $("#source-modal").hidden = true;
    }
  });
}

bindUi();
onRoute();
