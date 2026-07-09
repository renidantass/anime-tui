/** Player de vídeo (MP4 / HLS) com progresso, skip de opening e fallback de fonte. */

import { api } from "./api.js";

let hls = null;
let progressTimer = null;
let currentEpisodeLink = "";
let onCloseCb = null;
let activeOpts = null;
let retrying = false;

/** Já pulou a OP neste episódio. */
let introSkipped = false;
/** Aguardando o usuário posicionar no fim da OP para salvar. */
let markIntroMode = false;
/**
 * Intervalo da opening atual: { start, end, source: 'aniskip'|'local' } | null
 */
let introInterval = null;
let skipFetchToken = 0;

const SKIP_INTRO_MIN_DURATION = 180;
const SKIP_INTRO_HIDE_BEFORE = 2;
/** Fallback quando não há AniSkip nem marcação local. */
const SKIP_INTRO_DEFAULT_END = 85;
const ANISKIP_BASE = "https://api.aniskip.com/v2/skip-times";
const LOCAL_INTRO_KEY = "anishelf.introEnds";

const $ = (sel) => document.querySelector(sel);

function animeStorageKey(title) {
  return String(title || "")
    .trim()
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ");
}

function loadLocalIntroMap() {
  try {
    const raw = localStorage.getItem(LOCAL_INTRO_KEY);
    const obj = raw ? JSON.parse(raw) : {};
    return obj && typeof obj === "object" ? obj : {};
  } catch {
    return {};
  }
}

function getLocalIntroEnd(animeTitle) {
  const key = animeStorageKey(animeTitle);
  if (!key) return null;
  const n = Number(loadLocalIntroMap()[key]);
  return Number.isFinite(n) && n >= 20 && n <= 240 ? n : null;
}

function saveLocalIntroEnd(animeTitle, endSeconds) {
  const key = animeStorageKey(animeTitle);
  if (!key) return;
  const end = Math.round(Number(endSeconds) * 10) / 10;
  if (!Number.isFinite(end) || end < 20 || end > 240) return;
  const map = loadLocalIntroMap();
  map[key] = end;
  try {
    localStorage.setItem(LOCAL_INTRO_KEY, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

function setSkipIntroVisible(show) {
  const btn = $("#btn-skip-intro");
  if (!btn) return;
  btn.hidden = !show;
}

function setSkipIntroLabel(mode) {
  const btn = $("#btn-skip-intro");
  if (!btn) return;
  const label = btn.querySelector(".btn-skip-intro-label") || btn;
  if (mode === "mark") {
    if (btn.querySelector(".btn-skip-intro-label")) {
      btn.querySelector(".btn-skip-intro-label").textContent = "Salvar fim da OP";
    } else {
      // estrutura: svg + texto
      const texts = [...btn.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE);
      // fallback: reescreve innerHTML parcial
      const svg = btn.querySelector("svg");
      btn.innerHTML = "";
      if (svg) btn.appendChild(svg);
      const span = document.createElement("span");
      span.className = "btn-skip-intro-label";
      span.textContent = "Salvar fim da OP";
      btn.appendChild(span);
    }
    btn.title = "Posicione no fim da opening e clique para salvar (deste anime)";
    btn.classList.add("is-mark-mode");
  } else {
    const span = btn.querySelector(".btn-skip-intro-label");
    if (span) span.textContent = "Pular abertura";
    else {
      const svg = btn.querySelector("svg");
      btn.innerHTML = "";
      if (svg) btn.appendChild(svg);
      const s = document.createElement("span");
      s.className = "btn-skip-intro-label";
      s.textContent = "Pular abertura";
      btn.appendChild(s);
    }
    btn.title = "Pular a opening deste episódio (tecla S)";
    btn.classList.remove("is-mark-mode");
  }
}

function ensureSkipButtonStructure() {
  const btn = $("#btn-skip-intro");
  if (!btn || btn.querySelector(".btn-skip-intro-label")) return;
  const svg = btn.querySelector("svg");
  const text = (btn.textContent || "Pular abertura").replace(/\s+/g, " ").trim();
  btn.textContent = "";
  if (svg) btn.appendChild(svg);
  const span = document.createElement("span");
  span.className = "btn-skip-intro-label";
  span.textContent = text || "Pular abertura";
  btn.appendChild(span);
}

/**
 * Busca intervalos de OP no AniSkip (crowd-sourced por MAL id + episódio).
 * @returns {Promise<{start:number,end:number}|null>}
 */
async function fetchAniSkipOp(malId, episodeNumber, episodeLength) {
  const mal = Number(malId);
  const ep = Number(episodeNumber);
  if (!Number.isFinite(mal) || mal <= 0) return null;
  if (!Number.isFinite(ep) || ep <= 0) return null;
  const len =
    Number.isFinite(episodeLength) && episodeLength > 0
      ? Math.round(episodeLength)
      : 1440;
  const types = ["op"];
  const qs = new URLSearchParams();
  for (const t of types) qs.append("types[]", t);
  qs.set("episodeLength", String(len));
  const url = `${ANISKIP_BASE}/${mal}/${ep}?${qs.toString()}`;
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data?.found || !Array.isArray(data.results)) return null;
    const ops = data.results.filter(
      (r) => (r.skipType || r.skip_type) === "op" && r.interval
    );
    if (!ops.length) return null;
    // prefere o intervalo de OP mais longo (marcação mais completa)
    ops.sort((a, b) => {
      const ea = Number(a.interval.endTime ?? a.interval.end_time) || 0;
      const sa = Number(a.interval.startTime ?? a.interval.start_time) || 0;
      const eb = Number(b.interval.endTime ?? b.interval.end_time) || 0;
      const sb = Number(b.interval.startTime ?? b.interval.start_time) || 0;
      return eb - sb - (ea - sa);
    });
    const best = ops[0];
    const start = Number(best.interval.startTime ?? best.interval.start_time);
    const end = Number(best.interval.endTime ?? best.interval.end_time);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start + 5) {
      return null;
    }
    return { start: Math.max(0, start), end };
  } catch {
    return null;
  }
}

async function resolveIntroInterval({
  malId,
  episodeNumber,
  animeTitle,
  episodeLength,
  token,
}) {
  // 1) AniSkip (timestamps reais por episódio)
  const fromApi = await fetchAniSkipOp(malId, episodeNumber, episodeLength);
  if (token !== skipFetchToken) return; // episódio mudou
  if (fromApi) {
    introInterval = { ...fromApi, source: "aniskip" };
    markIntroMode = false;
    setSkipIntroLabel("skip");
    updateSkipIntroButton();
    return;
  }

  // 2) Aprendizado local por anime (você marcou o fim da OP uma vez)
  const localEnd = getLocalIntroEnd(animeTitle);
  if (token !== skipFetchToken) return;
  if (localEnd != null) {
    introInterval = { start: 0, end: localEnd, source: "local" };
    markIntroMode = false;
    setSkipIntroLabel("skip");
    updateSkipIntroButton();
    return;
  }

  // 3) Sem dados: modo “marcar fim da OP”
  if (token !== skipFetchToken) return;
  introInterval = null;
  markIntroMode = false;
  setSkipIntroLabel("skip");
  updateSkipIntroButton();
}

function effectiveIntroEnd(duration) {
  // 1) AniSkip / marcação local
  if (introInterval && Number.isFinite(introInterval.end)) {
    return Math.min(introInterval.end, Math.max(0, duration - 5));
  }
  // 2) padrão 85s quando não há dados
  if (Number.isFinite(duration) && duration > SKIP_INTRO_DEFAULT_END + 20) {
    return Math.min(SKIP_INTRO_DEFAULT_END, Math.max(0, duration - 5));
  }
  return null;
}

function updateSkipIntroButton() {
  const video = $("#video");
  const modal = $("#player-modal");
  if (!video || !modal || modal.hidden) {
    setSkipIntroVisible(false);
    return;
  }
  const duration = video.duration;
  const t = video.currentTime || 0;
  if (
    introSkipped ||
    !Number.isFinite(duration) ||
    duration < SKIP_INTRO_MIN_DURATION ||
    video.ended
  ) {
    setSkipIntroVisible(false);
    return;
  }

  // Modo marcar (opcional, clique longo): salvar fim da OP deste anime
  if (markIntroMode) {
    setSkipIntroLabel("mark");
    setSkipIntroVisible(t >= 15 && t < duration - 10);
    return;
  }

  const end = effectiveIntroEnd(duration);
  if (end == null) {
    setSkipIntroVisible(false);
    return;
  }

  const start = Math.max(0, Number(introInterval?.start) || 0);
  // mostra um pouco antes da OP e durante ela (ou 0→85s no fallback)
  const showFrom = Math.max(0, start - 3);
  setSkipIntroLabel("skip");
  setSkipIntroVisible(t >= showFrom && t < end - SKIP_INTRO_HIDE_BEFORE);
}

function toastSkip(msg) {
  // reusa toast global se existir
  try {
    const el = document.getElementById("toast");
    if (!el) return;
    el.hidden = false;
    el.textContent = msg;
    clearTimeout(toastSkip._t);
    toastSkip._t = setTimeout(() => {
      el.hidden = true;
    }, 3200);
  } catch {
    /* ignore */
  }
}

function skipIntro() {
  const video = $("#video");
  if (!video) return;
  const duration = video.duration;
  if (!Number.isFinite(duration) || duration < 30) return;

  // Finaliza marcação manual
  if (markIntroMode) {
    const end = video.currentTime;
    if (end < 20) {
      toastSkip("Posicione mais adiante — no fim da opening");
      return;
    }
    const title = activeOpts?.title || "";
    saveLocalIntroEnd(title, end);
    introInterval = { start: 0, end, source: "local" };
    markIntroMode = false;
    introSkipped = true;
    setSkipIntroVisible(false);
    setSkipIntroLabel("skip");
    toastSkip(`Opening salva (~${Math.round(end)}s) para este anime`);
    video.play().catch(() => {});
    reportProgress(false);
    return;
  }

  const end = effectiveIntroEnd(duration);
  if (end == null) {
    // ep curto demais até para o padrão 85s
    setSkipIntroVisible(false);
    return;
  }

  const target = Math.min(end, Math.max(0, duration - 5));
  const usedDefault = !introInterval;
  try {
    video.currentTime = target;
  } catch {
    /* ignore */
  }
  introSkipped = true;
  setSkipIntroVisible(false);
  if (usedDefault) {
    toastSkip(`Opening sem marcação · pulou ${Math.round(target)}s`);
  }
  video.play().catch(() => {});
  reportProgress(false);
}

async function resolveMalIdIfNeeded(animeTitle, knownMal) {
  if (knownMal && Number(knownMal) > 0) return Number(knownMal);
  const title = String(animeTitle || "").trim();
  if (!title || title.length < 2) return null;
  try {
    const meta = await api.meta(title);
    const mal = meta?.mal_id;
    if (mal && Number(mal) > 0) {
      if (activeOpts) {
        activeOpts.malId = Number(mal);
        activeOpts.playMeta = {
          ...(activeOpts.playMeta || {}),
          mal_id: Number(mal),
        };
      }
      return Number(mal);
    }
  } catch {
    /* meta opcional */
  }
  return null;
}

function scheduleIntroResolve() {
  const video = $("#video");
  const token = ++skipFetchToken;
  const episodeNumber =
    activeOpts?.episodeNumber ||
    activeOpts?.playMeta?.episode_number ||
    null;
  const animeTitle = activeOpts?.title || activeOpts?.playMeta?.anime_title || "";
  const episodeLength =
    video && Number.isFinite(video.duration) && video.duration > 0
      ? video.duration
      : activeOpts?.episodeLength || null;

  const knownMal = activeOpts?.malId || activeOpts?.playMeta?.mal_id || null;

  (async () => {
    const malId = await resolveMalIdIfNeeded(animeTitle, knownMal);
    if (token !== skipFetchToken) return;
    await resolveIntroInterval({
      malId,
      episodeNumber,
      animeTitle,
      episodeLength,
      token,
    });
  })();
}

export function initPlayer({ onClose } = {}) {
  onCloseCb = onClose;
  ensureSkipButtonStructure();
  $("#player-close")?.addEventListener("click", closePlayer);
  $("#btn-skip-intro")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    skipIntro();
  });
  // clique longo: marcar fim da OP manualmente (salva para o anime)
  let markHoldTimer = null;
  $("#btn-skip-intro")?.addEventListener("pointerdown", () => {
    clearTimeout(markHoldTimer);
    markHoldTimer = setTimeout(() => {
      markIntroMode = true;
      setSkipIntroLabel("mark");
      toastSkip("Modo marcar: vá ao fim da OP e clique em Salvar");
      updateSkipIntroButton();
    }, 650);
  });
  const clearMarkHold = () => {
    clearTimeout(markHoldTimer);
    markHoldTimer = null;
  };
  $("#btn-skip-intro")?.addEventListener("pointerup", clearMarkHold);
  $("#btn-skip-intro")?.addEventListener("pointerleave", clearMarkHold);
  $("#btn-skip-intro")?.addEventListener("pointercancel", clearMarkHold);
  document.addEventListener("keydown", (e) => {
    if ($("#player-modal")?.hidden) return;
    if (e.key === "Escape") {
      closePlayer();
      return;
    }
    if (
      (e.key === "s" || e.key === "S") &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.altKey
    ) {
      const tag = (e.target?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || e.target?.isContentEditable) {
        return;
      }
      if (!$("#btn-skip-intro")?.hidden || markIntroMode) {
        e.preventDefault();
        skipIntro();
      }
    }
  });

  const video = $("#video");
  video?.addEventListener("ended", () => {
    reportProgress(true);
    setSkipIntroVisible(false);
  });
  video?.addEventListener("timeupdate", updateSkipIntroButton);
  video?.addEventListener("loadedmetadata", () => {
    // com duração real, AniSkip acerta melhor o match
    scheduleIntroResolve();
    updateSkipIntroButton();
  });
  video?.addEventListener("play", updateSkipIntroButton);
  video?.addEventListener("seeked", updateSkipIntroButton);
}

function showLoading(show, msg) {
  const el = $("#player-loading");
  if (!el) return;
  el.hidden = !show;
  const p = el.querySelector("p");
  if (p && msg) p.textContent = msg;
  else if (p && show) p.textContent = "Abrindo vídeo…";
}

function showFallback(url) {
  const fb = $("#player-fallback");
  const a = $("#player-external");
  if (fb) fb.hidden = false;
  if (a) {
    a.href = url || "#";
    a.style.display = url ? "" : "none";
  }
  showLoading(false);
  setSkipIntroVisible(false);
}

function destroyHls() {
  if (hls) {
    try {
      hls.destroy();
    } catch {
      /* ignore */
    }
    hls = null;
  }
}

function startProgressLoop() {
  stopProgressLoop();
  progressTimer = setInterval(() => reportProgress(false), 8000);
}

function stopProgressLoop() {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
}

async function reportProgress(finished) {
  if (!currentEpisodeLink) return;
  const video = $("#video");
  if (!video || !video.duration || !Number.isFinite(video.duration)) return;
  const pos = finished ? video.duration : video.currentTime;
  try {
    await api.progress({
      episode_link: currentEpisodeLink,
      progress_seconds: pos,
      duration_seconds: video.duration,
    });
  } catch {
    /* silencioso */
  }
}

export function closePlayer() {
  const modal = $("#player-modal");
  const video = $("#video");
  reportProgress(false);
  stopProgressLoop();
  destroyHls();
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.load();
  }
  currentEpisodeLink = "";
  activeOpts = null;
  retrying = false;
  introSkipped = false;
  markIntroMode = false;
  introInterval = null;
  skipFetchToken += 1;
  setSkipIntroVisible(false);
  if (modal) modal.hidden = true;
  document.body.style.overflow = "";
  onCloseCb?.();
}

/**
 * Se o stream falhar no <video>, tenta próximas fontes candidatas.
 */
async function tryNextCandidate(reason) {
  if (retrying || !activeOpts) {
    showFallback(activeOpts?.externalUrl || activeOpts?.pageUrl);
    return;
  }
  const rest = activeOpts.fallbackCandidates || [];
  if (!rest.length) {
    showFallback(activeOpts.externalUrl || activeOpts.pageUrl);
    return;
  }

  retrying = true;
  const next = rest[0];
  const remaining = rest.slice(1);
  showLoading(true, `Fonte falhou · tentando ${next.name || "outra"}…`);

  const meta = activeOpts.playMeta || {};
  try {
    const res = await api.play({
      preferred_source: next.name,
      episode_link: next.link,
      candidates: [next, ...remaining],
      anime_title: meta.anime_title || activeOpts.title || "",
      episode_title: meta.episode_title || "",
      episode_number: meta.episode_number || "0",
      anime_image: meta.anime_image || "",
      season_number: meta.season_number || 1,
      source_color: next.color || "",
    });

    activeOpts = {
      ...activeOpts,
      playable: res.playable,
      streamUrl: res.stream_url,
      isHls: res.is_hls,
      startAt: res.start_at ?? activeOpts.startAt,
      pageUrl: res.page_url,
      externalUrl: res.external_url,
      episodeLink: res.episode_link || next.link,
      episodeLabel: [
        meta.episode_number && meta.episode_number !== "?"
          ? `Ep ${meta.episode_number}`
          : "Ep",
        res.source_name || next.name,
      ]
        .filter(Boolean)
        .join(" · "),
      fallbackCandidates: remaining.filter(
        (c) => c.link !== (res.episode_link || next.link)
      ),
    };
    $("#player-ep").textContent = activeOpts.episodeLabel || "";
    currentEpisodeLink = activeOpts.episodeLink || "";
    retrying = false;

    if (!res.playable || !res.stream_url) {
      await tryNextCandidate(reason);
      return;
    }
    await attachStream(activeOpts);
  } catch {
    retrying = false;
    activeOpts.fallbackCandidates = remaining;
    await tryNextCandidate(reason);
  }
}

function onStreamFatal() {
  tryNextCandidate("playback error");
}

async function attachStream(opts) {
  const video = $("#video");
  if (!video) return;

  destroyHls();
  const fb = $("#player-fallback");
  if (fb) fb.hidden = true;
  showLoading(true);
  setSkipIntroVisible(false);

  if (!opts.playable || !opts.streamUrl) {
    await tryNextCandidate("not playable");
    return;
  }

  const startAt = Math.max(0, Number(opts.startAt) || 0);
  const url = opts.streamUrl;

  const onReady = () => {
    showLoading(false);
    if (startAt > 2) {
      const seek = () => {
        try {
          video.currentTime = startAt;
        } catch {
          /* ignore */
        }
        video.removeEventListener("loadedmetadata", seek);
      };
      if (video.readyState >= 1) seek();
      else video.addEventListener("loadedmetadata", seek);
    }
    video.play().catch(() => {});
    startProgressLoop();
    scheduleIntroResolve();
    updateSkipIntroButton();
  };

  try {
    if (opts.isHls || url.includes(".m3u8")) {
      if (window.Hls && window.Hls.isSupported()) {
        hls = new window.Hls({
          enableWorker: true,
          xhrSetup(xhr) {
            xhr.withCredentials = false;
          },
        });
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(window.Hls.Events.MANIFEST_PARSED, onReady);
        hls.on(window.Hls.Events.ERROR, (_e, data) => {
          if (data?.fatal) onStreamFatal();
        });
        return;
      }
      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = url;
        video.addEventListener("loadedmetadata", onReady, { once: true });
        video.addEventListener("error", onStreamFatal, { once: true });
        return;
      }
      await tryNextCandidate("hls unsupported");
      return;
    }

    video.src = url;
    video.addEventListener("loadeddata", onReady, { once: true });
    video.addEventListener("error", onStreamFatal, { once: true });
  } catch {
    await tryNextCandidate("attach failed");
  }
}

/**
 * @param {object} opts
 */
export async function openPlayer(opts) {
  const modal = $("#player-modal");
  const video = $("#video");
  const fb = $("#player-fallback");
  if (!modal || !video) return;

  destroyHls();
  if (fb) fb.hidden = true;
  showLoading(true);
  retrying = false;
  introSkipped = false;
  markIntroMode = false;
  introInterval = null;
  skipFetchToken += 1;
  setSkipIntroVisible(false);
  ensureSkipButtonStructure();
  setSkipIntroLabel("skip");

  activeOpts = {
    ...opts,
    fallbackCandidates: [...(opts.fallbackCandidates || [])],
  };

  $("#player-title").textContent = opts.title || "Tocando";
  $("#player-ep").textContent = opts.episodeLabel || "";
  currentEpisodeLink = opts.episodeLink || "";

  modal.hidden = false;
  document.body.style.overflow = "hidden";

  // retomada depois da OP → não mostra pular
  const startAt = Math.max(0, Number(opts.startAt) || 0);
  const localEnd = getLocalIntroEnd(opts.title || "");
  const pastEnd =
    localEnd != null ? localEnd : SKIP_INTRO_DEFAULT_END;
  if (startAt >= pastEnd - SKIP_INTRO_HIDE_BEFORE) {
    introSkipped = true;
  }

  // tenta resolver AniSkip cedo (com length estimado); re-resolve no metadata
  scheduleIntroResolve();

  await attachStream(activeOpts);
}
