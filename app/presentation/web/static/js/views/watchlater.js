import { api, imgUrl } from "../api.js";
import { state } from "../state.js";
import { $, escapeHtml, PLACEHOLDER_POSTER } from "../utils/dom.js";

const DAY_MS = 86400000;

function daysAgo(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const d = Math.floor(diff / DAY_MS);
  if (d < 1) return "hoje";
  if (d === 1) return "ontem";
  if (d < 7) return `há ${d} dias`;
  const w = Math.floor(d / 7);
  if (w === 1) return "há 1 semana";
  if (w < 5) return `há ${w} semanas`;
  return `há ${Math.floor(d / 30)} meses`;
}

function groupItems(items) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const weekAgo = new Date(today.getTime() - 7 * DAY_MS);
  const g = { hoje: [], semana: [], antes: [] };
  for (const item of items) {
    const d = item.added_at ? new Date(item.added_at) : new Date();
    if (d >= today) g.hoje.push(item);
    else if (d >= weekAgo) g.semana.push(item);
    else g.antes.push(item);
  }
  return g;
}

function renderRow(item) {
  const src = imgUrl(item.anime_image) || PLACEHOLDER_POSTER;
  const row = document.createElement("div");
  row.className = "wl-row";
  row.innerHTML = `
    <div class="wl-row-poster">
      <img src="${src}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${PLACEHOLDER_POSTER}'">
    </div>
    <div class="wl-row-body">
      <div class="wl-row-title">${escapeHtml(item.anime_title)}</div>
      <div class="wl-row-meta">
        ${item.source_name ? `<span class="source-pill">${escapeHtml(item.source_name)}</span>` : ""}
        <span class="wl-row-date">${escapeHtml(daysAgo(item.added_at))}</span>
      </div>
    </div>
    <div class="wl-row-actions">
      <button type="button" class="wl-action-btn is-play" aria-label="Assistir" title="Assistir agora">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      </button>
      <button type="button" class="wl-action-btn is-remove" aria-label="Remover dos favoritos" title="Remove este anime dos favoritos" data-action="remove-wl">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </div>
  `;

  row.addEventListener("click", async (e) => {
    const rm = e.target.closest("[data-action=remove-wl]");
    if (rm) {
      if (rm.disabled) return;
      rm.disabled = true;
      const { toast } = await import("../toast.js");
      try {
        await api.removeWatchLater(item.anime_title);
        state.watchLater = state.watchLater.filter((w) => w.anime_title !== item.anime_title);
        const section = row.closest(".wl-section");
        row.remove();
        if (section && !section.querySelector(".wl-row")) section.remove();
        if (!$("#wl-shelf")?.querySelector(".wl-section")) build([]);
        toast("Removido dos favoritos");
      } catch (err) {
        toast(err.message || "Erro ao remover", true);
        rm.disabled = false;
      }
      return;
    }
    const play = e.target.closest(".wl-action-btn.is-play");
    if (play && play.disabled) return;
    if (play) play.disabled = true;
    try {
      await import("../play-flow.js").then((m) => m.onAnimeClick({
        title: item.anime_title,
        image: item.anime_image,
        sources: item.source_link ? [{ name: item.source_name, link: item.source_link, color: item.source_color }] : [],
      }));
    } finally {
      if (play) play.disabled = false;
    }
  });

  return row;
}

const LABELS = [
  { key: "hoje", label: "Adicionados hoje" },
  { key: "semana", label: "Esta semana" },
  { key: "antes", label: "Anteriormente" },
];

function build(items) {
  const c = $("#wl-container");
  if (!c) return;
  c.innerHTML = "";

  if (!items || !items.length) {
    c.innerHTML = `
      <div class="wl-empty">
        <div class="wl-empty-ico" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <strong>Sua lista de favoritos está vazia</strong>
        Animes que você salvar aparecem aqui. Use o ícone de bookmark nos cards para adicionar.
      </div>`;
    return;
  }

  const groups = groupItems(items);
  const shelf = document.createElement("div");
  shelf.id = "wl-shelf";
  shelf.className = "wl-shelf";

  for (const s of LABELS) {
    const list = groups[s.key];
    if (!list?.length) continue;
    const sec = document.createElement("div");
    sec.className = "wl-section";
    sec.innerHTML = `
      <div class="wl-divider">
        <span class="wl-divider-ico" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
        </span>
        <span class="wl-divider-label">${s.label}</span>
      </div>`;
    for (const item of list) sec.appendChild(renderRow(item));
    shelf.appendChild(sec);
  }
  c.appendChild(shelf);
}

export async function loadWatchLaterPage() {
  const c = $("#wl-container");
  if (!c) return;

  c.innerHTML = `<div class="wl-loading"><p style="color:var(--dim)">Carregando…</p></div>`;

  try {
    const data = await Promise.race([
      api.watchLater(),
      new Promise((_, reject) => setTimeout(() => reject(new Error("Sem resposta do servidor")), 8000)),
    ]);
    state.watchLater = data?.items || [];
    build(state.watchLater);
  } catch (e) {
    c.innerHTML = `<div class="wl-loading"><p style="color:var(--dim)">${escapeHtml(e.message || "Erro ao carregar")}</p></div>`;
  }
}
