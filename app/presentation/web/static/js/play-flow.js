import { api } from "./api.js";
import { state } from "./state.js";
import { $, escapeHtml } from "./utils/dom.js";
import {
  normalizeWatchTitles,
  resolveEpisodeNumber,
  stripTitleVariants,
} from "./utils/titles.js";
import {
  hasAudioChoice,
  detectAudioVariant,
  resolveSourceVariant,
  audioBucket,
  sourcesForAudioBucket,
  audioOptionMeta,
} from "./utils/audio.js";
import { toast, toastLoading, dismissToast } from "./toast.js";

let _openPlayer = null;
async function getOpenPlayer() {
  if (!_openPlayer) {
    const mod = await import("./player.js");
    _openPlayer = mod.openPlayer;
  }
  return _openPlayer;
}

export function sourcesToCandidates(sources) {
  return (sources || [])
    .filter((s) => s?.link)
    .map((s) => ({
      name: s.name || "",
      link: s.link,
      color: s.color || "",
      variant: s.variant || detectAudioVariant(s.title || "", s.link || ""),
      title: s.title || "",
    }));
}

function openChoiceModal({ heading, subtitle, options, onPick }) {
  const modal = $("#source-modal");
  const list = $("#source-options");
  const headingEl = $("#source-modal-heading");
  if (headingEl) headingEl.textContent = heading || "Escolha";
  $("#source-modal-title").textContent = subtitle || "";
  list.innerHTML = "";
  for (const opt of options || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "source-opt source-opt-rich";
    const accent = opt.accent || opt.color || "#888";
    btn.innerHTML = `
      <span class="source-dot" style="--dot:${accent};background:${accent}"></span>
      <span class="source-opt-text">
        <span class="source-opt-label">${escapeHtml(opt.label)}</span>
        ${opt.hint ? `<span class="source-opt-hint">${escapeHtml(opt.hint)}</span>` : ""}
      </span>
    `;
    btn.addEventListener("click", () => {
      modal.hidden = true;
      onPick(opt.data);
    });
    list.appendChild(btn);
  }
  modal.hidden = false;
}

export function openAudioChoiceModal(workTitle, sources, onPick) {
  const dub = sourcesForAudioBucket(sources, "dublado");
  const sub = sourcesForAudioBucket(sources, "legendado");
  const options = [];
  if (sub.length) options.push({ ...audioOptionMeta("legendado", sub), sources: sub });
  if (dub.length) options.push({ ...audioOptionMeta("dublado", dub), sources: dub });

  openChoiceModal({
    heading: "Como prefere assistir?",
    subtitle: stripTitleVariants(workTitle) || workTitle || "",
    options: options.map((o) => ({
      label: o.label,
      hint: o.hint,
      accent: o.accent,
      data: o.sources,
    })),
    onPick,
  });
}

export function openSourceModal(title, sources, onPick) {
  openChoiceModal({
    heading: "Qual fonte?",
    subtitle: title || "",
    options: (sources || []).map((s) => ({
      label: s.name || "Fonte",
      hint: s.variant
        ? audioOptionMeta(audioBucket(resolveSourceVariant(s)), [s]).label
        : "",
      accent: s.color || "#888",
      color: s.color,
      data: s,
    })),
    onPick,
  });
}

export function playEpisodeFromSources(item, sources) {
  const list = (sources || []).filter((s) => s?.link);
  if (!list.length) {
    toast("Nenhuma fonte disponível", true);
    return;
  }
  const links = list.map((s) => s.link).filter(Boolean);
  const num = resolveEpisodeNumber(item.number, item.title, ...links);
  const labels = normalizeWatchTitles(item.title, item.title, num);
  playEpisode({
    preferred_source: list[0].name,
    anime_title: labels.animeTitle,
    episode_title: labels.episodeTitle,
    episode_number: labels.number,
    anime_image: item.image,
    source_color: list[0].color,
    candidates: sourcesToCandidates(list),
  });
}

export function onEpisodeClick(item) {
  const sources = (item.sources || []).filter((s) => s?.link);
  if (!sources.length) {
    toast("Nenhuma fonte disponível", true);
    return;
  }
  if (hasAudioChoice(sources)) {
    openAudioChoiceModal(item.title, sources, (picked) => {
      playEpisodeFromSources(item, picked);
    });
    return;
  }
  playEpisodeFromSources(item, sources);
}

export function onAnimeClick(item) {
  const sources = (item.sources || []).filter((s) => s?.link);
  if (!sources.length) {
    toast("Este item não tem link de detalhes", true);
    return;
  }
  if (hasAudioChoice(sources)) {
    openAudioChoiceModal(item.title, sources, (picked) => {
      openAnimeFromSource(item, picked[0]);
    });
    return;
  }
  openAnimeFromSource(item, sources[0]);
}

export async function openAnimeFromSource(item, src) {
  if (!src?.link) {
    toast("Este item não tem link de detalhes", true);
    return;
  }
  const q = [
    `link=${encodeURIComponent(src.link)}`,
    `source=${encodeURIComponent(src.name || "")}`,
  ];
  if (item.anilist_id) q.push(`al=${encodeURIComponent(item.anilist_id)}`);
  const title = stripTitleVariants(item.title) || item.title;
  if (title) q.push(`title=${encodeURIComponent(title)}`);
  const { navigate } = await import("./router.js");
  navigate(`anime?${q.join("&")}`);
}

export async function navigateToAnimeSource(src, { title = "", anilistId = "" } = {}) {
  if (!src?.link) {
    toast("Link inválido", true);
    return;
  }
  const q = [
    `link=${encodeURIComponent(src.link)}`,
    `source=${encodeURIComponent(src.name || "")}`,
  ];
  if (anilistId) q.push(`al=${encodeURIComponent(anilistId)}`);
  if (title) q.push(`title=${encodeURIComponent(stripTitleVariants(title) || title)}`);
  const { navigate } = await import("./router.js");
  navigate(`anime?${q.join("&")}`);
}

export async function pickAnimeSourceThenOpen(title, sources, { anilistId = "" } = {}) {
  const linked = (sources || []).filter((s) => s?.link);
  if (!linked.length) {
    toast("Não achei nas fontes ativas", true);
    return;
  }
  if (hasAudioChoice(linked)) {
    openAudioChoiceModal(title, linked, (picked) => {
      navigateToAnimeSource(picked[0], { title, anilistId });
    });
    return;
  }
  navigateToAnimeSource(linked[0], { title, anilistId });
}

export async function playEpisode(payload) {
  const candidates = payload.candidates?.length
    ? payload.candidates
    : payload.episode_link
      ? [
          {
            name: payload.preferred_source || "",
            link: payload.episode_link,
            color: payload.source_color || "",
          },
        ]
      : [];

  if (!candidates.length) {
    toast("Nenhuma fonte para reproduzir", true);
    return;
  }

  if (candidates.length > 1) {
    toastLoading(`Tentando ${candidates.length} fontes…`);
  } else {
    toastLoading("Procurando stream…");
  }

  try {
    const labels = normalizeWatchTitles(
      payload.anime_title || "",
      payload.episode_title || "",
      payload.episode_number || ""
    );
    const body = {
      preferred_source: payload.preferred_source || candidates[0].name,
      anime_title: labels.animeTitle,
      episode_title: labels.episodeTitle,
      episode_number: labels.number || "0",
      anime_image: payload.anime_image || "",
      season_number: payload.season_number || 1,
      source_color: payload.source_color || candidates[0].color || "",
      episode_link: payload.episode_link || candidates[0].link,
      candidates,
    };
    const res = await api.play(body);
    const usedSource = res.source_name || body.preferred_source || "";

    if (res.switched) {
      const failed = (res.tried || [])
        .filter((t) => !t.ok)
        .map((t) => t.name)
        .filter(Boolean);
      toast(
        failed.length
          ? `${failed.join(", ")} falhou · usando ${usedSource}`
          : `Tocando em ${usedSource}`
      );
    }

    let malId = payload.mal_id || state.detailMeta?.mal_id || null;
    const anilistId = payload.anilist_id || state.detailMeta?.id || null;
    if (!malId && labels.animeTitle) {
      try {
        const meta = await api.meta(labels.animeTitle);
        if (meta?.mal_id) malId = meta.mal_id;
      } catch {
        /* opcional */
      }
    }
    const epNum = Number(labels.number);
    dismissToast();
    const openPlayer = await getOpenPlayer();
    await openPlayer({
      playable: res.playable,
      streamUrl: res.stream_url,
      isHls: res.is_hls,
      startAt: res.start_at,
      pageUrl: res.page_url,
      externalUrl: res.external_url,
      title: labels.animeTitle,
      episodeLabel: [labels.episodeLine, usedSource].filter(Boolean).join(" · "),
      episodeLink: res.episode_link || body.episode_link,
      episodeNumber: Number.isFinite(epNum) && epNum > 0 ? epNum : labels.number,
      malId: malId ? Number(malId) : null,
      anilistId: anilistId ? Number(anilistId) : null,
      fallbackCandidates: candidates.filter(
        (c) => c.link !== (res.episode_link || body.episode_link)
      ),
      playMeta: {
        anime_title: body.anime_title,
        episode_title: body.episode_title,
        episode_number: body.episode_number,
        anime_image: body.anime_image,
        season_number: body.season_number,
        mal_id: malId ? Number(malId) : null,
      },
    });
    if (!res.playable) {
      toast("Vídeo direto indisponível — abra no site");
    }
    import("./views/home.js").then((m) => m.renderContinueRow());
  } catch (e) {
    dismissToast();
    toast(e.message || "Não foi possível reproduzir", true);
  }
}

export async function playFromHistory(item) {
  const labels = normalizeWatchTitles(
    item.anime_title,
    item.episode_title,
    item.episode_number
  );
  await playEpisode({
    episode_link: item.episode_link,
    preferred_source: item.source_name,
    anime_title: labels.animeTitle,
    episode_title: labels.episodeTitle,
    episode_number: labels.number,
    anime_image: item.anime_image,
    season_number: item.season_number,
    source_color: item.source_color,
    candidates: [
      {
        name: item.source_name || "",
        link: item.episode_link,
        color: item.source_color || "",
      },
    ],
  });
}
