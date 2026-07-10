import { api } from "../api.js";
import {
  p, $video, $modal, $skipBtn,
  SKIP_INTRO_MIN_DURATION, SKIP_INTRO_DEFAULT_END, SKIP_INTRO_HIDE_BEFORE,
  getLocalIntroEnd, saveLocalIntroEnd,
  getOpeningMark, saveOpeningMark,
  setSkipIntroVisible, setSkipIntroLabel, setMarkBtnActive, ensureSkipButtonStructure,
} from "./state.js";

function parseAniSkipOpPayload(data) {
  if (!data?.found || !Array.isArray(data.results)) return null;
  const ops = data.results.filter(
    (r) => (r.skipType || r.skip_type) === "op" && r.interval
  );
  if (!ops.length) return null;
  ops.sort((a, b) => {
    const eA = Number(a.interval.endTime ?? a.interval.end_time) || 0;
    const sA = Number(a.interval.startTime ?? a.interval.start_time) || 0;
    const eB = Number(b.interval.endTime ?? b.interval.end_time) || 0;
    const sB = Number(b.interval.startTime ?? b.interval.start_time) || 0;
    return eB - sB - (eA - sA);
  });
  const best = ops[0];
  const start = Number(best.interval.startTime ?? best.interval.start_time);
  const end = Number(best.interval.endTime ?? best.interval.end_time);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start + 5) return null;
  return { start: Math.max(0, start), end };
}

async function fetchAniSkipOp(malId, episodeNumber, episodeLength) {
  const mal = Number(malId);
  const ep = Number(episodeNumber);
  if (!Number.isFinite(mal) || mal <= 0) return null;
  if (!Number.isFinite(ep) || ep <= 0) return null;
  const len = Number.isFinite(episodeLength) && episodeLength > 60 ? episodeLength : 0;
  try {
    const data = await api.skipTimes(mal, ep, len, "op");
    return parseAniSkipOpPayload(data);
  } catch { return null; }
}

async function resolveIntroInterval({ malId, episodeNumber, animeTitle, seasonNumber, episodeLength, token }) {
  try {
    const fromApi = await fetchAniSkipOp(malId, episodeNumber, episodeLength);
    if (token !== p.skipFetchToken) return;
    if (fromApi) {
      p.introInterval = { ...fromApi, source: "aniskip" };
      p.markIntroMode = false;
      setMarkBtnActive(false);
      setSkipIntroLabel("skip");
      updateSkipIntroButton();
      return;
    }

    // tenta marcação por temporada (backend)
    const seasonEnd = await getOpeningMark(animeTitle, seasonNumber);
    if (token !== p.skipFetchToken) return;
    if (seasonEnd != null) {
      p.introInterval = { start: 0, end: seasonEnd, source: "season" };
      p.markIntroMode = false;
      setMarkBtnActive(false);
      setSkipIntroLabel("skip");
      updateSkipIntroButton();
      return;
    }

    // fallback para marcação local antiga (por título)
    const localEnd = getLocalIntroEnd(animeTitle);
    if (token !== p.skipFetchToken) return;
    if (localEnd != null) {
      p.introInterval = { start: 0, end: localEnd, source: "local" };
      p.markIntroMode = false;
      setMarkBtnActive(false);
      setSkipIntroLabel("skip");
      updateSkipIntroButton();
      return;
    }

    if (token !== p.skipFetchToken) return;
    p.introInterval = null;
    p.markIntroMode = false;
    setMarkBtnActive(false);
    setSkipIntroLabel("skip");
    updateSkipIntroButton();
  } finally {
    if (token === p.skipFetchToken) p.introResolveSettled = true;
  }
}

function effectiveIntroEnd(duration) {
  if (p.introInterval && Number.isFinite(p.introInterval.end)) {
    return Math.min(p.introInterval.end, Math.max(0, duration - 5));
  }
  if (Number.isFinite(duration) && duration > SKIP_INTRO_DEFAULT_END + 20) {
    return Math.min(SKIP_INTRO_DEFAULT_END, Math.max(0, duration - 5));
  }
  return null;
}

function clearSkipIntroAutoHide() {
  if (p.skipIntroShowTimer) {
    clearTimeout(p.skipIntroShowTimer);
    p.skipIntroShowTimer = null;
  }
}

export function updateSkipIntroButton() {
  const video = $video();
  const modal = $modal();
  if (!video || !modal || modal.hidden) {
    clearSkipIntroAutoHide();
    p.skipIntroShownForInterval = false;
    setSkipIntroVisible(false);
    return;
  }
  const duration = video.duration;
  const t = video.currentTime || 0;
  if (!Number.isFinite(duration) || duration < SKIP_INTRO_MIN_DURATION || video.ended) {
    clearSkipIntroAutoHide();
    p.skipIntroShownForInterval = false;
    setSkipIntroVisible(false);
    return;
  }

  const endProbe = effectiveIntroEnd(duration);
  if (p.introSkipped && endProbe != null && t < endProbe - SKIP_INTRO_HIDE_BEFORE) {
    p.introSkipped = false;
    p.skipIntroShownForInterval = false;
  }

  if (p.markIntroMode) {
    clearSkipIntroAutoHide();
    p.skipIntroShownForInterval = false;
    setSkipIntroLabel("mark");
    setSkipIntroVisible(t >= 15 && t < duration - 10);
    return;
  }

  if (p.introSkipped) {
    clearSkipIntroAutoHide();
    setSkipIntroVisible(false);
    return;
  }

  const end = endProbe;
  if (end == null) {
    clearSkipIntroAutoHide();
    p.skipIntroShownForInterval = false;
    setSkipIntroVisible(false);
    return;
  }

  // Reset when completely past the intro window
  if (t >= end + 2) {
    p.skipIntroShownForInterval = false;
    clearSkipIntroAutoHide();
    setSkipIntroVisible(false);
    return;
  }

  setSkipIntroLabel("skip");
  const inIntroWindow = t < end - SKIP_INTRO_HIDE_BEFORE;
  if (inIntroWindow) {
    if (!p.skipIntroShownForInterval) {
      p.skipIntroShownForInterval = true;
      p.skipIntroShowTimer = setTimeout(() => {
        p.skipIntroShowTimer = null;
        setSkipIntroVisible(false);
      }, 5000);
    }
    // Only show while the auto-hide timer hasn't fired
    if (p.skipIntroShowTimer) {
      setSkipIntroVisible(true);
    }
  } else {
    clearSkipIntroAutoHide();
    setSkipIntroVisible(false);
  }
}

function toastSkip(msg) {
  try {
    const el = document.getElementById("toast");
    if (!el) return;
    el.hidden = false;
    el.textContent = msg;
    clearTimeout(toastSkip._t);
    toastSkip._t = setTimeout(() => { el.hidden = true; }, 3200);
  } catch { /* ignore */ }
}

export async function skipIntro() {
  const video = $video();
  if (!video) return;
  const duration = video.duration;
  if (!Number.isFinite(duration) || duration < 30) return;

  if (p.markIntroMode) {
    const end = video.currentTime;
    if (end < 20) {
      toastSkip("Posicione mais adiante — no fim da opening");
      return;
    }
    const title = p.activeOpts?.title || "";
    const seasonNumber = p.activeOpts?.playMeta?.season_number || 1;
    // salva por temporada no backend + cache local
    saveOpeningMark(title, seasonNumber, end);
    // mantém também no localStorage legado para compatibilidade offline
    saveLocalIntroEnd(title, end);
    p.introInterval = { start: 0, end, source: "season" };
    p.markIntroMode = false;
    setMarkBtnActive(false);
    p.introSkipped = true;
    clearSkipIntroAutoHide();
    setSkipIntroVisible(false);
    setSkipIntroLabel("skip");
    toastSkip(`Opening salva (~${Math.round(end)}s) — ${title} (T${seasonNumber})`);
    video.play().catch(() => {});
    import("./progress.js").then((m) => m.reportProgress(false));
    return;
  }

  if (!p.introResolveSettled && p.introResolvePromise) {
    toastSkip("Buscando abertura…");
    try { await p.introResolvePromise; } catch { /* ignore */ }
  }

  const end = effectiveIntroEnd(duration);
  if (end == null) {
    clearSkipIntroAutoHide();
    setSkipIntroVisible(false);
    return;
  }

  const target = Math.min(end, Math.max(0, duration - 5));
  const src = p.introInterval?.source || "default";
  try { video.currentTime = target; } catch { /* ignore */ }
  p.introSkipped = true;
  clearSkipIntroAutoHide();
  setSkipIntroVisible(false);
  if (src === "default") {
    toastSkip(`Opening sem marcação · pulou ${Math.round(target)}s`);
  } else if (src === "aniskip") {
    const m = Math.floor(target / 60);
    const s = Math.round(target % 60);
    toastSkip(`Abertura pulada · ${m}:${String(s).padStart(2, "0")}`);
  } else if (src === "season") {
    toastSkip(`Abertura pulada · ${Math.round(target)}s (temporada)`);
  } else if (src === "local") {
    toastSkip(`Abertura pulada · ${Math.round(target)}s`);
  }
  video.play().catch(() => {});
  import("./progress.js").then((m) => m.reportProgress(false));
}

async function resolveMalIdIfNeeded(animeTitle, knownMal) {
  if (knownMal && Number(knownMal) > 0) return Number(knownMal);
  const title = String(animeTitle || "").trim();
  if (!title || title.length < 2) return null;
  const variants = [
    title,
    title.replace(/\s*[-–—:|]\s*epis[oó]dio\s*\d+.*$/i, "").trim(),
    title.replace(/\s+ep\s*\d+.*$/i, "").trim(),
  ].filter((t, i, arr) => t && arr.indexOf(t) === i);
  for (const q of variants) {
    try {
      const meta = await api.meta(q);
      const mal = meta?.mal_id;
      if (mal && Number(mal) > 0) {
        if (p.activeOpts) {
          p.activeOpts.malId = Number(mal);
          p.activeOpts.playMeta = {
            ...(p.activeOpts.playMeta || {}),
            mal_id: Number(mal),
          };
        }
        return Number(mal);
      }
    } catch { /* try next variant */ }
  }
  return null;
}

function parseEpisodeNumberLoose(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value) && value > 0) return Math.floor(value);
  const s = String(value);
  const m = s.match(/(?:epis[oó]dio|ep)\s*[#.:]?\s*(\d{1,4})/i) || s.match(/\b(\d{1,4})\b/);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function scheduleIntroResolve({ force = false } = {}) {
  const video = $video();
  const episodeNumber = parseEpisodeNumberLoose(
    p.activeOpts?.episodeNumber ??
      p.activeOpts?.playMeta?.episode_number ??
      p.activeOpts?.episodeLabel ??
      p.activeOpts?.title
  );
  const animeTitle = p.activeOpts?.title || p.activeOpts?.playMeta?.anime_title || "";
  const episodeLength =
    video && Number.isFinite(video.duration) && video.duration > 0
      ? video.duration
      : p.activeOpts?.episodeLength || null;
  const knownMal = p.activeOpts?.malId || p.activeOpts?.playMeta?.mal_id || null;

  const seasonNumber = p.activeOpts?.playMeta?.season_number || 1;

  const key = `${knownMal || animeTitle}|${episodeNumber || "?"}|s${seasonNumber}|${
    episodeLength ? Math.round(episodeLength) : 0
  }`;

  if (!force && p.introResolveKey === key && p.introResolvePromise) {
    return p.introResolvePromise;
  }
  if (
    !force &&
    p.introInterval?.source === "aniskip" &&
    p.introResolveSettled &&
    p.introResolveKey &&
    p.introResolveKey.startsWith(`${knownMal || animeTitle}|${episodeNumber || "?"}|`)
  ) {
    return p.introResolvePromise || Promise.resolve();
  }

  const token = ++p.skipFetchToken;
  p.introResolveKey = key;
  p.introResolveSettled = false;

  p.introResolvePromise = (async () => {
    try {
      const malId = await resolveMalIdIfNeeded(animeTitle, knownMal);
      if (token !== p.skipFetchToken) return;
      await resolveIntroInterval({ malId, episodeNumber, animeTitle, seasonNumber, episodeLength, token });
    } finally {
      if (token === p.skipFetchToken) p.introResolveSettled = true;
    }
  })();

  return p.introResolvePromise;
}
