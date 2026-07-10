import { api } from "../api.js";
import { $, escapeHtml } from "../utils/dom.js";
import { historyCard } from "../cards.js";
import { normalizeWatchTitles } from "../utils/titles.js";

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

function renderSection(title, items, grid) {
  if (!items.length) return;
  const heading = document.createElement("div");
  heading.className = "history-section-head";
  heading.innerHTML = `<h3>${escapeHtml(title)}</h3><span class="count-pill">${items.length}</span>`;
  grid.appendChild(heading);
  for (const h of items) grid.appendChild(historyCard(h));
}

export async function loadHistoryPage() {
  const grid = $("#history-grid");
  if (!grid) return;
  grid.innerHTML = `<div class="empty-state">Carregando…</div>`;
  try {
    const data = await api.history(true);
    const items = dedupeHistoryByAnime(data.items || []);
    if (!items.length) {
      grid.innerHTML = `<div class="empty-state"><strong>Nada aqui ainda</strong>Quando assistir um episódio, ele aparece com o progresso.</div>`;
      return;
    }
    grid.innerHTML = "";
    const inProgress = items.filter((h) => !h.is_finished);
    const finished = items.filter((h) => h.is_finished);
    renderSection("Continuar", inProgress, grid);
    renderSection("Concluídos", finished, grid);
  } catch (e) {
    grid.innerHTML = `<div class="empty-state">${escapeHtml(e.message)}</div>`;
  }
}
