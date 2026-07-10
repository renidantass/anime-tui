import { api } from "../api.js";
import { state } from "../state.js";
import { $, escapeHtml } from "../utils/dom.js";
import { watchLaterCard } from "../cards.js";

export async function loadWatchLaterPage() {
  const grid = $("#watchlater-grid");
  if (!grid) return;
  grid.innerHTML = `<div class="empty-state">Carregando…</div>`;
  try {
    const data = await api.watchLater();
    state.watchLater = data.items || [];
    if (!state.watchLater.length) {
      grid.innerHTML = `<div class="empty-state"><strong>Lista vazia</strong>Animes que você salvar aparecem aqui.</div>`;
      return;
    }
    grid.innerHTML = "";
    for (const item of state.watchLater) {
      grid.appendChild(watchLaterCard(item));
    }
  } catch (e) {
    grid.innerHTML = `<div class="empty-state">${escapeHtml(e.message)}</div>`;
  }
}
