import { api, imgUrl } from "./api.js";
import { state } from "./state.js";
import {
  $,
  $$,
  escapeHtml,
  playIcon as _playIcon,
  PLACEHOLDER_POSTER,
  posterStyle,
  skeletonShelf as _skeletonShelf,
} from "./utils/dom.js";
import {
  normalizeWatchTitles,
  resolveEpisodeNumber,
  formatEpLabel,
  stripTitleVariants,
} from "./utils/titles.js";
import {
  hasAudioChoice,
} from "./utils/audio.js";

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

export function episodeCard(item, { progressRatio } = {}) {
  const poster = imgUrl(item.image);
  const playIcon = _playIcon;
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
    import("./play-flow.js").then((m) => m.onEpisodeClick(item));
  });
  return el;
}

export function animeCard(item) {
  const poster = imgUrl(item.image);
  const playIcon = _playIcon;
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
  const isSaved = state.watchLater.some((w) => w.anime_title === item.title);
  el.innerHTML = `
    <div class="card-poster has-img">
      <img class="card-poster-img" src="${imgSrc}" alt="" loading="lazy" onerror="this.onerror=null; this.src='${PLACEHOLDER_POSTER}';" />
      <button type="button" class="card-bookmark-btn${isSaved ? " is-saved" : ""}" aria-label="${isSaved ? "Remover da lista" : "Assistir depois"}" data-action="bookmark">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="${isSaved ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
        </svg>
      </button>
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
  el.addEventListener("click", (e) => {
    if (e.target.closest("[data-action=bookmark]")) {
      toggleWatchLater(item, el);
      return;
    }
    import("./play-flow.js").then((m) => m.onAnimeClick(item));
  });
  return el;
}

async function toggleWatchLater(item, el) {
  const { api } = await import("./api.js");
  const { toast } = await import("./toast.js");
  const bookmark = el.querySelector(".card-bookmark-btn");
  const isSaved = bookmark?.classList.contains("is-saved");
  try {
    if (isSaved) {
      await api.removeWatchLater(item.title);
      bookmark?.classList.remove("is-saved");
      bookmark?.querySelector("svg")?.setAttribute("fill", "none");
      bookmark?.setAttribute("aria-label", "Assistir depois");
      state.watchLater = state.watchLater.filter((w) => w.anime_title !== item.title);
      toast("Removido da lista");
    } else {
      await api.addWatchLater({
        anime_title: item.title,
        anime_image: item.image || "",
        source_name: (item.sources && item.sources[0]?.name) || "",
        source_link: (item.sources && item.sources[0]?.link) || "",
        source_color: (item.sources && item.sources[0]?.color) || "",
      });
      bookmark?.classList.add("is-saved");
      bookmark?.querySelector("svg")?.setAttribute("fill", "currentColor");
      bookmark?.setAttribute("aria-label", "Remover da lista");
      state.watchLater.push({
        anime_title: item.title,
        anime_image: item.image || "",
        source_name: (item.sources && item.sources[0]?.name) || "",
        source_link: (item.sources && item.sources[0]?.link) || "",
        source_color: (item.sources && item.sources[0]?.color) || "",
      });
      toast("Adicionado à lista");
    }
  } catch (e) {
    toast(e.message || "Erro ao salvar", true);
  }
}

export function historyCard(item) {
  const poster = imgUrl(item.anime_image);
  const playIcon = _playIcon;
  const ratio = item.progress_ratio || 0;
  const showProgress = ratio > 0.02;
  const pct = Math.round(ratio * 100);
  const progress =
    showProgress
      ? `<div class="card-progress"><i style="width:${pct}%"></i></div>`
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
  el.className = "card" + (item.is_finished ? " is-finished" : "");
  const imgSrc = poster || PLACEHOLDER_POSTER;
  el.innerHTML = `
    <div class="card-poster">
      <img class="card-poster-img" src="${imgSrc}" alt="" loading="lazy" onerror="this.onerror=null; this.src='${PLACEHOLDER_POSTER}';" />
      ${corner}
      <div class="card-play">
        <button type="button" class="btn-play-sm" aria-label="${showProgress ? "Continuar" : "Assistir"}">${playIcon(18)}</button>
      </div>
      ${progress}
    </div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(labels.animeTitle)}</div>
      ${item.source_name ? `<div class="card-meta"><span class="source-pill">${escapeHtml(item.source_name)}</span></div>` : ""}
    </div>
  `;
  el.addEventListener("click", () => import("./play-flow.js").then((m) => m.playFromHistory(item)));
  return el;
}

export function catalogPlaceholderCard(item) {
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

export function watchLaterCard(item) {
  const poster = imgUrl(item.anime_image);
  const playIcon = _playIcon;
  const el = document.createElement("article");
  el.className = "card";
  const imgSrc = poster || PLACEHOLDER_POSTER;
  el.innerHTML = `
    <div class="card-poster has-img">
      <img class="card-poster-img" src="${imgSrc}" alt="" loading="lazy" onerror="this.onerror=null; this.src='${PLACEHOLDER_POSTER}';" />
      <button type="button" class="card-remove-btn" aria-label="Remover da lista" data-action="remove-wl">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
      <div class="card-play">
        <button type="button" class="btn-play-sm" aria-label="Assistir">${playIcon(18)}</button>
      </div>
    </div>
    <div class="card-body">
      <div class="card-title">${escapeHtml(item.anime_title)}</div>
      ${item.source_name ? `<div class="card-meta"><span class="source-pill">${escapeHtml(item.source_name)}</span></div>` : ""}
    </div>
  `;
  el.addEventListener("click", (e) => {
    if (e.target.closest("[data-action=remove-wl]")) return;
    import("./play-flow.js").then((m) => m.onAnimeClick({
      title: item.anime_title,
      image: item.anime_image,
      sources: item.source_link ? [{ name: item.source_name, link: item.source_link, color: item.source_color }] : [],
    }));
  });
  return el;
}

export { pillHtml, audioChoiceBadge };
