/**
 * anishelf — entry point
 * Bootstraps the app, binds UI events, starts the router.
 */

import { initPlayer } from "./player.js";
import { state } from "./state.js";
import { $, $$, PLACEHOLDER_POSTER } from "./utils/dom.js";
import { toast } from "./toast.js";
import { onRoute, navigate } from "./router.js";
import { openSearch, closeSearch, runSearch } from "./search.js";
import { loadCalendarCheckPref, saveCalendarCheckPref } from "./views/calendar.js";

function bindUi() {
  initPlayer({
    onClose: () => {
      import("./views/home.js").then((m) => {
        m.renderContinueRow();
        m.renderWatchLaterRow();
      });
      if (state.route === "history") {
        import("./views/history.js").then((m) => m.loadHistoryPage());
      }
      if (state.route === "watchlater") {
        import("./views/watchlater.js").then((m) => m.loadWatchLaterPage());
      }
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
    if (state.heroItem) {
      import("./play-flow.js").then((m) => m.onEpisodeClick(state.heroItem));
    }
  });

  $("#detail-back")?.addEventListener("click", () => navigate("home"));
  $("#btn-genre-back")?.addEventListener("click", () => {
    import("./views/genres.js").then((m) => m.backToGenrePick());
  });

  // calendar check sources preference
  state.calendarCheckSources = loadCalendarCheckPref();
  const checkSourcesEl = $("#calendar-check-sources");
  if (checkSourcesEl) {
    checkSourcesEl.checked = !!state.calendarCheckSources;
    checkSourcesEl.addEventListener("change", async () => {
      state.calendarCheckSources = !!checkSourcesEl.checked;
      saveCalendarCheckPref(state.calendarCheckSources);
      state.calendarCache = null;
      const { loadCalendarPage } = await import("./views/calendar.js");
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
      const { loadCalendarPage } = await import("./views/calendar.js");
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
        const { loadCalendarPage } = await import("./views/calendar.js");
        await loadCalendarPage({ force: true });
        return;
      }
      state.calendarDays = days;
      state.calendarCache = null;
      const { syncCalendarRangeButtons, loadCalendarPage } = await import("./views/calendar.js");
      syncCalendarRangeButtons();
      await loadCalendarPage({ force: true });
    });
  });

  $("#btn-clear-watchlater")?.addEventListener("click", async () => {
    if (!confirm("Limpar todos os favoritos?")) return;
    const { api } = await import("./api.js");
    try {
      await api.clearWatchLater();
      toast("Favoritos limpos");
      const { loadWatchLaterPage } = await import("./views/watchlater.js");
      loadWatchLaterPage();
      const { renderWatchLaterRow } = await import("./views/home.js");
      renderWatchLaterRow();
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btn-clear-history")?.addEventListener("click", async () => {
    if (!confirm("Limpar todo o histórico?")) return;
    const { api } = await import("./api.js");
    try {
      await api.clearHistory();
      toast("Histórico limpo");
      const { loadHistoryPage } = await import("./views/history.js");
      loadHistoryPage();
      const { renderContinueRow } = await import("./views/home.js");
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

  $("#shortcuts-close")?.addEventListener("click", () => {
    $("#shortcuts-modal").hidden = true;
  });
  $("#shortcuts-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "shortcuts-modal") e.target.hidden = true;
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
      if (!$("#shortcuts-modal")?.hidden) $("#shortcuts-modal").hidden = true;
    }
    if (e.key === "?") {
      if (e.target.matches("input, textarea, select")) return;
      if (!$("#player-modal")?.hidden) return;
      e.preventDefault();
      const m = $("#shortcuts-modal");
      if (m) m.hidden = !m.hidden;
    }
  });
}

bindUi();
onRoute();
new Image().src = PLACEHOLDER_POSTER;

document.addEventListener("load", (e) => {
  if (e.target.classList.contains("card-poster-img")) {
    e.target.classList.add("is-loaded");
  }
}, true);

document.addEventListener("error", (e) => {
  if (e.target.classList.contains("card-poster-img")) {
    e.target.classList.add("is-loaded");
  }
}, true);
