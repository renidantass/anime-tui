import {
  p, $video, $modal, $overlay, $skipBtn,
  $centeredBtn, $progress, $progressFill, $progressBuffer, $progressThumb, $progressHover,
  $timeCurrent, $timeDuration, $btnPlay,
  $btnMute, $volumeSlider, $volumeFill, $volumeThumb,
  $btnPip, $btnDownload, $btnFullscreen, $iconFsEnter, $iconFsExit, $hint, $markBtn,
  destroyHls, setVideoReady,
  ensureSkipButtonStructure, setSkipIntroLabel, setMarkBtnActive,
  setSkipIntroVisible, getLocalIntroEnd, getOpeningMark, SKIP_INTRO_DEFAULT_END, SKIP_INTRO_HIDE_BEFORE,
  showLoading, showFallback,
} from "./player/state.js";
import { skipIntro, scheduleIntroResolve, updateSkipIntroButton } from "./player/intro.js";
import { attachStream } from "./player/stream.js";
import { stopProgressLoop, reportProgress } from "./player/progress.js";

function formatTime(s) {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

function showControls(show) {
  const overlay = $overlay();
  if (!overlay) return;
  overlay.classList.toggle("is-idle", !show);
  const shell = overlay.closest(".player-shell");
  if (shell) shell.classList.toggle("is-interactive", show);
}

function scheduleIdleHide() {
  clearTimeout(p.controlsIdleTimer);
  showControls(true);
  const video = $video();
  if (!video || video.paused || video.ended) return;
  p.controlsIdleTimer = setTimeout(() => showControls(false), 3000);
}

function togglePlay() {
  const video = $video();
  if (!video) return;
  if (video.paused) {
    video.play().catch(() => {});
  } else {
    video.pause();
  }
}

function updatePlayButton() {
  const video = $video();
  const playBtn = $btnPlay();
  const centered = $centeredBtn();
  if (!video || !playBtn) return;
  const isPlaying = !video.paused && !video.ended;
  playBtn.classList.toggle("is-playing", isPlaying);
  if (centered) {
    centered.classList.toggle("is-visible", video.paused && video.readyState >= 1);
  }
}

function updateProgress() {
  const video = $video();
  const fill = $progressFill();
  const thumb = $progressThumb();
  const current = $timeCurrent();
  const dur = $timeDuration();
  if (!video || !fill) return;
  const d = video.duration;
  const t = video.currentTime || 0;
  if (Number.isFinite(d) && d > 0) {
    const pct = (t / d) * 100;
    fill.style.width = `${pct}%`;
    if (thumb) thumb.style.left = `${pct}%`;
  }
  if (current) current.textContent = formatTime(t);
  if (dur && Number.isFinite(d)) dur.textContent = formatTime(d);
}

function updateBuffer() {
  const video = $video();
  const buf = $progressBuffer();
  if (!video || !buf || !video.buffered.length) return;
  const d = video.duration;
  if (!Number.isFinite(d) || d <= 0) return;
  const end = video.buffered.end(video.buffered.length - 1);
  buf.style.width = `${(end / d) * 100}%`;
}

function updateVolume() {
  const video = $video();
  const fill = $volumeFill();
  const slider = $volumeSlider();
  if (!video || !fill) return;
  const vol = video.muted ? 0 : video.volume;
  fill.style.width = `${vol * 100}%`;
  if (slider) {
    const thumb = slider.querySelector(".player-volume-thumb");
    if (thumb) thumb.style.left = `${vol * 100}%`;
  }
}

function updateVolumeIcon() {
  const video = $video();
  const icons = {
    high: document.getElementById("icon-volume-high"),
    mid: document.getElementById("icon-volume-mid"),
    low: document.getElementById("icon-volume-low"),
    mute: document.getElementById("icon-volume-mute"),
  };
  if (!video) return;
  Object.values(icons).forEach((i) => { if (i) i.hidden = true; });
  if (video.muted || video.volume === 0) {
    if (icons.mute) icons.mute.hidden = false;
  } else if (video.volume >= 0.5) {
    if (icons.high) icons.high.hidden = false;
  } else if (video.volume > 0) {
    if (icons.mid) icons.mid.hidden = false;
  } else {
    if (icons.low) icons.low.hidden = false;
  }
}

function toggleMute() {
  const video = $video();
  if (!video) return;
  video.muted = !video.muted;
}

function setVolumeFromEvent(e) {
  const slider = $volumeSlider();
  const video = $video();
  if (!slider || !video) return;
  const rect = slider.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  video.volume = x;
  video.muted = false;
}

function toggleFullscreen() {
  const modal = $modal();
  if (!modal) return;
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  } else {
    modal.requestFullscreen().catch(() => {});
  }
}

function togglePip() {
  const video = $video();
  if (!video) return;
  if (document.pictureInPictureElement) {
    document.exitPictureInPicture().catch(() => {});
  } else if (document.pictureInPictureEnabled) {
    video.requestPictureInPicture().catch(() => {});
  }
}

function updateFullscreenIcon() {
  const enter = $iconFsEnter();
  const exit = $iconFsExit();
  if (!enter || !exit) return;
  const isFs = !!document.fullscreenElement;
  enter.hidden = isFs;
  exit.hidden = !isFs;
}

function handleProgressClick(e) {
  const wrap = $progress();
  const video = $video();
  if (!wrap || !video) return;
  const rect = wrap.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const d = video.duration;
  if (Number.isFinite(d) && d > 0) {
    video.currentTime = x * d;
  }
}

function handleProgressHover(e) {
  const wrap = $progress();
  const hover = $progressHover();
  const video = $video();
  if (!wrap || !hover || !video) return;
  const rect = wrap.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const d = video.duration;
  hover.style.left = `${x * 100}%`;
  if (Number.isFinite(d) && d > 0) {
    hover.textContent = formatTime(x * d);
  }
}

export function initPlayer({ onClose } = {}) {
  p.onCloseCb = onClose;
  ensureSkipButtonStructure();
  document.querySelector("#player-close")?.addEventListener("click", closePlayer);

  const skipBtn = $skipBtn();
  skipBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    skipIntro().catch(() => {});
  });

  let markHoldTimer = null;
  skipBtn?.addEventListener("pointerdown", () => {
    clearTimeout(markHoldTimer);
    markHoldTimer = setTimeout(() => {
      p.markIntroMode = true;
      setSkipIntroLabel("mark");
      updateSkipIntroButton();
    }, 650);
  });
  const clearMarkHold = () => { clearTimeout(markHoldTimer); markHoldTimer = null; };
  skipBtn?.addEventListener("pointerup", clearMarkHold);
  skipBtn?.addEventListener("pointerleave", clearMarkHold);
  skipBtn?.addEventListener("pointercancel", clearMarkHold);

  const markBtn = $markBtn();
  markBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (p.markIntroMode) {
      skipIntro().catch(() => {});
    } else {
      p.markIntroMode = true;
      setSkipIntroLabel("mark");
      setMarkBtnActive(true);
      updateSkipIntroButton();
    }
  });

  const shell = document.querySelector(".player-shell");
  if (shell) {
    shell.addEventListener("mousemove", scheduleIdleHide);
    shell.addEventListener("touchstart", () => {
      const ov = $overlay();
      if (!ov || ov.classList.contains("is-idle")) {
        showControls(true);
        scheduleIdleHide();
      }
    });
    shell.addEventListener("click", (e) => {
      const skip = $skipBtn();
      const centered = $centeredBtn();
      const progress = $progress();
      const isControl = e.target?.closest(".player-overlay, .player-btn, .btn-skip-intro, .player-hint, .player-speed-btn, .icon-btn, .video-centered-btn, .btn, .player-ended, .player-fallback, .player-loading, #btn-download");
      if (!isControl && !e.target?.closest("#video")) {
        togglePlay();
      }
    });
  }

  const centeredBtn = $centeredBtn();
  centeredBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    togglePlay();
  });

  const btnPlay = $btnPlay();
  btnPlay?.addEventListener("click", (e) => {
    e.stopPropagation();
    togglePlay();
  });

  const progressWrap = $progress();
  progressWrap?.addEventListener("click", (e) => {
    e.stopPropagation();
    handleProgressClick(e);
  });
  progressWrap?.addEventListener("mousemove", handleProgressHover);

  const muteBtn = $btnMute();
  muteBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleMute();
  });

  const volSlider = $volumeSlider();
  volSlider?.addEventListener("click", (e) => {
    e.stopPropagation();
    setVolumeFromEvent(e);
  });

  const volBtn = $btnMute();
  volBtn?.addEventListener("mouseenter", () => {
    const s = $volumeSlider();
    if (s) s.classList.add("is-open");
  });

  const volWrap = document.querySelector(".player-volume-wrap");
  volWrap?.addEventListener("mouseleave", () => {
    const s = $volumeSlider();
    if (s) s.classList.remove("is-open");
  });

  const pipBtn = $btnPip();
  pipBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    togglePip();
  });

  const fsBtn = $btnFullscreen();
  fsBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleFullscreen();
  });

  const dlBtn = $btnDownload();
  dlBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    const url = p.activeOpts?.streamUrl || p.activeOpts?.pageUrl || p.activeOpts?.externalUrl;
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = p.activeOpts?.title || "video";
    a.target = "_blank";
    a.rel = "noopener";
    a.click();
  });

  const video = $video();
  video?.addEventListener("play", () => {
    updatePlayButton();
    scheduleIdleHide();
  });
  video?.addEventListener("pause", () => {
    updatePlayButton();
    showControls(true);
    clearTimeout(p.controlsIdleTimer);
  });
  video?.addEventListener("timeupdate", () => {
    updateProgress();
    updateSkipIntroButton();
  });
  video?.addEventListener("progress", updateBuffer);
  video?.addEventListener("volumechange", () => {
    updateVolume();
    updateVolumeIcon();
    localStorage.setItem("anishelf.volume", String(video.volume));
  });
  video?.addEventListener("loadedmetadata", () => {
    updateProgress();
    updateBuffer();
    updateVolume();
    updateVolumeIcon();
    scheduleIntroResolve();
    updateSkipIntroButton();
  });
  video?.addEventListener("ended", () => {
    reportProgress(true);
    setSkipIntroVisible(false);
    showEnded();
    updatePlayButton();
    showControls(true);
    clearTimeout(p.controlsIdleTimer);
  });
  video?.addEventListener("waiting", showBuffering);
  video?.addEventListener("canplay", hideBuffering);
  video?.addEventListener("playing", () => {
    hideBuffering();
    updatePlayButton();
  });
  video?.addEventListener("seeked", () => {
    updateSkipIntroButton();
    updateProgress();
  });

  const savedVol = localStorage.getItem("anishelf.volume");
  if (video && savedVol != null) video.volume = Math.min(1, Math.max(0, Number(savedVol)));

  const SPEEDS = [1, 1.5, 2, 0.5];
  const speedBtn = document.querySelector("#player-speed");
  let speedIdx = 0;
  speedBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    speedIdx = (speedIdx + 1) % SPEEDS.length;
    const rate = SPEEDS[speedIdx];
    if (video) video.playbackRate = rate;
    speedBtn.textContent = rate + "×";
  });

  document.querySelector("#player-retry")?.addEventListener("click", () => {
    const opts = p.activeOpts;
    if (!opts) return;
    document.querySelector("#player-fallback").hidden = true;
    p.retrying = false;
    showLoading(true);
    attachStream(opts).catch(() => {});
  });
  document.querySelector("#player-ended-close")?.addEventListener("click", closePlayer);
  document.querySelector("#player-next")?.addEventListener("click", () => {
    closePlayer();
    const link = p.activeOpts?.episodeLink || "";
    const source = p.activeOpts?.sourceName || "";
    if (link) {
      import("./router.js").then(({ navigate }) => navigate(`anime?link=${encodeURIComponent(link)}&source=${encodeURIComponent(source)}`));
    }
  });

  document.addEventListener("fullscreenchange", updateFullscreenIcon);

  document.addEventListener("keydown", (e) => {
    if ($modal()?.hidden) return;
    if (e.key === "Escape") { closePlayer(); return; }
    if (e.key === "f" || e.key === "F") {
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        toggleFullscreen();
      }
      return;
    }
    if (e.key === "m" || e.key === "M") {
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        toggleMute();
      }
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (video) video.currentTime = Math.max(0, video.currentTime - 10);
      return;
    }
    if (e.key === "ArrowRight") {
      e.preventDefault();
      if (video) video.currentTime = Math.min(video.duration || 0, video.currentTime + 10);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (video) video.volume = Math.min(1, video.volume + 0.1);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (video) video.volume = Math.max(0, video.volume - 0.1);
      return;
    }
    if (e.key === " " || e.key === "k" || e.key === "K") {
      if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        const tag = (e.target?.tagName || "").toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "button" || e.target?.isContentEditable) return;
        e.preventDefault();
        togglePlay();
      }
      return;
    }
    if ((e.key === "s" || e.key === "S") && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const tag = (e.target?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || e.target?.isContentEditable) return;
      if (!$skipBtn()?.hidden || p.markIntroMode) {
        e.preventDefault();
        skipIntro().catch(() => {});
      }
    }
  });

  document.addEventListener("keyup", (e) => {
    if (e.key === " " && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const tag = (e.target?.tagName || "").toLowerCase();
      if (tag === "button") return;
      e.preventDefault();
    }
  });
}

function showBuffering() {
  const el = document.querySelector("#player-buffering");
  if (el) el.hidden = false;
}

function hideBuffering() {
  const el = document.querySelector("#player-buffering");
  if (el) el.hidden = true;
}

export function showEnded() {
  const el = document.querySelector("#player-ended");
  if (el) el.hidden = false;
  showControls(true);
  clearTimeout(p.controlsIdleTimer);
  const centered = $centeredBtn();
  if (centered) centered.classList.remove("is-visible");
}

function hideEnded() {
  const el = document.querySelector("#player-ended");
  if (el) el.hidden = true;
}

export function closePlayer() {
  showControls(true);
  clearTimeout(p.controlsIdleTimer);
  const modal = $modal();
  const video = $video();
  reportProgress(false);
  stopProgressLoop();
  destroyHls();
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.load();
    setVideoReady(false);
  }
  p.currentEpisodeLink = "";
  p.activeOpts = null;
  p.retrying = false;
  p.introSkipped = false;
  p.markIntroMode = false;
  setMarkBtnActive(false);
  p.introInterval = null;
  p.introResolvePromise = null;
  p.introResolveKey = "";
  p.introResolveSettled = false;
  p.skipFetchToken += 1;
  p.skipIntroShownForInterval = false;
  clearTimeout(p.skipIntroShowTimer);
  p.skipIntroShowTimer = null;
  setSkipIntroVisible(false);
  hideEnded();
  hideBuffering();
  if (modal) modal.hidden = true;
  document.body.style.overflow = "";
  document.body.classList.remove("player-active");
  p.onCloseCb?.();
}

export async function openPlayer(opts) {
  const modal = $modal();
  const video = $video();
  const fb = document.querySelector("#player-fallback");
  if (!modal || !video) return;

  destroyHls();
  if (fb) fb.hidden = true;
  showLoading(true);
  showControls(true);
  clearTimeout(p.controlsIdleTimer);
  p.retrying = false;
  p.introSkipped = false;
  p.markIntroMode = false;
  setMarkBtnActive(false);
  p.introInterval = null;
  p.introResolvePromise = null;
  p.introResolveKey = "";
  p.introResolveSettled = false;
  p.skipFetchToken += 1;
  p.skipIntroShownForInterval = false;
  clearTimeout(p.skipIntroShowTimer);
  p.skipIntroShowTimer = null;
  setSkipIntroVisible(false);
  ensureSkipButtonStructure();
  setSkipIntroLabel("skip");

  p.activeOpts = {
    ...opts,
    fallbackCandidates: [...(opts.fallbackCandidates || [])],
  };

  document.querySelector("#player-title").textContent = opts.title || "Tocando";
  document.querySelector("#player-ep").textContent = opts.episodeLabel || "";
  p.currentEpisodeLink = opts.episodeLink || "";

  modal.hidden = false;
  document.body.style.overflow = "hidden";
  document.body.classList.add("player-active");

  video.volume = Math.min(1, Math.max(0, Number(localStorage.getItem("anishelf.volume") || 1)));
  updateVolume();
  updateVolumeIcon();
  updatePlayButton();
  updateProgress();

  const startAt = Math.max(0, Number(opts.startAt) || 0);
  const localEnd = getLocalIntroEnd(opts.title || "");
  const pastEnd = localEnd != null ? localEnd : SKIP_INTRO_DEFAULT_END;
  if (startAt >= pastEnd - SKIP_INTRO_HIDE_BEFORE) {
    p.introSkipped = true;
  }

  scheduleIntroResolve();
  await attachStream(p.activeOpts);
}
