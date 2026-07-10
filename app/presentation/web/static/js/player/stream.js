import { api } from "../api.js";
import {
  p, $video, destroyHls,
  showLoading, showFallback, setSkipIntroVisible, setSkipIntroLabel, setVideoReady,
  ensureSkipButtonStructure,
} from "./state.js";
import { scheduleIntroResolve, skipIntro } from "./intro.js";

async function tryNextCandidate(reason) {
  if (p.retrying || !p.activeOpts) {
    showFallback(p.activeOpts?.externalUrl || p.activeOpts?.pageUrl);
    return;
  }
  const rest = p.activeOpts.fallbackCandidates || [];
  if (!rest.length) {
    showFallback(p.activeOpts.externalUrl || p.activeOpts.pageUrl);
    return;
  }

  p.retrying = true;
  const next = rest[0];
  const remaining = rest.slice(1);
  showLoading(true, `Fonte falhou · tentando ${next.name || "outra"}…`);

  const meta = p.activeOpts.playMeta || {};
  try {
    const res = await api.play({
      preferred_source: next.name,
      episode_link: next.link,
      candidates: [next, ...remaining],
      anime_title: meta.anime_title || p.activeOpts.title || "",
      episode_title: meta.episode_title || "",
      episode_number: meta.episode_number || "0",
      anime_image: meta.anime_image || "",
      season_number: meta.season_number || 1,
      source_color: next.color || "",
    });

    p.activeOpts = {
      ...p.activeOpts,
      playable: res.playable,
      streamUrl: res.stream_url,
      isHls: res.is_hls,
      startAt: res.start_at ?? p.activeOpts.startAt,
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
    document.querySelector("#player-ep").textContent = p.activeOpts.episodeLabel || "";
    p.currentEpisodeLink = p.activeOpts.episodeLink || "";
    p.retrying = false;

    if (!res.playable || !res.stream_url) {
      await tryNextCandidate(reason);
      return;
    }
    await attachStream(p.activeOpts);
  } catch {
    p.retrying = false;
    p.activeOpts.fallbackCandidates = remaining;
    await tryNextCandidate(reason);
  }
}

function onStreamFatal() {
  tryNextCandidate("playback error");
}

export async function attachStream(opts) {
  const video = $video();
  if (!video) return;

  destroyHls();
  const fb = document.querySelector("#player-fallback");
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
    setVideoReady(true);
    if (startAt > 2) {
      const seek = () => {
        try { video.currentTime = startAt; } catch { /* ignore */ }
        video.removeEventListener("loadedmetadata", seek);
      };
      if (video.readyState >= 1) seek();
      else video.addEventListener("loadedmetadata", seek);
    }
    video.play().catch(() => {});
    import("./progress.js").then((m) => m.startProgressLoop());
    scheduleIntroResolve();
  };

  try {
    if (opts.isHls || url.includes(".m3u8")) {
      if (window.Hls && window.Hls.isSupported()) {
        p.hls = new window.Hls({
          enableWorker: true,
          xhrSetup(xhr) { xhr.withCredentials = false; },
        });
        p.hls.loadSource(url);
        p.hls.attachMedia(video);
        p.hls.on(window.Hls.Events.MANIFEST_PARSED, onReady);
        p.hls.on(window.Hls.Events.ERROR, (_e, data) => {
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
