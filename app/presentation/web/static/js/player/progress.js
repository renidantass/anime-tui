import { api } from "../api.js";
import { p } from "./state.js";

export function startProgressLoop() {
  stopProgressLoop();
  p.progressTimer = setInterval(() => reportProgress(false), 8000);
}

export function stopProgressLoop() {
  if (p.progressTimer) {
    clearInterval(p.progressTimer);
    p.progressTimer = null;
  }
}

export async function reportProgress(finished) {
  if (!p.currentEpisodeLink) return;
  const video = document.querySelector("#video");
  if (!video || !video.duration || !Number.isFinite(video.duration)) return;
  const pos = finished ? video.duration : video.currentTime;
  try {
    await api.progress({
      episode_link: p.currentEpisodeLink,
      progress_seconds: pos,
      duration_seconds: video.duration,
    });
  } catch { /* silencioso */ }
}
