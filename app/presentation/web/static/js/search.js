import { api } from "./api.js";
import { state } from "./state.js";
import { $, $$, escapeHtml, skeletonShelf } from "./utils/dom.js";
import { animeCard } from "./cards.js";
import { toast } from "./toast.js";

let _sourcesReadyPromise = null;

function saveSearchQuery(q) {
  const key = "anishelf.recentSearches";
  try {
    const list = JSON.parse(localStorage.getItem(key) || "[]");
    const filtered = list.filter((s) => s !== q);
    filtered.unshift(q);
    localStorage.setItem(key, JSON.stringify(filtered.slice(0, 5)));
  } catch { /* ignore */ }
}

function loadSearchHistory() {
  try {
    return JSON.parse(localStorage.getItem("anishelf.recentSearches") || "[]");
  } catch { return []; }
}

function renderSearchHistory() {
  const box = $("#search-results");
  if (!box) return;
  const history = loadSearchHistory();
  if (!history.length) {
    box.innerHTML = `<p class="search-status">Digite o nome de um anime</p>`;
    return;
  }
  box.innerHTML = `<div class="search-history-label">Buscas recentes</div>
    <div class="search-history-list">${history.map((q) =>
      `<button type="button" class="search-history-chip" data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`
    ).join("")}</div>`;
  box.querySelectorAll(".search-history-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = $("#search-input");
      if (input) {
        input.value = btn.dataset.q;
        runSearch(btn.dataset.q);
      }
    });
  });
}

export async function waitSourcesReady() {
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
      await new Promise((r) => setTimeout(r, 400));
    }
  })();
  return _sourcesReadyPromise;
}

export async function hasAnyEnabledSource() {
  try {
    const data = await api.sources();
    return (data.items || []).some((s) => s.enabled);
  } catch {
    return true;
  }
}

export function openSearch() {
  const ov = $("#search-overlay");
  if (!ov) return;
  ov.hidden = false;
  const input = $("#search-input");
  if (input) {
    input.value = "";
    input.focus();
  }
  updateSearchSourceBar();
  renderSearchHistory();
}

export async function updateSearchSourceBar() {
  const el = $("#search-sources");
  if (!el) return;
  try {
    const data = await api.sources();
    const enabled = (data.items || []).filter((s) => s.enabled);
    const online = enabled.filter((s) => s.available);
    const count = enabled.length;
    if (!count) {
      el.innerHTML = `<span class="src-bar-none">Nenhuma fonte ativa</span>`;
      return;
    }
    const chips = enabled
      .map((s) => {
        const cls = s.available ? "src-chip-on" : "src-chip-off";
        return `<span class="src-chip ${cls}" style="--src-color:${s.color || "#666"}">${escapeHtml(s.name)}</span>`;
      })
      .join("");
    el.innerHTML = `<span class="src-bar-label">Fontes ativas (${online.length}/${count})</span>${chips}`;
  } catch {
    el.innerHTML = "";
  }
}

export function closeSearch(clear = true) {
  const ov = $("#search-overlay");
  if (!ov) return;
  ov.hidden = true;
  if (clear) {
    const input = $("#search-input");
    if (input) input.value = "";
    $("#search-results").innerHTML = "";
  }
}

export async function runSearch(q) {
  const box = $("#search-results");
  if (!box) return;
  if (!q || q.length < 2) {
    box.innerHTML = `<p class="search-status">Digite pelo menos 2 letras</p>`;
    return;
  }
  box.innerHTML = skeletonShelf(6);
  try {
    await waitSourcesReady();
    const data = await api.search(q);
    const items = data.items || [];
    if (!items.length) {
      box.innerHTML = `<p class="search-status">Nada para “${escapeHtml(q)}”</p>`;
      return;
    }
    saveSearchQuery(q);
    box.innerHTML = `<div class="search-count">${items.length} resultado${items.length !== 1 ? "s" : ""}</div>`;
    const frag = document.createDocumentFragment();
    for (const a of items) frag.appendChild(animeCard(a));
    box.appendChild(frag);
  } catch (e) {
    box.innerHTML = `<p class="search-status">${escapeHtml(e.message)}</p>`;
  }
}
