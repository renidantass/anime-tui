/**
 * anishelf — UI web pensada pra quem assiste anime
 */

import { api, imgUrl } from "./api.js";
import { initPlayer, openPlayer, closePlayer } from "./player.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

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
  genreMoreOpen: false,
  /** Cache client: genre → { items, at } */
  genreCache: {},
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
  return `
    <span class="audio-choice-chip" title="${title}">
      <i class="card-audio-pill is-leg">LEG</i>
      <i class="card-audio-pill is-dub">DUB</i>
      <span class="audio-choice-chip-label">áudio</span>
    </span>`;
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
  return Array.from({ length: count }, () => `<div class="skel"></div>`).join("");
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
  el.innerHTML = `
    <div class="card-poster ${poster ? "has-img" : ""}" style="${posterStyle(poster)}">
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
        ${audioChoiceBadge(item.sources, "inline")}
        ${pillHtml(item.sources)}
        ${item.date ? `<span>${escapeHtml(item.date)}</span>` : ""}
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
  el.innerHTML = `
    <div class="card-poster ${poster ? "has-img" : ""}" style="${posterStyle(poster)}">
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
  el.innerHTML = `
    <div class="card-poster ${poster ? "has-img" : ""}" style="${posterStyle(poster)}">
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

async function waitSourcesReady(maxMs = 45000) {
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
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function loadHome({ silent = false } = {}) {
  const seq = ++state.catalogReloadSeq;
  state.loadingCatalog = true;
  state.catalogDirty = true;
  const scroller = $("#episodes-scroller");
  if (scroller) {
    scroller.innerHTML = skeletonShelf(8);
  }
  const count = $("#episodes-count");
  if (count) count.textContent = "…";
  const heroTitle = $("#hero-title");
  if (heroTitle && !state.episodes.length) {
    heroTitle.textContent = "Carregando…";
  }
  try {
    if (!silent) toast("Carregando episódios…");
    await waitSourcesReady();
    const data = await api.episodes();
    // ignora resposta antiga se outro reload foi pedido no meio
    if (seq !== state.catalogReloadSeq) return;
    state.episodes = data.items || [];
    state.catalogDirty = false;
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
  const popular = $("#genre-popular");
  if (popular) {
    popular.innerHTML = Array.from(
      { length: 6 },
      () => `<div class="skel skel-genre-tile"></div>`
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
  const { popular, others } = splitGenres();
  fillGenreGrid($("#genre-popular"), popular, { showGo: true });
  fillGenreGrid($("#genre-others"), others, { showGo: false });

  const moreBtn = $("#btn-genre-more");
  const morePanel = $("#genre-more-panel");
  if (moreBtn) {
    moreBtn.hidden = !others.length;
    moreBtn.setAttribute("aria-expanded", state.genreMoreOpen ? "true" : "false");
    moreBtn.textContent = state.genreMoreOpen
      ? "Ocultar outros gêneros"
      : `Mais gêneros${others.length ? ` (${others.length})` : ""}`;
  }
  if (morePanel) {
    morePanel.hidden = !state.genreMoreOpen || !others.length;
  }
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
    btn.innerHTML = `
      <span class="genre-tile-label">${escapeHtml(g.label || g.name)}</span>
      ${showGo ? `<span class="genre-tile-go">Ver animes →</span>` : ""}
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
  const t = $("#genre-active-title");
  const k = $("#genre-kicker");
  if (t) t.textContent = title || "—";
  if (k) {
    k.textContent = kicker || "";
    k.hidden = true; // evitado de propósito — título único basta
  }
  if (title) setTopbar("", title);
}

async function loadGenreBrowse(genre, { silent = false, force = false } = {}) {
  if (!genre) return;
  const seq = ++state.genreSeq;
  state.genreLoading = true;
  state.genreItems = [];
  state.genreCatalog = [];
  setGenreStep("results");
  renderGenrePickers();

  const scroller = $("#genre-scroller");
  const count = $("#genre-count");
  const label = genreLabel(genre);
  setExploreHead(label, "Carregando");
  if (count) count.textContent = "…";

  // cache client (resultado já resolvido)
  const cached = state.genreCache[genre];
  if (!force && cached && Date.now() - cached.at < GENRE_CACHE_MS && cached.items?.length) {
    if (seq !== state.genreSeq) return;
    state.genreItems = cached.items;
    showGenreLoading(false);
    renderGenreAvailable(cached.items, { label, animated: false });
    setExploreHead(label, "Nas suas fontes");
    state.genreLoading = false;
    renderGenrePickers();
    return;
  }

  showGenreLoading(true, {
    title: `Carregando ${label}…`,
    sub: "Buscando no catálogo",
    indeterminate: true,
  });
  if (scroller) {
    scroller.innerHTML = skeletonShelf(10);
  }

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
        await loadGenreBrowseLegacy(genre, { seq, silent, label, scroller, count });
        return;
      }
      throw catalogErr;
    }

    if (seq !== state.genreSeq) return;
    const candidates = catalog.items || [];
    state.genreCatalog = candidates;
    setExploreHead(label, "Conferindo fontes");
    showGenreLoading(true, {
      title: `Conferindo ${label}…`,
      sub: "Vendo o que existe nas fontes",
      progress: 8,
    });
    renderGenreChecking(candidates);

    if (!candidates.length) {
      if (scroller) {
        scroller.innerHTML = `<div class="empty-state"><strong>Nada neste gênero</strong>Não há títulos listados para ${escapeHtml(label)}.</div>`;
      }
      if (count) count.textContent = "0";
      showGenreLoading(false);
      return;
    }

    // 2) resolve em lotes — UI preenche conforme chega
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
      const pct = Math.round((done / queue.length) * 100);
      const statusTitle = `Conferindo… ${done}/${queue.length}`;
      const statusSub =
        found.length > 0
          ? `${found.length} disponível${found.length === 1 ? "" : "is"}`
          : "Procurando títulos nas fontes ativas";
      // se já tem cards, só atualiza o pill (não reabre o overlay)
      if (found.length > 0) {
        setGenreStatus(true, `${statusTitle} · ${statusSub}`);
      } else {
        showGenreLoading(true, {
          title: statusTitle,
          sub: statusSub,
          progress: pct,
        });
      }
      try {
        const res = await api.genreResolve(
          batch.map((c) => ({
            id: c.id,
            title: c.title,
            titles: c.titles || [c.title],
            image: c.image || "",
            score: c.score ?? null,
            banner: c.banner || "",
            season: c.season || "",
            season_label: c.season_label || "",
            season_line: c.season_line || "",
            year: c.year ?? null,
            format: c.format || "",
            format_label: c.format_label || "",
            status: c.status || "",
            status_label: c.status_label || "",
            episodes: c.episodes ?? null,
            studios: c.studios || [],
            genres: c.genres || [],
            genres_label: c.genres_label || [],
            description: c.description || "",
          }))
        );
        if (seq !== state.genreSeq) return;
        for (const item of res.items || []) {
          const key = (item.title || "").trim().toLowerCase();
          if (!key || seenTitles.has(key)) continue;
          seenTitles.add(key);
          found.push(item);
          // primeiros hits: esconde overlay grande, mantém pill de status
          if (found.length === 1) {
            const loadingEl = $("#genre-loading");
            if (loadingEl) loadingEl.hidden = true;
            $("#explore-panel")?.classList.remove("is-loading");
          }
          appendGenreCard(item);
          if (count) count.textContent = `${found.length} disponíveis`;
        }
      } catch (batchErr) {
        if (
          batchErr.status === 404 ||
          batchErr.status === 405 ||
          /not found|method not allowed/i.test(batchErr.message || "")
        ) {
          resolveUnsupported = true;
          break;
        }
        console.warn("resolve batch failed", batchErr);
      }
    }

    if (resolveUnsupported) {
      await loadGenreBrowseLegacy(genre, { seq, silent, label, scroller, count });
      return;
    }

    if (seq !== state.genreSeq) return;
    state.genreItems = found;
    state.genreCache[genre] = { items: found, at: Date.now() };

    // remove placeholders restantes
    scroller?.querySelectorAll(".card.is-checking").forEach((n) => n.remove());

    if (!found.length) {
      if (scroller) {
        scroller.innerHTML = `<div class="empty-state"><strong>Nada nas fontes</strong>Há ${queue.length} títulos de ${escapeHtml(label)} no catálogo, mas nenhum está nas fontes ativas.</div>`;
      }
      if (count) count.textContent = "0";
      setExploreHead(label, "Nada encontrado");
    } else {
      if (count) count.textContent = `${found.length}`;
      setExploreHead(label, "Nas suas fontes");
      if (!silent) {
        toast(`${found.length} anime${found.length === 1 ? "" : "s"} de ${label}`);
      }
    }
  } catch (e) {
    if (seq !== state.genreSeq) return;
    if (!silent) toast(e.message || "Não foi possível buscar o gênero", true);
    if (scroller) {
      scroller.innerHTML = `<div class="empty-state"><strong>Busca falhou</strong>${escapeHtml(e.message || "Tente outro gênero.")}</div>`;
    }
    if (count) count.textContent = "0";
  } finally {
    if (seq === state.genreSeq) {
      state.genreLoading = false;
      showGenreLoading(false);
      renderGenrePickers();
    }
  }
}

/** Fallback único request: /api/genres/browse */
async function loadGenreBrowseLegacy(genre, { seq, silent, label, scroller, count }) {
  setExploreHead(label, "Buscando");
  showGenreLoading(true, {
    title: `Carregando ${label}…`,
    sub: "Pode levar alguns segundos",
    indeterminate: true,
  });
  if (scroller) scroller.innerHTML = skeletonShelf(10);
  if (count) count.textContent = "…";
  try {
    const data = await api.browseGenre(genre, 1, 16);
    if (seq !== state.genreSeq) return;
    const items = data.items || [];
    state.genreItems = items;
    state.genreCache[genre] = { items, at: Date.now() };
    renderGenreAvailable(items, { label: data.label || label, animated: true });
    if (!items.length) {
      setExploreHead(data.label || label, "Nada encontrado");
    } else {
      setExploreHead(data.label || label, "Nas suas fontes");
      if (!silent) toast(`${items.length} anime${items.length === 1 ? "" : "s"} de ${data.label || label}`);
    }
  } catch (e) {
    if (seq !== state.genreSeq) return;
    if (!silent) toast(e.message || "Não foi possível buscar o gênero", true);
    if (scroller) {
      scroller.innerHTML = `<div class="empty-state"><strong>Busca falhou</strong>${escapeHtml(e.message || "Tente outro gênero.")}</div>`;
    }
    if (count) count.textContent = "0";
  } finally {
    if (seq === state.genreSeq) {
      state.genreLoading = false;
      showGenreLoading(false);
      renderGenrePickers();
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
      ${escapeHtml(time)}
      ${relative ? `<small>${escapeHtml(relative)}</small>` : ""}
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
  if (bg && item.image) {
    bg.style.backgroundImage = `url('${imgUrl(item.image)}')`;
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
  $("#hero-desc").textContent =
    item.date
      ? `Lançado em ${item.date}`
      : "Pronto para assistir. Se uma fonte falhar, tentamos outra.";
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

  toast(
    candidates.length > 1
      ? `Abrindo vídeo (${candidates.length} fontes)…`
      : "Abrindo vídeo…"
  );

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
    const malId =
      payload.mal_id ||
      state.detailMeta?.mal_id ||
      null;
    const anilistId =
      payload.anilist_id ||
      state.detailMeta?.id ||
      null;
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
    bg.style.backgroundImage = `url('${imgUrl(meta.banner)}')`;
  }

  // poster só se a fonte não trouxe imagem útil
  const posterEl = $("#detail-poster");
  const sourceImg = (state.detail.image || "").trim();
  if (posterEl && meta.image && !sourceImg) {
    posterEl.src = imgUrl(meta.image);
    posterEl.alt = state.detail.title || meta.title || "";
    posterEl.style.display = "";
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
    posterEl.onerror = () => {
      posterEl.style.display = "none";
      posterEl.removeAttribute("src");
    };
    if (poster) {
      posterEl.src = poster;
      posterEl.alt = detail.title || "";
      posterEl.style.display = "";
    } else {
      posterEl.removeAttribute("src");
      posterEl.alt = "";
      posterEl.style.display = "none";
    }
  }
  const bg = $("#detail-bg");
  if (bg) {
    bg.style.backgroundImage = poster ? `url('${poster}')` : "";
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
      <div class="ep-thumb ${thumb ? "has-img" : "is-placeholder"}" ${
        thumb ? `style="background-image:url('${thumb}')"` : ""
      }>
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

function formatUptime(pct) {
  if (pct == null || Number.isNaN(Number(pct))) return "—";
  return `${Number(pct).toFixed(0)}%`;
}

function uptimeClass(pct) {
  if (pct == null) return "";
  if (pct >= 90) return "good";
  if (pct >= 60) return "warn";
  return "bad";
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

function sourceInitials(name) {
  const parts = String(name || "?").trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function renderSourceCard(s) {
  const st = statusLabel(s.status, s.available);
  const uptime = s.uptime_percent;
  const card = document.createElement("article");
  card.className = `source-card is-${st.cls}`;
  card.dataset.id = s.identifier;

  const caps = [
    s.has_search ? "busca" : null,
    s.has_details ? "ficha" : null,
    s.enabled ? "ligada" : "desligada",
  ].filter(Boolean);

  card.innerHTML = `
    <div class="source-card-main">
      <div class="source-card-head">
        <span class="source-brand" style="--brand:${s.color || "#666"};background:${s.color || "#666"}">${escapeHtml(sourceInitials(s.name))}</span>
        <div class="source-card-titles">
          <div class="source-card-name">${escapeHtml(s.name)}</div>
          <div class="source-card-host">${escapeHtml(hostFromUrl(s.base_url) || s.identifier)}</div>
        </div>
        <span class="status-pill ${st.cls}">${st.text}</span>
      </div>
      <div class="source-metrics">
        <div class="metric">
          <span class="metric-label">Disponível</span>
          <div class="metric-value ${uptimeClass(uptime)}">${escapeHtml(formatUptime(uptime))}</div>
          <div class="uptime-bar" title="Testes recentes">
            <i style="width:${uptime != null ? Math.max(0, Math.min(100, uptime)) : 0}%"></i>
          </div>
        </div>
        <div class="metric">
          <span class="metric-label">Latência</span>
          <div class="metric-value ${latencyClass(s.latency_ms)}">${escapeHtml(formatLatency(s.latency_ms))}</div>
        </div>
        <div class="metric">
          <span class="metric-label">Último teste</span>
          <div class="metric-value" style="font-size:0.85rem">${escapeHtml(formatCheckTime(s.last_check_at))}</div>
        </div>
      </div>
      <div class="source-caps">
        ${caps.map((c) => `<span class="cap-chip">${escapeHtml(c)}</span>`).join("")}
        ${s.checks_total ? `<span class="cap-chip">${s.checks_ok}/${s.checks_total} ok</span>` : ""}
      </div>
      ${s.error && !s.available ? `<p class="source-error">Erro: ${escapeHtml(s.error)}</p>` : ""}
    </div>
    <div class="source-card-aside">
      <div class="source-toggle-wrap">
        <span class="source-toggle-label">${s.enabled ? "Ligada" : "Desligada"}</span>
        <label class="switch" title="Usar esta fonte">
          <input type="checkbox" ${s.enabled ? "checked" : ""} data-id="${escapeHtml(s.identifier)}" />
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="source-card-actions">
        <button type="button" class="btn-icon-sm" data-ping="${escapeHtml(s.identifier)}" title="Testar agora">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>
          </svg>
          Testar
        </button>
      </div>
    </div>
  `;

  const input = card.querySelector("input[type=checkbox]");
  const labelEl = card.querySelector(".source-toggle-label");

  input?.addEventListener("change", async () => {
    const enabled = input.checked;
    input.disabled = true;
    card.classList.add("is-busy");
    try {
      await api.setSource(s.identifier, enabled);
      if (labelEl) labelEl.textContent = enabled ? "Ligada" : "Desligada";
      toast(`${s.name} ${enabled ? "ativada" : "desativada"} · atualizando…`);
      state.catalogDirty = true;
      state.episodes = [];
      await reloadAfterSourcesChange();
    } catch (e) {
      input.checked = !enabled;
      toast(e.message || "Não foi possível alterar a fonte", true);
    } finally {
      input.disabled = false;
      card.classList.remove("is-busy");
    }
  });

  card.querySelector("[data-ping]")?.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const btn = e.currentTarget;
    btn.disabled = true;
    card.classList.add("is-busy");
    const pill = card.querySelector(".status-pill");
    if (pill) {
      pill.className = "status-pill checking";
      pill.textContent = "Testando";
    }
    try {
      const updated = await api.refreshSourceHealth(s.identifier);
      // re-render only this card
      const next = renderSourceCard(updated);
      card.replaceWith(next);
      toast(
        updated.available
          ? `${updated.name} online · ${formatLatency(updated.latency_ms)}`
          : `${updated.name} offline${updated.error ? ` (${updated.error})` : ""}`,
        !updated.available
      );
    } catch (err) {
      toast(err.message || "Teste falhou", true);
      btn.disabled = false;
      card.classList.remove("is-busy");
    }
  });

  return card;
}

async function loadSources({ recheck = false } = {}) {
  const list = $("#sources-list");
  if (!list) return;
  list.innerHTML = `<div class="empty-state">Carregando fontes…</div>`;
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
    list.innerHTML = "";
    if (!items.length) {
      list.innerHTML = `<div class="empty-state"><strong>Nenhuma fonte</strong>Nenhum site foi encontrado.</div>`;
      return;
    }
    for (const s of items) {
      list.appendChild(renderSourceCard(s));
    }
  } catch (e) {
    list.innerHTML = `<div class="empty-state"><strong>Erro</strong>${escapeHtml(e.message)}</div>`;
  }
}

// ── Search ───────────────────────────────────────────────────────────────────

function openSearch() {
  const ov = $("#search-overlay");
  if (!ov) return;
  ov.hidden = false;
  $("#search-input")?.focus();
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

  $("#btn-genre-more")?.addEventListener("click", () => {
    state.genreMoreOpen = !state.genreMoreOpen;
    renderGenrePickers();
  });
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

  $("#btn-refresh-health")?.addEventListener("click", async () => {
    const btn = $("#btn-refresh-health");
    if (btn) btn.disabled = true;
    try {
      await loadSources({ recheck: true });
    } finally {
      if (btn) btn.disabled = false;
    }
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
