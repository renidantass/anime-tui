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
  detailSources: [],
  detailPreferred: "",
  searchTimer: null,
  route: "home",
  /** Catálogo precisa ser buscado de novo (ex.: fontes mudaram). */
  catalogDirty: true,
  loadingCatalog: false,
  /** Reload do catálogo agendado após mudança de fontes. */
  catalogReloadSeq: 0,
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
  if (e) e.textContent = eyebrow;
  if (t) t.textContent = title;
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
    state.route = "detail";
    setActiveNav("home");
    setTopbar("Ficha", "Detalhes do anime");
    showView("view-detail");
    await loadDetail(link, source);
    return;
  }

  if (path === "history") {
    state.route = "history";
    setActiveNav("history");
    setTopbar("Watch history", "Sua fila");
    showView("view-history");
    await loadHistoryPage();
    return;
  }

  if (path === "sources") {
    state.route = "sources";
    setActiveNav("sources");
    setTopbar("Providers", "Fontes ativas");
    showView("view-sources");
    await loadSources();
    return;
  }

  state.route = "home";
  setActiveNav("home");
  setTopbar("Tonight’s shelf", "Novos drops");
  showView("view-home");
  if (state.catalogDirty || !state.episodes.length) {
    await loadHome();
  } else {
    await renderContinueRow();
  }
}

// ── Cards ────────────────────────────────────────────────────────────────────

function pillHtml(sources) {
  return (sources || [])
    .slice(0, 3)
    .map((s) => {
      const color = s.color || "#666";
      return `<span class="source-pill" style="--pill:${color}" data-color>${escapeHtml(s.name)}</span>`;
    })
    .join("");
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
  el.className = "card";
  el.innerHTML = `
    <div class="card-poster ${poster ? "has-img" : ""}" style="${posterStyle(poster)}">
      ${corner}
      <div class="card-play">
        <button type="button" class="btn-play-sm" aria-label="Assistir">${playIcon(18)}</button>
      </div>
      ${progress}
    </div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(labels.animeTitle || item.title)}</div>
      <div class="card-meta">
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
  const el = document.createElement("article");
  el.className = "card";
  el.innerHTML = `
    <div class="card-poster ${poster ? "has-img" : ""}" style="${posterStyle(poster)}">
      <div class="card-play">
        <button type="button" class="btn-play-sm" aria-label="Abrir">${playIcon(18)}</button>
      </div>
    </div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(item.title)}</div>
      <div class="card-meta">
        ${item.rating ? `<span class="ep-badge">★ ${escapeHtml(item.rating)}</span>` : ""}
        ${pillHtml(item.sources)}
      </div>
    </div>
  `;
  el.addEventListener("click", () => {
    const src = item.sources?.[0];
    if (!src?.link) {
      toast("Sem link de detalhes", true);
      return;
    }
    navigate(
      `anime?link=${encodeURIComponent(src.link)}&source=${encodeURIComponent(src.name || "")}`
    );
  });
  return el;
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
    heroTitle.textContent = "Carregando shelf…";
  }
  try {
    if (!silent) toast("Sincronizando drops…");
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
    toast(e.message || "Erro ao carregar", true);
    if (scroller) {
      scroller.innerHTML = `<div class="empty-state"><strong>Não deu pra carregar</strong>Verifique a conexão e as fontes ativas.</div>`;
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
  await loadHome({ silent: true });
  const q = $("#search-input")?.value?.trim();
  if (q && q.length >= 2 && !$("#search-overlay")?.hidden) {
    await runSearch(q);
  }
}

function renderHero() {
  const item = state.episodes[0];
  state.heroItem = item || null;
  if (!item) {
    $("#hero-title").textContent = "Shelf vazio";
    $("#hero-desc").textContent =
      "Ative ao menos uma fonte na aba Fontes para encher o deck.";
    const bg = $("#hero-bg");
    if (bg) bg.style.backgroundImage = "";
    $("#hero-meta").textContent = "Nenhum drop no momento";
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
  $("#hero-meta").textContent = [
    labels.number && labels.number !== "?" ? labels.episodeLine : null,
    (item.sources || []).map((s) => s.name).join(" · "),
  ]
    .filter(Boolean)
    .join("  ·  ");
  $("#hero-desc").textContent =
    item.date
      ? `Drop recente · ${item.date}`
      : "Pronto pra assistir — fallback automático entre fontes.";
}

function renderEpisodesRow() {
  const scroller = $("#episodes-scroller");
  if (!scroller) return;
  scroller.innerHTML = "";
  const count = $("#episodes-count");
  if (!state.episodes.length) {
    scroller.innerHTML = `<div class="empty-state"><strong>Shelf vazio</strong>Nenhum drop nas fontes ativas. Ative provedores em Fontes.</div>`;
    if (count) count.textContent = "0";
    return;
  }
  if (count) count.textContent = `${state.episodes.length} eps`;
  const frag = document.createDocumentFragment();
  for (const ep of state.episodes) {
    frag.appendChild(episodeCard(ep));
  }
  scroller.appendChild(frag);
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
    }));
}

function onEpisodeClick(item) {
  const sources = item.sources || [];
  if (!sources.length) {
    toast("Nenhuma fonte disponível", true);
    return;
  }
  const links = sources.map((s) => s.link).filter(Boolean);
  const num = resolveEpisodeNumber(item.number, item.title, ...links);
  const labels = normalizeWatchTitles(item.title, item.title, num);
  // Fallback automático entre fontes — sem modal obrigatório
  playEpisode({
    preferred_source: sources[0].name,
    anime_title: labels.animeTitle,
    episode_title: labels.episodeTitle,
    episode_number: labels.number,
    anime_image: item.image,
    source_color: sources[0].color,
    candidates: sourcesToCandidates(sources),
  });
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

/**
 * Títulos limpos pra UI/histórico.
 * @returns {{ animeTitle: string, episodeTitle: string, number: string, episodeLine: string }}
 */
function normalizeWatchTitles(animeTitle, episodeTitle, number) {
  const num = resolveEpisodeNumber(number, episodeTitle, animeTitle);
  let anime = stripEpisodeSuffix(animeTitle, num);
  let ep = stripEpisodeSuffix(episodeTitle, num);

  if (isOnlyEpisodeLabel(episodeTitle) || isOnlyEpisodeLabel(ep)) ep = "";
  if (ep && anime && ep.toLowerCase() === anime.toLowerCase()) ep = "";

  if (!anime) {
    anime = stripEpisodeSuffix(episodeTitle, num) || String(animeTitle || episodeTitle || "Anime").trim();
    if (isOnlyEpisodeLabel(anime)) anime = String(animeTitle || "Anime").trim();
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

function openSourceModal(title, sources, onPick) {
  const modal = $("#source-modal");
  const list = $("#source-options");
  $("#source-modal-title").textContent = title;
  list.innerHTML = "";
  for (const s of sources) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "source-opt";
    btn.innerHTML = `
      <span class="source-dot" style="--dot:${s.color || "#888"};background:${s.color || "#888"}"></span>
      <span>${escapeHtml(s.name)}</span>
    `;
    btn.addEventListener("click", () => {
      modal.hidden = true;
      onPick(s);
    });
    list.appendChild(btn);
  }
  modal.hidden = false;
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
      ? `Resolvendo stream (${candidates.length} fontes)…`
      : "Resolvendo stream…"
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
          ? `${failed.join(", ")} indisponível — usando ${usedSource}`
          : `Reproduzindo via ${usedSource}`
      );
    }

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
      },
    });
    if (!res.playable) {
      toast("Stream direto indisponível — abra na fonte");
    }
    renderContinueRow();
  } catch (e) {
    toast(e.message || "Falha ao reproduzir", true);
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

async function loadDetail(link, preferredSource) {
  if (!link) {
    toast("Link inválido", true);
    navigate("home");
    return;
  }
  $("#detail-title").textContent = "Carregando…";
  $("#detail-desc").textContent = "";
  $("#detail-episodes").innerHTML = "";
  $("#season-select").innerHTML = "";
  try {
    await waitSourcesReady();
    const detail = await api.anime(link);
    state.detail = detail;
    state.detailPreferred = preferredSource || "";
    // se veio da busca, sources estão no hash source name only — re-fetch not needed
    renderDetail(detail, preferredSource);
  } catch (e) {
    toast(e.message || "Erro ao carregar anime", true);
    navigate("home");
  }
}

function renderDetail(detail, preferredSource) {
  const poster = imgUrl(detail.image);
  $("#detail-title").textContent = detail.title;
  $("#detail-rating").textContent = detail.rating
    ? `★ ${detail.rating}`
    : "";
  $("#detail-desc").textContent = detail.description || "Sem sinopse.";
  const posterEl = $("#detail-poster");
  if (posterEl) {
    posterEl.src = poster || "";
    posterEl.alt = detail.title;
    posterEl.style.display = poster ? "" : "none";
  }
  const bg = $("#detail-bg");
  if (bg && poster) bg.style.backgroundImage = `url('${poster}')`;

  const pills = $("#detail-sources");
  if (pills) {
    pills.innerHTML = preferredSource
      ? `<span class="source-pill">${escapeHtml(preferredSource)}</span>`
      : "";
  }

  const seasons = detail.seasons || [];
  const select = $("#season-select");
  select.innerHTML = "";
  if (!seasons.length) {
    $("#detail-episodes").innerHTML =
      `<div class="empty-state"><strong>Sem episódios</strong>Esta ficha não trouxe lista de episódios.</div>`;
    return;
  }
  seasons.forEach((s, i) => {
    const opt = document.createElement("option");
    opt.value = String(i);
    opt.textContent = `Temporada ${s.number}`;
    select.appendChild(opt);
  });
  select.onchange = () => renderSeasonEpisodes(seasons[Number(select.value)]);
  renderSeasonEpisodes(seasons[0]);
}

function renderSeasonEpisodes(season) {
  const grid = $("#detail-episodes");
  if (!grid || !season) return;
  grid.innerHTML = "";
  grid.classList.add("episodes-list");
  const frag = document.createDocumentFragment();
  for (const ep of season.episodes || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ep-card";
    const thumb = imgUrl(ep.image || state.detail?.image);
    const labels = normalizeWatchTitles(
      state.detail?.title || "",
      ep.title,
      resolveEpisodeNumber(ep.number, ep.title, ep.link)
    );
    // badge já tem o nº — se o título era só "Episódio 1", não repete
    const epDisplay = labels.episodeTitle || "Episódio";
    btn.innerHTML = `
      <div class="ep-thumb" style="${thumb ? `background-image:url('${thumb}')` : ""}">
        <span class="ep-num">${escapeHtml(labels.number && labels.number !== "?" ? labels.number : "?")}</span>
      </div>
      <div class="ep-info">
        <div class="ep-title">${escapeHtml(epDisplay)}</div>
        ${ep.date ? `<div class="ep-date">${escapeHtml(ep.date)}</div>` : ""}
      </div>
    `;
    btn.addEventListener("click", () => {
      playEpisode({
        episode_link: ep.link,
        preferred_source: state.detailPreferred,
        anime_title: labels.animeTitle,
        episode_title: labels.episodeTitle,
        episode_number: labels.number,
        anime_image: state.detail?.image || ep.image || "",
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
      grid.innerHTML = `<div class="empty-state"><strong>Fila vazia</strong>Assista um episódio e ele aparece aqui com progresso.</div>`;
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
  if (s === "checking") return { cls: "checking", text: "Checando" };
  return { cls: "unknown", text: "Desconhecido" };
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
  if (!iso) return "nunca";
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
    s.has_details ? "detalhes" : null,
    s.enabled ? "preferida" : "pausada",
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
          <span class="metric-label">Uptime</span>
          <div class="metric-value ${uptimeClass(uptime)}">${escapeHtml(formatUptime(uptime))}</div>
          <div class="uptime-bar" title="Janela recente de health checks">
            <i style="width:${uptime != null ? Math.max(0, Math.min(100, uptime)) : 0}%"></i>
          </div>
        </div>
        <div class="metric">
          <span class="metric-label">Latência</span>
          <div class="metric-value ${latencyClass(s.latency_ms)}">${escapeHtml(formatLatency(s.latency_ms))}</div>
        </div>
        <div class="metric">
          <span class="metric-label">Último check</span>
          <div class="metric-value" style="font-size:0.85rem">${escapeHtml(formatCheckTime(s.last_check_at))}</div>
        </div>
      </div>
      <div class="source-caps">
        ${caps.map((c) => `<span class="cap-chip">${escapeHtml(c)}</span>`).join("")}
        ${s.checks_total ? `<span class="cap-chip">${s.checks_ok}/${s.checks_total} ok</span>` : ""}
      </div>
      ${s.error && !s.available ? `<p class="source-error">Falha: ${escapeHtml(s.error)}</p>` : ""}
    </div>
    <div class="source-card-aside">
      <div class="source-toggle-wrap">
        <span class="source-toggle-label">${s.enabled ? "Ativa" : "Inativa"}</span>
        <label class="switch" title="Usar esta fonte no catálogo">
          <input type="checkbox" ${s.enabled ? "checked" : ""} data-id="${escapeHtml(s.identifier)}" />
          <span class="switch-slider"></span>
        </label>
      </div>
      <div class="source-card-actions">
        <button type="button" class="btn-icon-sm" data-ping="${escapeHtml(s.identifier)}" title="Checar agora">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>
          </svg>
          Ping
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
      if (labelEl) labelEl.textContent = enabled ? "Ativa" : "Inativa";
      toast(`${s.name}: ${enabled ? "ativada" : "desativada"} — recarregando…`);
      state.catalogDirty = true;
      state.episodes = [];
      await reloadAfterSourcesChange();
    } catch (e) {
      input.checked = !enabled;
      toast(e.message || "Falha ao alterar fonte", true);
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
      pill.textContent = "Checando";
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
      toast(err.message || "Falha no health check", true);
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
      toast("Checando status das fontes…");
      data = await api.refreshSourcesHealth();
    } else {
      data = await api.sources();
    }
    const items = data.items || [];
    list.innerHTML = "";
    if (!items.length) {
      list.innerHTML = `<div class="empty-state"><strong>Nenhuma fonte</strong>Nenhum provedor foi descoberto.</div>`;
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
    box.innerHTML = `<p class="search-status">Digite ao menos 2 caracteres para buscar</p>`;
    return;
  }
  box.innerHTML = `<p class="search-status">Buscando nas fontes…</p>`;
  try {
    await waitSourcesReady();
    const data = await api.search(q);
    const items = data.items || [];
    if (!items.length) {
      box.innerHTML = `<p class="search-status">Nada encontrado para “${escapeHtml(q)}”</p>`;
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
    // se houver várias fontes, mostra picker; senão play direto
    const sources = item.sources || [];
    if (sources.length > 1) {
      openSourceModal(item.title, sources, (src) => {
        playEpisode({
          preferred_source: src.name,
          anime_title: item.title,
          episode_title: item.title,
          episode_number: resolveEpisodeNumber(
            item.number,
            item.title,
            ...sources.map((s) => s.link)
          ),
          anime_image: item.image,
          source_color: src.color,
          candidates: sourcesToCandidates(sources),
        });
      });
      return;
    }
    onEpisodeClick(item);
  });

  $("#detail-back")?.addEventListener("click", () => navigate("home"));

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
