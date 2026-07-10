import { $ } from "../utils/dom.js";

const LOCAL_INTRO_KEY = "anishelf.introEnds";
export const SKIP_INTRO_MIN_DURATION = 180;
export const SKIP_INTRO_HIDE_BEFORE = 2;
export const SKIP_INTRO_DEFAULT_END = 85;

export const p = {
  hls: null,
  progressTimer: null,
  currentEpisodeLink: "",
  onCloseCb: null,
  activeOpts: null,
  retrying: false,
  introSkipped: false,
  markIntroMode: false,
  introInterval: null,
  introResolvePromise: null,
  introResolveKey: "",
  introResolveSettled: false,
  skipFetchToken: 0,
  controlsIdleTimer: null,
};

export const $video = () => $("#video");
export const $modal = () => $("#player-modal");
export const $overlay = () => $("#player-overlay");
export const $fb = () => $("#player-fallback");
export const $loading = () => $("#player-loading");
export const $skipBtn = () => $("#btn-skip-intro");
export const $centeredBtn = () => $("#btn-centered-play");
export const $progress = () => $("#player-progress");
export const $progressFill = () => $("#progress-fill");
export const $progressBuffer = () => $("#progress-buffer");
export const $progressThumb = () => $("#progress-thumb");
export const $progressHover = () => $("#progress-hover");
export const $timeCurrent = () => $("#player-time-current");
export const $timeDuration = () => $("#player-time-duration");
export const $btnPlay = () => $("#btn-play");
export const $iconPlay = () => $("#icon-play");
export const $iconPause = () => $("#icon-pause");
export const $btnMute = () => $("#btn-mute");
export const $volumeSlider = () => $("#volume-slider");
export const $volumeFill = () => $("#volume-fill");
export const $volumeThumb = () => $("#volume-thumb");
export const $btnPip = () => $("#btn-pip");
export const $btnDownload = () => $("#btn-download");
export const $btnFullscreen = () => $("#btn-fullscreen");
export const $iconFsEnter = () => $("#icon-fs-enter");
export const $iconFsExit = () => $("#icon-fs-exit");
export const $hint = () => $("#player-hint");
export const $toast = () => document.getElementById("toast");

export function destroyHls() {
  if (p.hls) {
    try { p.hls.destroy(); } catch { /* ignore */ }
    p.hls = null;
  }
}

export function setVideoReady(ready) {
  const video = $video();
  if (!video) return;
  video.classList.toggle("is-ready", !!ready);
}

export function showLoading(show, msg) {
  const el = $loading();
  if (!el) return;
  el.hidden = !show;
  if (show) setVideoReady(false);
  const pEl = el.querySelector("p");
  if (pEl && msg) pEl.textContent = msg;
  else if (pEl && show) pEl.textContent = "Abrindo vídeo…";
}

export function showFallback(url) {
  const fb = $fb();
  const a = document.getElementById("player-external");
  if (fb) fb.hidden = false;
  if (a) {
    a.href = url || "#";
    a.style.display = url ? "" : "none";
  }
  showLoading(false);
  setVideoReady(false);
  setSkipIntroVisible(false);
}

export function ensureSkipButtonStructure() {
  const btn = $skipBtn();
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

export function setSkipIntroLabel(mode) {
  const btn = $skipBtn();
  if (!btn) return;
  const label = btn.querySelector(".btn-skip-intro-label") || btn;
  if (mode === "mark") {
    label.textContent = "Salvar fim da OP";
    btn.title = "Posicione no fim da opening e clique para salvar (deste anime)";
    btn.classList.add("is-mark-mode");
  } else {
    label.textContent = "Pular abertura";
    btn.title = "Pular a opening deste episódio (tecla S)";
    btn.classList.remove("is-mark-mode");
  }
}

export function setSkipIntroVisible(show) {
  const btn = $skipBtn();
  if (!btn) return;
  btn.hidden = !show;
}

export function animeStorageKey(title) {
  return String(title || "").trim().toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ");
}

export function loadLocalIntroMap() {
  try {
    const raw = localStorage.getItem(LOCAL_INTRO_KEY);
    const obj = raw ? JSON.parse(raw) : {};
    return obj && typeof obj === "object" ? obj : {};
  } catch { return {}; }
}

export function getLocalIntroEnd(animeTitle) {
  const key = animeStorageKey(animeTitle);
  if (!key) return null;
  const n = Number(loadLocalIntroMap()[key]);
  return Number.isFinite(n) && n >= 20 && n <= 240 ? n : null;
}

export function saveLocalIntroEnd(animeTitle, endSeconds) {
  const key = animeStorageKey(animeTitle);
  if (!key) return;
  const end = Math.round(Number(endSeconds) * 10) / 10;
  if (!Number.isFinite(end) || end < 20 || end > 240) return;
  const map = loadLocalIntroMap();
  map[key] = end;
  try {
    localStorage.setItem(LOCAL_INTRO_KEY, JSON.stringify(map));
  } catch { /* ignore */ }
}
