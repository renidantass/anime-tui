import { api } from "../api.js";
import { state } from "../state.js";
import { $, escapeHtml } from "../utils/dom.js";
import { toast } from "../toast.js";
import { waitSourcesReady as _waitSourcesReady } from "../search.js";

function statusLabel(status, available) {
  const s = (status || (available ? "online" : "offline")).toLowerCase();
  if (s === "online") return { cls: "online", text: "Online" };
  if (s === "offline") return { cls: "offline", text: "Offline" };
  if (s === "checking") return { cls: "checking", text: "Testando" };
  return { cls: "unknown", text: "—" };
}

function formatLatency(ms) {
  if (ms == null || Number.isNaN(Number(ms))) return "—";
  const n = Number(ms);
  if (n < 1000) return `${Math.round(n)} ms`;
  return `${(n / 1000).toFixed(1)} s`;
}

function hostFromUrl(url) {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url.replace(/^https?:\/\//, "").split("/")[0];
  }
}

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) { h = ((h << 5) - h) + s.charCodeAt(i); h |= 0; }
  return Math.abs(h);
}

function sourceEmblemSvg(id, color) {
  const c = color || "#666";
  const h = hashStr(id || "");
  const templates = [
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="6"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/>
    </svg>`,
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2L2 12l10 10 10-10z"/><path d="M12 6l-4 4 4 4 4-4z"/><circle cx="12" cy="12" r="2"/>
    </svg>`,
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><circle cx="12" cy="12" r="3"/>
    </svg>`,
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="5" r="2"/><circle cx="12" cy="19" r="2"/><circle cx="5" cy="12" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="12" cy="12" r="4"/>
    </svg>`,
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="1" fill="${c}"/>
    </svg>`,
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 12c2-2 4-4 6 0s4 4 6 0 4-4 6 0"/><path d="M3 18c2-2 4-4 6 0s4 4 6 0 4-4 6 0"/><circle cx="12" cy="6" r="2"/>
    </svg>`,
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2L2 7l10 5 10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
    </svg>`,
    `<svg viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="9"/><path d="M12 7v2"/><path d="M12 15v2"/><path d="M7 12h2"/><path d="M15 12h2"/><circle cx="12" cy="12" r="3" fill="${c}" opacity="0.3"/>
    </svg>`,
  ];
  return templates[h % templates.length];
}

function signalBarsHtml(s) {
  const ms = s.latency_ms;
  const bars = [];
  const levels = ms == null ? [0, 0, 0, 0, 0]
    : ms < 200  ? [1, 1, 1, 1, 1]
    : ms < 500  ? [1, 1, 1, 1, 0]
    : ms < 1000 ? [1, 1, 1, 0, 0]
    : ms < 2500 ? [1, 1, 0, 0, 0]
    : [1, 0, 0, 0, 0];
  const heights = [6, 9, 12, 15, 18];
  for (let i = 0; i < 5; i++) {
    const on = levels[i] && s.available;
    const cls = !s.enabled ? "" : !on ? "is-bad" : ms < 500 ? "is-on" : ms < 1500 ? "is-warn" : "is-bad";
    bars.push(`<span class="signal-bar ${cls}" style="height:${heights[i]}px;opacity:${on ? 1 : s.enabled ? 0.2 : 0.08}"></span>`);
  }
  return `<span class="signal-bars">${bars.join("")}</span>`;
}

function renderSourcesDashboard(items) {
  const el = $("#sources-dashboard");
  if (!el) return;
  const total = items.length;
  const online = items.filter((s) => s.enabled && s.available).length;
  const offline = items.filter((s) => s.enabled && !s.available).length;
  const disabled = items.filter((s) => !s.enabled).length;
  el.innerHTML = `
    <div class="dash-stat total"><span class="dash-stat-value">${total}</span><span class="dash-stat-label">Total</span></div>
    <div class="dash-stat online"><span class="dash-stat-value">${online}</span><span class="dash-stat-label">Online</span></div>
    <div class="dash-stat offline"><span class="dash-stat-value">${offline}</span><span class="dash-stat-label">Offline</span></div>
    <div class="dash-stat disabled"><span class="dash-stat-value">${disabled}</span><span class="dash-stat-label">Desativadas</span></div>
  `;
}

function updateSourceCard(card, updated) {
  const st = statusLabel(updated.status, updated.available);
  const dot = card.querySelector(".status-dot");
  if (dot) { dot.className = `status-dot ${st.cls}`; }

  const barsWrap = card.querySelector(".signal-bars-wrap");
  if (barsWrap) barsWrap.innerHTML = signalBarsHtml(updated);

  const errEl = card.querySelector(".source-error");
  if (updated.error && !updated.available) {
    if (!errEl) {
      const p = document.createElement("p");
      p.className = "source-error";
      p.innerHTML = `${escapeHtml(updated.error)}`;
      card.appendChild(p);
    } else {
      errEl.innerHTML = `${escapeHtml(updated.error)}`;
    }
  } else if (errEl) {
    errEl.remove();
  }
  card.className = `source-card is-${st.cls}${updated.enabled === false ? " is-disabled" : ""}`;
  card.classList.remove("is-busy");
}

function renderSourceCard(s) {
  const st = statusLabel(s.status, s.available);
  const card = document.createElement("article");
  card.className = `source-card is-${st.cls}${s.enabled ? "" : " is-disabled"}`;
  card.dataset.id = s.identifier;

  const host = hostFromUrl(s.base_url);
  const capBadges = [
    s.has_search ? `<span class="source-cap-badge">Busca</span>` : "",
    s.has_details ? `<span class="source-cap-badge">Detalhes</span>` : "",
  ].filter(Boolean).join("");

  const emblem = sourceEmblemSvg(s.identifier, s.color || "#666");

  card.innerHTML = `
    <div class="source-card-body">
      <span class="source-emblem" style="--src-color:${s.color || "#666"}">${emblem}</span>

      <div class="source-card-titles">
        <div class="source-card-name">${escapeHtml(s.name)}</div>
        <div class="source-card-host">${escapeHtml(host || s.identifier)}</div>
        ${capBadges ? `<div class="source-caps">${capBadges}</div>` : ""}
      </div>

      <div class="signal-bars-wrap">${signalBarsHtml(s)}</div>

      <div class="source-card-controls">
        <span class="status-dot ${st.cls}"></span>
        <button type="button" class="btn-ping" data-ping="${escapeHtml(s.identifier)}" title="Testar agora" aria-label="Testar ${escapeHtml(s.name)}">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>
        </button>
        <label class="switch source-toggle" title="${s.enabled ? "Desativar" : "Ativar"} ${escapeHtml(s.name)}">
          <input type="checkbox" ${s.enabled ? "checked" : ""} data-id="${escapeHtml(s.identifier)}" />
          <span class="switch-slider"></span>
        </label>
      </div>
    </div>
    ${s.error && !s.available ? `<p class="source-error">${escapeHtml(s.error)}</p>` : ""}
  `;

  const input = card.querySelector("input[type=checkbox]");
  input?.addEventListener("change", async () => {
    const enabled = input.checked;
    input.disabled = true;
    card.classList.add("is-busy");
    try {
      await api.setSource(s.identifier, enabled);
      toast(`${s.name} ${enabled ? "ativada" : "desativada"} · atualizando…`);
      state.catalogDirty = true;
      state.episodes = [];
      await loadSources();
      import("../views/home.js").then((m) => m.reloadAfterSourcesChange());
    } catch (e) {
      input.checked = !enabled;
      toast(e.message || "Não foi possível alterar a fonte", true);
      input.disabled = false;
      card.classList.remove("is-busy");
    }
  });

  card.querySelector("[data-ping]")?.addEventListener("click", async (e) => {
    e.preventDefault(); e.stopPropagation();
    const btn = e.currentTarget; btn.disabled = true;
    card.classList.add("is-busy");
    const dot = card.querySelector(".status-dot");
    if (dot) dot.className = "status-dot checking";
    try {
      const updated = await api.refreshSourceHealth(s.identifier);
      updateSourceCard(card, updated);
      btn.disabled = false;
      toast(updated.available
        ? `${updated.name} online · ${formatLatency(updated.latency_ms)}`
        : `${updated.name} offline${updated.error ? ` (${updated.error})` : ""}`,
        !updated.available);
    } catch (err) {
      toast(err.message || "Teste falhou", true);
      btn.disabled = false;
      card.classList.remove("is-busy");
    }
  });

  return card;
}

export async function loadSources({ recheck = false } = {}) {
  const list = $("#sources-list");
  if (!list) return;
  list.innerHTML = `<div class="sources-empty">Carregando fontes…</div>`;
  try {
    await _waitSourcesReady();
    let data;
    if (recheck) {
      toast("Testando fontes…");
      data = await api.refreshSourcesHealth();
    } else {
      data = await api.sources();
    }
    const items = data.items || [];
    if (!items.length) {
      list.innerHTML = `<div class="sources-empty"><strong>Nenhuma fonte</strong>Nenhum site foi encontrado.</div>`;
      const dashboard = $("#sources-dashboard");
      if (dashboard) dashboard.innerHTML = "";
      return;
    }

    renderSourcesDashboard(items);

    const groups = [
      { label: "Online", items: items.filter((s) => s.enabled && s.available), cls: "group-online" },
      { label: "Com problema", items: items.filter((s) => s.enabled && !s.available && s.status !== "unknown"), cls: "group-offline" },
      { label: "Não verificadas", items: items.filter((s) => s.enabled && s.status === "unknown" && !s.available), cls: "group-unknown" },
      { label: "Desativadas", items: items.filter((s) => !s.enabled), cls: "group-disabled" },
    ].filter((g) => g.items.length > 0);

    list.innerHTML = "";
    for (const group of groups) {
      const section = document.createElement("div");
      section.className = `sources-group ${group.cls}`;
      section.innerHTML = `<h4 class="sources-group-label">${group.label} <span class="sources-group-count">${group.items.length}</span></h4>`;
      for (const s of group.items) {
        section.appendChild(renderSourceCard(s));
      }
      list.appendChild(section);
    }
  } catch (e) {
    list.innerHTML = `<div class="sources-empty"><strong>Erro</strong>${escapeHtml(e.message)}</div>`;
  }
}
