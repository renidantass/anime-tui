import { api, imgUrl } from "../api.js";
import { state } from "../state.js";
import { $, $$, escapeHtml, PLACEHOLDER_POSTER, showGenreSkeletons, removeGenreSkeletons, removeOneGenreSkeleton } from "../utils/dom.js";
import { waitSourcesReady as _waitSourcesReady } from "../search.js";
import { toast } from "../toast.js";
import { animeCard, catalogPlaceholderCard } from "../cards.js";
import { hasAudioChoice, detectAudioVariant } from "../utils/audio.js";
import { stripTitleVariants } from "../utils/titles.js";

const GENRE_CACHE_MS = 8 * 60 * 1000;

const GENRE_POPULAR_ORDER = [
  "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Romance",
  "Sci-Fi", "Slice of Life", "Horror", "Mystery", "Sports", "Supernatural",
];

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

export function genreLabel(id) {
  const g = state.genres.find((x) => (x.id || x.name) === id);
  return g?.label || id;
}

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

function setTopbar(eyebrow, title) {
  const e = $("#topbar-eyebrow");
  const t = $("#topbar-title");
  if (e) {
    e.textContent = eyebrow || "";
    e.hidden = !eyebrow;
  }
  if (t) t.textContent = title || "";
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

export function renderGenrePickers() {
  const { popular, others } = splitGenres();
  fillGenreGrid($("#genre-grid"), [...popular, ...others], { showGo: true });
}

export function selectGenre(id) {
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
  if (step === "pick") setGenreStatus(false);
  if (step === "results" && state.selectedGenre) {
    setTopbar("", genreLabel(state.selectedGenre));
  } else {
    setTopbar("", "Gêneros");
  }
}

function backToGenrePick() {
  state.genreSeq++;
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

export { _renderGenreLoadMore };

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

async function loadMoreGenre() {
  const genre = state.genreCurrentGenre || state.selectedGenre;
  if (!genre || !state.genreHasNext) return;

  const btn = $("#genre-load-more-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Carregando…"; }

  showGenreSkeletons(3);
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
    removeGenreSkeletons();
  } catch (e) {
    toast(e.message || "Falha ao carregar mais", true);
  } finally {
    removeGenreSkeletons();
    _renderGenreLoadMore();
  }
}

function appendGenreCard(item) {
  const scroller = $("#genre-scroller");
  if (!scroller) return;
  const empty = scroller.querySelector(".empty-state");
  if (empty) empty.remove();
  const card = animeCard(item);
  card.classList.add("available-pop");
  const firstSkel = scroller.querySelector(".skel-card");
  if (firstSkel) {
    scroller.insertBefore(card, firstSkel);
  } else {
    scroller.appendChild(card);
  }
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

export async function loadGenreBrowse(genre, { silent = false, force = false } = {}) {
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
  setTopbar("", label);
  if (count) count.textContent = "…";
  if (scroller) scroller.innerHTML = "";

  const cached = state.genreCache[genre];
  if (!force && cached && Date.now() - cached.at < GENRE_CACHE_MS && cached.items?.length) {
    if (seq !== state.genreSeq) return;
    state.genrePage = 1;
    state.genreHasNext = true;
    state.genreCurrentGenre = genre;
    state.genreItems = cached.items;
    setGenreStatus(false);
    renderGenreAvailable(cached.items, { label, animated: false });
    state.genreLoading = false;
    return;
  }

  showGenreSkeletons(6);

  try {
    await _waitSourcesReady();
    if (seq !== state.genreSeq) return;

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
      setGenreStatus(false);
      removeGenreSkeletons();
      if (scroller) scroller.innerHTML = `<div class="empty-state"><strong>Nada neste gênero</strong>Não há títulos listados para ${escapeHtml(label)}.</div>`;
      if (count) count.textContent = "0";
      state.genreLoading = false;
      return;
    }

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


    }

    if (resolveUnsupported) {
      await loadGenreBrowseLegacy(genre, { seq, label, scroller, count });
      return;
    }

    if (seq !== state.genreSeq) return;
    state.genreItems = found;
    state.genreCache[genre] = { items: found, at: Date.now() };
    removeGenreSkeletons();

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
    setGenreStatus(false);
    removeGenreSkeletons();
    if (!silent) toast(e.message || "Não foi possível buscar o gênero", true);
    if (scroller) scroller.innerHTML = `<div class="empty-state"><strong>Busca falhou</strong>${escapeHtml(e.message || "Tente outro gênero.")}</div>`;
    if (count) count.textContent = "0";
  } finally {
    if (seq === state.genreSeq) {
      state.genreLoading = false;
      setGenreStatus(false);
      removeGenreSkeletons();
      renderGenrePickers();
      _renderGenreLoadMore();
    }
  }
}

async function loadGenreBrowseLegacy(genre, { seq, label, scroller, count }) {
  showGenreSkeletons(6);
  try {
    const data = await api.browseGenre(genre, 1, 16);
    if (seq !== state.genreSeq) return;
    const items = data.items || [];
    state.genreItems = items;
    state.genreCache[genre] = { items, at: Date.now() };
    state.genrePage = Number(data.page) || 1;
    state.genreHasNext = Boolean(data.has_next);
    removeGenreSkeletons();
    renderGenreAvailable(items, { label: data.label || label, animated: true });
  } catch (e) {
    if (seq !== state.genreSeq) return;
    removeGenreSkeletons();
    if (scroller) scroller.innerHTML = `<div class="empty-state"><strong>Busca falhou</strong>${escapeHtml(e.message || "Tente outro gênero.")}</div>`;
    if (count) count.textContent = "0";
  } finally {
    if (seq === state.genreSeq) {
      state.genreLoading = false;
      setGenreStatus(false);
      _renderGenreLoadMore();
    }
  }
}

export async function loadGenresPage() {
  if (!state.selectedGenre) {
    setGenreStep("pick");
  }
  try {
    await _waitSourcesReady();
    await loadGenresIfNeeded();

    if (state.selectedGenre) {
      setGenreStep("results");
      const cached = state.genreCache[state.selectedGenre];
      if (cached?.items?.length && !state.genreLoading) {
        showGenreLoading(false);
        setGenreStatus(false);
        setTopbar("", genreLabel(state.selectedGenre));
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
    return;
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
  } catch {
    if (grid) {
      grid.innerHTML = `<div class="empty-state" style="grid-column:1/-1">Não deu para carregar os gêneros.</div>`;
    }
  }
}

export { backToGenrePick, setGenreStep, setTopbar };
