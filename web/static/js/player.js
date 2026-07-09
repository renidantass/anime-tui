/** Player de vídeo (MP4 / HLS) com progresso no histórico e fallback de fonte. */

import { api } from "./api.js";

let hls = null;
let progressTimer = null;
let currentEpisodeLink = "";
let onCloseCb = null;
let activeOpts = null;
let retrying = false;

const $ = (sel) => document.querySelector(sel);

export function initPlayer({ onClose } = {}) {
  onCloseCb = onClose;
  $("#player-close")?.addEventListener("click", closePlayer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#player-modal")?.hidden) {
      closePlayer();
    }
  });

  const video = $("#video");
  video?.addEventListener("ended", () => {
    reportProgress(true);
  });
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
  activeOpts = {
    ...opts,
    fallbackCandidates: [...(opts.fallbackCandidates || [])],
  };

  $("#player-title").textContent = opts.title || "Tocando";
  $("#player-ep").textContent = opts.episodeLabel || "";
  currentEpisodeLink = opts.episodeLink || "";

  modal.hidden = false;
  document.body.style.overflow = "hidden";

  await attachStream(activeOpts);
}
