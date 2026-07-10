import { state } from "./state.js";
import { $, $$ } from "./utils/dom.js";

export function parseHash() {
  const h = location.hash.replace(/^#\/?/, "") || "home";
  const [path, ...rest] = h.split("?");
  const params = new URLSearchParams(rest.join("?") || "");
  return { path, params };
}

export function navigate(path) {
  location.hash = `#/${path}`;
}

export function setActiveNav(route) {
  $$(".rail-link, .nav-link").forEach((a) => {
    a.classList.toggle("active", a.dataset.nav === route);
  });
}

export function setTopbar(eyebrow, title) {
  const e = $("#topbar-eyebrow");
  const t = $("#topbar-title");
  if (e) {
    e.textContent = eyebrow || "";
    e.hidden = !eyebrow;
  }
  if (t) t.textContent = title || "";
}

export function showView(id) {
  const prev = document.querySelector(".view.is-active");
  const next = document.getElementById(id);
  if (prev === next) return;
  if (prev) {
    prev.classList.remove("is-active");
    prev.hidden = true;
  }
  if (next) {
    next.hidden = false;
    next.classList.add("is-active");
  }
}

export async function onRoute() {
  const { closeSearch } = await import("./search.js");
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
    const { loadDetail } = await import("./views/detail.js");
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
    const { loadGenresPage } = await import("./views/genres.js");
    await loadGenresPage();
    return;
  }

  if (path === "calendar") {
    state.route = "calendar";
    setActiveNav("calendar");
    setTopbar("", "Calendário");
    showView("view-calendar");
    const { loadCalendarPage } = await import("./views/calendar.js");
    await loadCalendarPage();
    return;
  }

  if (path === "history") {
    state.route = "history";
    setActiveNav("history");
    setTopbar("", "Continuar");
    showView("view-history");
    const { loadHistoryPage } = await import("./views/history.js");
    await loadHistoryPage();
    return;
  }

  if (path === "watchlater") {
    state.route = "watchlater";
    setActiveNav("watchlater");
    setTopbar("", "Assistir Depois");
    showView("view-watchlater");
    const { loadWatchLaterPage } = await import("./views/watchlater.js");
    await loadWatchLaterPage();
    return;
  }

  if (path === "sources") {
    state.route = "sources";
    setActiveNav("sources");
    setTopbar("", "Fontes");
    showView("view-sources");
    const { loadSources } = await import("./views/sources.js");
    await loadSources();
    return;
  }

  state.route = "home";
  setActiveNav("home");
  setTopbar("", "Início");
  showView("view-home");
  const { loadHome, renderContinueRow } = await import("./views/home.js");
  if (state.catalogDirty || !state.episodes.length) {
    await loadHome();
  } else {
    await renderContinueRow();
  }
}
