import { api, imgUrl } from "../api.js";
import { state } from "../state.js";
import { $, $$, escapeHtml } from "../utils/dom.js";
import { detectAudioVariant, hasAudioChoice } from "../utils/audio.js";
import { audioChoiceBadge } from "../cards.js";
import { waitSourcesReady as _waitSourcesReady } from "../search.js";
import { toast, toastLoading } from "../toast.js";
import { pickAnimeSourceThenOpen, navigateToAnimeSource } from "../play-flow.js";
import { stripTitleVariants } from "../utils/titles.js";

const CALENDAR_CACHE_MS = 5 * 60 * 1000;

export function loadCalendarCheckPref() {
  try {
    return localStorage.getItem("anishelf.calendarCheckSources") === "1";
  } catch {
    return false;
  }
}

export function saveCalendarCheckPref(on) {
  try {
    localStorage.setItem("anishelf.calendarCheckSources", on ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export async function loadCalendarPage({ force = false } = {}) {
  const board = $("#calendar-board");
  const status = $("#calendar-status");
  const statusText = $("#calendar-status-text");
  const checkEl = $("#calendar-check-sources");

  if (checkEl && checkEl.checked !== !!state.calendarCheckSources) {
    checkEl.checked = !!state.calendarCheckSources;
  }

  const cached = state.calendarCache;
  if (
    !force &&
    cached &&
    cached.days === state.calendarDays &&
    !!cached.check_sources === !!state.calendarCheckSources &&
    Date.now() - cached.at < CALENDAR_CACHE_MS
  ) {
    state.calendarItems = cached.items;
    renderCalendar(cached.items);
    return;
  }

  state.calendarLoading = true;
  if (status) status.hidden = false;
  if (statusText) {
    statusText.textContent = state.calendarCheckSources
      ? "Conferindo episódios nas fontes…"
      : "Carregando…";
  }
  if (board && !state.calendarItems.length) {
    board.innerHTML = `<div class="empty-state">Buscando próximos episódios…</div>`;
  }
  syncCalendarRangeButtons();

  try {
    if (state.calendarCheckSources) {
      await _waitSourcesReady();
    }
    const data = await api.calendar(
      state.calendarDays,
      !!state.calendarCheckSources
    );
    const items = data.items || [];
    state.calendarItems = items;
    state.calendarCache = {
      days: state.calendarDays,
      check_sources: !!state.calendarCheckSources,
      items,
      at: Date.now(),
      total: data.total,
      available_total: data.available_total,
    };
    renderCalendar(items);
  } catch (e) {
    if (board) {
      board.innerHTML = `<div class="empty-state"><strong>Calendário indisponível</strong>${escapeHtml(
        e.message || "Tente novamente."
      )}</div>`;
    }
    toast(e.message || "Não foi possível carregar o calendário", true);
  } finally {
    state.calendarLoading = false;
    if (status) status.hidden = true;
  }
}

export function syncCalendarRangeButtons() {
  $$("#calendar-range .range-btn").forEach((btn) => {
    const d = Number(btn.dataset.days);
    btn.classList.toggle("active", d === state.calendarDays);
  });
  const checkEl = $("#calendar-check-sources");
  if (checkEl) checkEl.checked = !!state.calendarCheckSources;
}

export function renderCalendar(items) {
  const board = $("#calendar-board");
  if (!board) return;

  const checking = !!state.calendarCheckSources;
  const groups = groupAiringByLocalDay(items || [], state.calendarDays);
  const hasAny = groups.some((g) => g.items.length > 0);
  if (!hasAny) {
    board.innerHTML = `<div class="empty-state"><strong>Nada neste período</strong>Sem episódios nos próximos ${state.calendarDays} dias.</div>`;
    return;
  }

  board.innerHTML = "";
  const frag = document.createDocumentFragment();
  const todayKey = localDateKey(new Date());

  for (const g of groups) {
    if (!g.items.length) continue;
    const day = document.createElement("section");
    day.className = "calendar-day" + (g.key === todayKey ? " is-today" : "");
    const label = formatCalendarDayLabel(g.key, todayKey);
    const avail = g.items.filter((i) => i.available === true).length;
    const countLabel = checking
      ? `${g.items.length} ep · ${avail} disponíveis`
      : `${g.items.length} ep${g.items.length === 1 ? "" : "s"}`;
    day.innerHTML = `
      <div class="calendar-day-head">
        <div class="calendar-day-title">
          ${escapeHtml(label.title)}
          <small>${escapeHtml(label.sub)}</small>
        </div>
        <span class="calendar-day-count">${escapeHtml(countLabel)}</span>
      </div>
      <div class="calendar-list"></div>
    `;
    const list = day.querySelector(".calendar-list");
    for (const item of g.items) {
      list.appendChild(calendarRow(item, { checking }));
    }
    frag.appendChild(day);
  }
  board.appendChild(frag);
}

function localDateKey(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function groupAiringByLocalDay(items, days) {
  const map = new Map();
  for (const item of items) {
    const ts = Number(item.airing_at) * 1000;
    if (!ts) continue;
    const key = localDateKey(new Date(ts));
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(item);
  }

  const out = [];
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  for (let i = 0; i < days; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    const key = localDateKey(d);
    const dayItems = (map.get(key) || []).slice().sort(
      (a, b) => Number(a.airing_at) - Number(b.airing_at)
    );
    out.push({ key, items: dayItems });
  }
  return out;
}

function formatCalendarDayLabel(key, todayKey) {
  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const weekday = date.toLocaleDateString("pt-BR", { weekday: "long" });
  const full = date.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
  });
  const cap = weekday.charAt(0).toUpperCase() + weekday.slice(1);
  if (key === todayKey) {
    return { title: "Hoje", sub: `${cap} · ${full}` };
  }
  const tomorrow = new Date();
  tomorrow.setHours(0, 0, 0, 0);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (key === localDateKey(tomorrow)) {
    return { title: "Amanhã", sub: `${cap} · ${full}` };
  }
  return { title: cap, sub: full };
}

function calendarRow(item, { checking = false } = {}) {
  const btn = document.createElement("button");
  btn.type = "button";
  const available =
    checking &&
    item.available === true &&
    (item.sources || []).some((s) => s?.link || s?.episode_link);
  const unavailable = checking && item.available === false;
  btn.className =
    "calendar-row" +
    (available ? " is-available" : "") +
    (unavailable ? " is-unavailable" : "");
  const when = new Date(Number(item.airing_at) * 1000);
  const time = when.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const relative = formatTimeUntil(item.airing_at);
  const poster = imgUrl(item.source_image || item.image);
  const sourceNames = (item.sources || []).map((s) => s.name).filter(Boolean);
  let unavailHint = "Episódio ainda não está nas fontes";
  if (item.unavailable_reason === "anime_only") {
    unavailHint = "Anime nas fontes, episódio ainda não";
  } else if (item.unavailable_reason === "episode_unknown") {
    unavailHint = "Sem número de episódio para conferir";
  } else if (unavailable) {
    unavailHint = "Não está nas fontes ativas";
  }
  const sub = [
    available ? sourceNames.slice(0, 2).join(" · ") : null,
    unavailable ? unavailHint : null,
    item.format_label,
    item.score != null ? `★ ${(item.score / 10).toFixed(1)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const ep =
    item.episode != null && item.episode !== ""
      ? `Ep ${item.episode}`
      : "Ep ?";
  const badges = [];
  if (checking) {
    badges.push(
      available
        ? `<span class="cal-badge cal-badge-ok">disponível</span>`
        : `<span class="cal-badge cal-badge-off">indisponível</span>`
    );
  }
  const audioSources = (item.sources || []).map((s) => ({
    ...s,
    link: s.link || s.episode_link || "",
    variant:
      s.variant ||
      detectAudioVariant(s.title || item.source_title || item.title || "", s.link || s.episode_link || ""),
  }));
  badges.push(audioChoiceBadge(audioSources, "cal"));

  btn.innerHTML = `
    <div class="calendar-time">
      ${relative ? `<strong>${escapeHtml(relative)}</strong>` : escapeHtml(time)}
      <small>${escapeHtml(time)}</small>
    </div>
    <div class="calendar-thumb" style="${
      poster ? `background-image:url('${poster}')` : ""
    }"></div>
    <div class="calendar-info">
      <div class="calendar-title-row">
        <div class="calendar-title">${escapeHtml(item.source_title || item.title || "Anime")}</div>
        <div class="calendar-badges">${badges.filter(Boolean).join("")}</div>
      </div>
      <div class="calendar-sub">${escapeHtml(sub)}</div>
    </div>
    <span class="calendar-ep">${escapeHtml(ep)}</span>
  `;
  btn.addEventListener("click", () => openCalendarItem(item, { checking }));
  return btn;
}

function formatTimeUntil(airingAt) {
  const ts = Number(airingAt) * 1000;
  if (!ts) return "";
  const diff = ts - Date.now();
  if (diff < 0) return "agora";
  const mins = Math.round(diff / 60000);
  if (mins < 60) return `em ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) {
    const rem = mins % 60;
    return rem ? `em ${hours} h ${rem} min` : `em ${hours} h`;
  }
  const days = Math.floor(hours / 24);
  return days === 1 ? "em 1 dia" : `em ${days} dias`;
}

async function openCalendarItem(item, { checking = false } = {}) {
  const title = item.source_title || item.title || item.media?.title || "";

  if (checking) {
    const sources = (item.sources || [])
      .map((s) => ({
        ...s,
        link: s.link || s.episode_link || "",
        variant:
          s.variant ||
          detectAudioVariant(s.title || title, s.link || s.episode_link || ""),
        title: s.title || title,
      }))
      .filter((s) => s.link);
    if (sources.length) {
      pickAnimeSourceThenOpen(title, sources, { anilistId: item.id || "" });
      return;
    }
    const ep =
      item.episode != null && item.episode !== "" ? ` ep ${item.episode}` : "";
    if (item.unavailable_reason === "anime_only") {
      toast(
        title
          ? `"${title}"${ep} ainda não está nas fontes`
          : "Episódio ainda não está nas fontes",
        true
      );
      return;
    }
    toast(
      title
        ? `"${title}"${ep} indisponível nas fontes`
        : "Indisponível nas fontes ativas",
      true
    );
    return;
  }

  if (!title) {
    toast("Título inválido", true);
    return;
  }
  toast(`Procurando ${title}…`);
  try {
    await _waitSourcesReady();
    const data = await api.search(title);
    const hit = (data.items || [])[0];
    pickAnimeSourceThenOpen(title, hit?.sources || [], {
      anilistId: item.id || "",
    });
  } catch (e) {
    toast(e.message || "Busca falhou", true);
  }
}
