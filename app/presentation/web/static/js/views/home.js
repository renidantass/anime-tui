import { api, imgUrl } from "../api.js";
import { state } from "../state.js";
import { $, $$, escapeHtml, PLACEHOLDER_POSTER, skeletonShelf } from "../utils/dom.js";
import { normalizeWatchTitles, resolveEpisodeNumber } from "../utils/titles.js";
import { hasAudioChoice as _hasAudioChoice, detectAudioVariant, audioBucket, resolveSourceVariant } from "../utils/audio.js";
import { episodeCard, animeCard, historyCard, watchLaterCard, audioChoiceBadge } from "../cards.js";
import { waitSourcesReady, hasAnyEnabledSource } from "../search.js";
import { toast } from "../toast.js";
import { onEpisodeClick } from "../play-flow.js";

export async function loadHome({ silent = false } = {}) {
  const seq = ++state.catalogReloadSeq;
  state.loadingCatalog = true;
  state.catalogDirty = true;

  restoreHeroStructure();
  $("#view-home")?.classList.add("is-loading-home");

  const scroller = $("#episodes-scroller");
  if (scroller) {
    scroller.innerHTML = skeletonShelf(8);
  }
  try {
    await waitSourcesReady();
    const data = await api.episodes();
    if (seq !== state.catalogReloadSeq) return;
    state.episodes = data.items || [];
    state.catalogDirty = false;

    state.episodes.sort((a, b) => {
      const da = a.date || ""; const db = b.date || "";
      if (da && db) return db.localeCompare(da);
      if (da) return -1; if (db) return 1;
      const na = parseFloat(a.number) || 0;
      const nb = parseFloat(b.number) || 0;
      return nb - na;
    });

    if (!state.episodes.length) {
      const anyEnabled = await hasAnyEnabledSource();
      if (!anyEnabled) {
        showNoSourcesOnboarding();
        return;
      }
    }

    renderHero();
    renderEpisodesRow();
    renderContinueRow();
    renderWatchLaterRow();
  } catch (e) {
    if (seq !== state.catalogReloadSeq) return;
    if (!silent) toast(e.message || "Não foi possível carregar", true);
    if (scroller) {
      scroller.innerHTML = `<div class="empty-state"><strong>Não carregou</strong>Confira a internet e as fontes ativas.</div>`;
    }
  } finally {
    if (seq === state.catalogReloadSeq) {
      state.loadingCatalog = false;
      $("#view-home")?.classList.remove("is-loading-home");
      startBroadcastClock();
    }
  }
}

export async function reloadAfterSourcesChange() {
  state.genreCache = {};
  await loadHome({ silent: true });
  if (state.route === "genres" && state.selectedGenre) {
    import("./genres.js").then((m) => m.loadGenreBrowse(state.selectedGenre, { silent: true, force: true }));
  }
  const q = $("#search-input")?.value?.trim();
  if (q && q.length >= 2 && !$("#search-overlay")?.hidden) {
    import("../search.js").then((m) => m.runSearch(q));
  }
}

function restoreHeroStructure() {
  const viewHome = $("#view-home");
  if (!viewHome || !viewHome.querySelector(".onboarding-hero")) return;

  viewHome.innerHTML = `
    <div class="home-layout">
      <article class="spotlight" id="hero">
          <div class="spotlight-poster-wrap"><img class="spotlight-poster" id="hero-poster" alt="" /></div>
        <div class="spotlight-body">
          <span class="tag tag-hot" id="hero-badge">Em destaque</span>
          <h2 class="spotlight-title" id="hero-title">Carregando…</h2>
          <p class="spotlight-meta" id="hero-meta"></p>
          <div class="spotlight-actions">
            <button type="button" class="btn btn-accent" id="hero-play">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              Assistir
            </button>
          </div>
        </div>
        <time class="spotlight-hud-code" id="hero-clock"><span class="hud-live"></span><span class="hud-time">--:--:--</span></time>
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

  rebindHeroButtons();
}

function rebindHeroButtons() {
  $("#hero-play")?.addEventListener("click", (e) => {
    e.stopPropagation();
    if (state.heroItem) onEpisodeClick(state.heroItem);
  });
  $("#hero")?.addEventListener("click", () => {
    if (state.heroItem) onEpisodeClick(state.heroItem);
  });
}

function showNoSourcesOnboarding() {
  const viewHome = $("#view-home");
  if (!viewHome) return;
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

export function renderHero() {
  const item = dedupeEpisodesByWork(state.episodes)[0];
  state.heroItem = item || null;
  if (!item) {
    const titleEl = $("#hero-title");
    const metaEl = $("#hero-meta");
    const poster = $("#hero-poster");
    if (titleEl) titleEl.textContent = "Nada por aqui";
    if (metaEl) metaEl.textContent = "Nenhum episódio no momento";
    if (poster) poster.src = "";
    return;
  }
  const posterEl = $("#hero-poster");
  if (posterEl) {
    const url = imgUrl(item.image);
    posterEl.src = url || PLACEHOLDER_POSTER;
    posterEl.onerror = () => { posterEl.src = PLACEHOLDER_POSTER; };
  }
  const links = (item.sources || []).map((s) => s.link);
  const labels = normalizeWatchTitles(
    item.title,
    item.title,
    resolveEpisodeNumber(item.number, item.title, ...links)
  );
  const titleEl = $("#hero-title");
  if (titleEl) titleEl.textContent = labels.animeTitle || item.title;
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
  const descEl = $("#hero-desc");
  // desc intentionally left empty
}

export function renderEpisodesRow() {
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
    if (!cur.image && ep.image) cur.image = ep.image;
    if (!cur.date && ep.date) cur.date = ep.date;
    for (const s of ep.sources || []) {
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

export async function renderWatchLaterRow() {
  const row = $("#row-watchlater");
  const scroller = $("#watchlater-scroller");
  if (!row || !scroller) return;
  try {
    const data = await api.watchLater();
    const items = data.items || [];
    if (!items.length) {
      row.hidden = true;
      return;
    }
    row.hidden = false;
    scroller.innerHTML = "";
    const frag = document.createDocumentFragment();
    for (const item of items.slice(0, 20)) {
      frag.appendChild(watchLaterCard(item));
    }
    scroller.appendChild(frag);
  } catch {
    row.hidden = true;
  }
}

export async function renderContinueRow() {
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

let _clockTimer = null;

function pad(n) {
  return String(n).padStart(2, "0");
}

function tickClock() {
  const el = document.getElementById("hero-clock");
  if (!el) return;
  const now = new Date();
  const hh = pad(now.getHours());
  const mm = pad(now.getMinutes());
  const ss = pad(now.getSeconds());
  el.querySelector(".hud-time").textContent = `${hh}:${mm}:${ss}`;
}

function startBroadcastClock() {
  if (_clockTimer) clearInterval(_clockTimer);
  tickClock();
  _clockTimer = setInterval(tickClock, 1000);
}
