import { api, imgUrl } from "../api.js";
import { state } from "../state.js";
import { $, $$, escapeHtml, PLACEHOLDER_POSTER } from "../utils/dom.js";
import { normalizeWatchTitles, resolveEpisodeNumber, formatEpLabel, isOnlyEpisodeLabel, cleanTitleForAniList, stripTitleVariants } from "../utils/titles.js";

function setText(sel, text) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (el) el.textContent = text ?? "";
}

function setHtml(sel, html) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (el) el.innerHTML = html ?? "";
}

function resetDetailShell() {
  setText("#detail-title", "Carregando…");
  setText("#detail-desc", "");
  setText("#detail-rating", "");
  setHtml("#detail-episodes", "");
  setHtml("#detail-meta-row", "");
  setHtml("#detail-tags", "");
  setHtml("#detail-sources", "");
  const select = $("#season-select");
  if (select) {
    select.innerHTML = "";
    select.onchange = null;
  }
  const alt = $("#detail-alt-title");
  if (alt) {
    alt.hidden = true;
    alt.textContent = "";
  }
  const next = $("#detail-next");
  if (next) {
    next.hidden = true;
    next.textContent = "";
  }
  const franchise = $("#detail-franchise");
  if (franchise) franchise.hidden = true;
  setHtml("#franchise-rail", "");
  setText("#detail-eyebrow", "Anime");
  const posterEl = $("#detail-poster");
  if (posterEl) {
    posterEl.removeAttribute("src");
    posterEl.alt = "";
    posterEl.style.display = "none";
  }
  const bg = $("#detail-bg");
  if (bg) bg.style.backgroundImage = "";
}

function renderSeasonEpisodes(season) {
  const grid = $("#detail-episodes");
  if (!grid || !season) return;
  grid.innerHTML = "";
  grid.classList.add("episodes-list");
  const frag = document.createDocumentFragment();
  const epMeta = state.detailEpisodeMeta || {};

  for (const ep of season.episodes || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ep-card";

    const num = resolveEpisodeNumber(ep.number, ep.title, ep.link);
    const labels = normalizeWatchTitles(
      state.detail?.title || "",
      ep.title,
      num
    );
    const meta = epMeta[String(labels.number)] || epMeta[String(num)] || null;

    const rawThumb = (ep.image || "").trim() || (meta?.thumbnail || "").trim();
    const thumb = rawThumb ? imgUrl(rawThumb) : "";

    const generic =
      isOnlyEpisodeLabel(ep.title) ||
      !labels.episodeTitle ||
      labels.episodeTitle.toLowerCase() === `episodio ${labels.number}` ||
      labels.episodeTitle.toLowerCase() === `episódio ${labels.number}`;
    const alTitle = (meta?.title || "").trim();
    let mainLine;
    let subLine = "";
    if (generic && alTitle) {
      mainLine = alTitle;
      subLine = `Episódio ${labels.number}`;
    } else if (generic) {
      mainLine = `Episódio ${labels.number && labels.number !== "?" ? labels.number : "?"}`;
      subLine = "";
    } else {
      mainLine = labels.episodeTitle;
      subLine = `Episódio ${labels.number}`;
    }

    const numLabel =
      labels.number && labels.number !== "?" ? String(labels.number) : "?";

    btn.innerHTML = `
      <div class="ep-thumb" data-thumb="${escapeHtml(thumb)}">
        ${
          thumb
            ? `<span class="ep-num">Ep ${escapeHtml(numLabel)}</span>`
            : `<span class="ep-placeholder-num">${escapeHtml(numLabel)}</span>`
        }
      </div>
      <div class="ep-info">
        <div class="ep-kicker">${escapeHtml(subLine || `Episódio ${numLabel}`)}</div>
        <div class="ep-title">${escapeHtml(mainLine)}</div>
        ${ep.date ? `<div class="ep-date">${escapeHtml(ep.date)}</div>` : ""}
      </div>
      <span class="ep-play-hint" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
      </span>
    `;

    const thumbEl = btn.querySelector(".ep-thumb");
    if (thumbEl && thumb) {
      const obs = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
          thumbEl.style.backgroundImage = `url('${thumb}')`;
          thumbEl.classList.add("has-img");
          obs.disconnect();
        }
      }, { rootMargin: "200px" });
      obs.observe(thumbEl);
    }
    if (!subLine && generic && !alTitle) {
      const k = btn.querySelector(".ep-kicker");
      if (k) k.hidden = true;
    } else if (subLine && mainLine === subLine) {
      const k = btn.querySelector(".ep-kicker");
      if (k) k.hidden = true;
    }

    btn.addEventListener("click", () => {
      import("../play-flow.js").then((m) => {
        m.playEpisode({
          episode_link: ep.link,
          preferred_source: state.detailPreferred,
          anime_title: labels.animeTitle,
          episode_title: alTitle || labels.episodeTitle,
          episode_number: labels.number,
          anime_image: rawThumb || state.detail?.image || "",
          season_number: season.number,
          candidates: [
            {
              name: state.detailPreferred || "",
              link: ep.link,
              color: "",
            },
          ],
        });
      });
    });
    frag.appendChild(btn);
  }
  grid.appendChild(frag);
}

export function renderDetail(detail, preferredSource) {
  if (!detail) return;

  setText("#detail-title", detail.title || "Sem título");
  const rating = String(detail.rating || "").trim();
  setText("#detail-rating", rating ? `★ ${rating}` : "");
  renderWatchLaterBtn(detail);
  const descEl = document.querySelector("#detail-desc");
  if (descEl) {
    descEl.textContent = detail.description || "Sem sinopse.";
    descEl.classList.remove("is-expanded");
  }
  const descToggle = document.querySelector("#detail-desc-toggle");
  if (descToggle) {
    const needsToggle = descEl && (detail.description || "").length > 200;
    descToggle.hidden = !needsToggle;
    descToggle.textContent = "Mostrar mais";
    if (!needsToggle) descEl?.classList.remove("is-clamped");
    descToggle.onclick = () => {
      const expanded = descEl.classList.toggle("is-expanded");
      descToggle.textContent = expanded ? "Mostrar menos" : "Mostrar mais";
    };
  }

  const poster = imgUrl(detail.image);
  const posterEl = $("#detail-poster");
  if (posterEl) {
    posterEl.alt = detail.title || "";
    posterEl.style.display = "";
    posterEl.loading = "lazy";
    requestAnimationFrame(() => {
      posterEl.onerror = () => { posterEl.src = PLACEHOLDER_POSTER; };
      posterEl.src = poster || PLACEHOLDER_POSTER;
    });
  }
  const bg = $("#detail-bg");
  if (bg) {
    if (poster) {
      const img = new Image();
      img.onload = () => { bg.style.backgroundImage = `url('${poster}')`; };
      img.onerror = () => { bg.style.backgroundImage = `url('${PLACEHOLDER_POSTER}')`; };
      img.src = poster;
    } else {
      bg.style.backgroundImage = `url('${PLACEHOLDER_POSTER}')`;
    }
  }

  const pills = $("#detail-sources");
  if (pills) {
    pills.innerHTML = preferredSource
      ? `<span class="source-pill">${escapeHtml(preferredSource)}</span>`
      : "";
  }

  const seasons = Array.isArray(detail.seasons) ? detail.seasons : [];
  const select = $("#season-select");
  if (select) {
    select.innerHTML = "";
    select.onchange = null;
  }

  if (!seasons.length) {
    setHtml(
      "#detail-episodes",
      `<div class="empty-state"><strong>Sem episódios</strong>A fonte não enviou a lista de episódios.</div>`
    );
    return;
  }

  if (select) {
    seasons.forEach((s, i) => {
      const opt = document.createElement("option");
      opt.value = String(i);
      const n = s.number ?? i + 1;
      const count = Array.isArray(s.episodes) ? s.episodes.length : 0;
      opt.textContent = count
        ? `Temporada ${n} · ${count} episódios`
        : `Temporada ${n}`;
      select.appendChild(opt);
    });
    select.onchange = () => {
      const idx = Number(select.value);
      renderSeasonEpisodes(seasons[idx]);
    };
  }
  renderSeasonEpisodes(seasons[0]);
}

function renderWatchLaterBtn(detail) {
  const container = $("#detail-sources");
  if (!container) return;
  const existing = container.parentNode?.querySelector(".detail-wl-btn");
  if (existing) existing.remove();
  const isSaved = state.watchLater.some((w) => w.anime_title === detail.title);
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn btn-ghost detail-wl-btn";
  btn.innerHTML = `
    <svg viewBox="0 0 24 24" width="16" height="16" fill="${isSaved ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
    </svg>
    <span>${isSaved ? "Nos favoritos" : "Favoritos"}</span>
  `;
  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const { api: _api } = await import("../api.js");
    const { toast } = await import("../toast.js");
    try {
      if (isSaved) {
        await _api.removeWatchLater(detail.title);
        state.watchLater = state.watchLater.filter((w) => w.anime_title !== detail.title);
        btn.innerHTML = `
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
          <span>Favoritos</span>
        `;
        toast("Removido dos favoritos");
      } else {
        await _api.addWatchLater({
          anime_title: detail.title,
          anime_image: detail.image || "",
          source_name: (detail.sources?.[0]?.name) || "",
          source_link: (detail.sources?.[0]?.link) || "",
          source_color: (detail.sources?.[0]?.color) || "",
        });
        state.watchLater.push({
          anime_title: detail.title,
          anime_image: detail.image || "",
          source_name: (detail.sources?.[0]?.name) || "",
          source_link: (detail.sources?.[0]?.link) || "",
          source_color: (detail.sources?.[0]?.color) || "",
        });
        btn.innerHTML = `
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
          </svg>
          <span>Nos favoritos</span>
        `;
        toast("Adicionado aos favoritos");
      }
    } catch (e) {
      toast(e.message || "Erro ao salvar", true);
    }
  });
  container.after(btn);
}

function applyAniListMeta(meta) {
  if (!meta || !state.detail) return;

  const eyebrow = $("#detail-eyebrow");
  if (eyebrow) {
    const bits = ["Catálogo"];
    if (meta.season_line) bits.push(meta.season_line);
    eyebrow.textContent = bits.join(" · ");
  }

  const bg = $("#detail-bg");
  if (bg && meta.banner) {
    const bannerUrl = imgUrl(meta.banner);
    const img = new Image();
    img.onload = () => { bg.style.backgroundImage = `url('${bannerUrl}')`; };
    img.onerror = () => { bg.style.backgroundImage = ""; };
    img.src = bannerUrl;
  }

  const posterEl = $("#detail-poster");
  const sourceImg = (state.detail.image || "").trim();
  if (posterEl && meta.image && !sourceImg) {
    setTimeout(() => {
      if (!state.detailMeta || state.detailMeta !== meta) return;
      posterEl.onerror = () => { posterEl.src = PLACEHOLDER_POSTER; };
      posterEl.src = imgUrl(meta.image);
      posterEl.alt = state.detail.title || meta.title || "";
    }, 600);
  }

  const alt = $("#detail-alt-title");
  if (alt) {
    const base = state.detail.title || "";
    const alts = [meta.title_english, meta.title_romaji, meta.title_native]
      .filter(Boolean)
      .filter((t) => t.toLowerCase() !== base.toLowerCase());
    const unique = [...new Set(alts)];
    if (unique.length) {
      alt.hidden = false;
      alt.textContent = unique.slice(0, 2).join(" · ");
    }
  }

  const row = $("#detail-meta-row");
  if (row) {
    const chips = [];
    if (meta.score != null) {
      chips.push(
        `<span class="meta-chip score">★ ${(Number(meta.score) / 10).toFixed(1)}</span>`
      );
    }
    if (meta.format_label) {
      chips.push(`<span class="meta-chip">${escapeHtml(meta.format_label)}</span>`);
    }
    if (meta.season_line) {
      chips.push(`<span class="meta-chip">${escapeHtml(meta.season_line)}</span>`);
    }
    if (meta.status_label) {
      const st = String(meta.status || "").toLowerCase();
      const cls =
        st === "releasing"
          ? "status-releasing"
          : st === "finished"
            ? "status-finished"
            : "";
      chips.push(
        `<span class="meta-chip ${cls}">${escapeHtml(meta.status_label)}</span>`
      );
    }
    if (meta.episodes) {
      chips.push(`<span class="meta-chip">${meta.episodes} eps</span>`);
    }
    if (meta.duration) {
      chips.push(`<span class="meta-chip">${meta.duration} min</span>`);
    }
    if (meta.studios?.length) {
      chips.push(
        `<span class="meta-chip">${escapeHtml(meta.studios.slice(0, 2).join(" · "))}</span>`
      );
    }
    row.innerHTML = chips.join("");
  }

  const desc = $("#detail-desc");
  if (desc && meta.description) {
    const current = (desc.textContent || "").trim();
    if (!current || current === "Sem sinopse.") {
      desc.textContent = meta.description;
    }
  }

  const ratingEl = $("#detail-rating");
  if (ratingEl && meta.score != null) {
    const cur = (ratingEl.textContent || "").trim();
    if (!cur) {
      ratingEl.textContent = `★ ${(Number(meta.score) / 10).toFixed(1)}`;
    }
  }

  const tags = $("#detail-tags");
  if (tags && meta.genres_label?.length) {
    tags.innerHTML = meta.genres_label
      .slice(0, 8)
      .map((g) => `<span class="detail-tag">${escapeHtml(g)}</span>`)
      .join("");
  }

  const next = $("#detail-next");
  if (next && meta.next_episode && meta.next_airing_at) {
    const when = formatAiringAt(meta.next_airing_at);
    next.hidden = false;
    next.textContent = `Próximo episódio: ${meta.next_episode}${when ? ` · ${when}` : ""}`;
  } else if (next) {
    next.hidden = true;
    next.textContent = "";
  }

  renderFranchise(meta.franchise || meta.relations || []);
}

function formatAiringAt(unix) {
  if (!unix) return "";
  try {
    const d = new Date(Number(unix) * 1000);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function renderFranchise(items) {
  const section = $("#detail-franchise");
  const rail = $("#franchise-rail");
  if (!section || !rail) return;
  const list = (items || []).filter(
    (x) => x && x.title && (x.is_current || x.relation_type === "CURRENT" || x.available)
  );
  const related = list.filter(
    (x) => !(x.is_current || x.relation_type === "CURRENT")
  );
  if (!related.length) {
    section.hidden = true;
    rail.innerHTML = "";
    return;
  }
  section.hidden = false;
  rail.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const item of list.slice(0, 16)) {
    const card = document.createElement("article");
    const isCurrent = !!item.is_current || item.relation_type === "CURRENT";
    const hasSources = (item.sources || []).some((s) => s?.link);
    card.className =
      "franchise-card" +
      (isCurrent ? " is-current" : "") +
      (!isCurrent && hasSources ? " has-link" : "");
    const poster = imgUrl(item.image);
    const sourceNames = (item.sources || []).map((s) => s.name).filter(Boolean);
    const metaLine = [
      item.relation_label,
      sourceNames.slice(0, 2).join(" · "),
      item.season_label && item.year
        ? `${item.season_label} ${item.year}`
        : item.year || item.season_label || "",
      item.format_label,
    ]
      .filter(Boolean)
      .join(" · ");
    card.innerHTML = `
      <div class="franchise-poster" style="${poster ? `background-image:url('${poster}')` : ""}">
        <span class="franchise-rel">${escapeHtml(item.relation_label || "Relacionado")}</span>
      </div>
      <div class="franchise-body">
        <div class="franchise-title">${escapeHtml(item.source_title || item.title)}</div>
        <div class="franchise-meta">${escapeHtml(metaLine)}</div>
      </div>
    `;
    if (!isCurrent && hasSources) {
      card.addEventListener("click", () => {
        const src = item.sources[0];
        import("../router.js").then(({ navigate }) =>
          navigate(
            `anime?link=${encodeURIComponent(src.link)}&source=${encodeURIComponent(
              src.name || ""
            )}&al=${encodeURIComponent(item.id || "")}&title=${encodeURIComponent(
              item.source_title || item.title
            )}`
          )
        );
      });
    }
    frag.appendChild(card);
  }
  rail.appendChild(frag);
}

export async function loadDetail(link, preferredSource, { anilistId = null, titleHint = "" } = {}) {
  const { navigate } = await import("../router.js");
  const { toast } = await import("../toast.js");
  const _waitSourcesReady = (await import("../search.js")).waitSourcesReady;

  if (!link) {
    toast("Link inválido", true);
    navigate("home");
    return;
  }
  const seq = ++state.detailSeq;
  state.detailLink = link;
  resetDetailShell();

  try {
    await _waitSourcesReady();
    if (seq !== state.detailSeq) return;
    const detail = await api.anime(link);
    if (seq !== state.detailSeq) return;
    if (!detail?.title) {
      throw new Error("Anime não encontrado");
    }
    state.detail = detail;
    state.detailPreferred = preferredSource || "";
    state.detailMeta = null;
    state.detailEpisodeMeta = {};
    renderDetail(detail, preferredSource);

    const title = titleHint || detail.title || "";
    enrichDetailWithAniList(title, anilistId, seq).catch(() => {});
  } catch (e) {
    if (seq !== state.detailSeq) return;
    toast(e.message || "Não foi possível abrir o anime", true);
    navigate("home");
  }
}

async function enrichDetailWithAniList(title, anilistId, seq) {
  const cleaned = cleanTitleForAniList(title);
  if (!cleaned && (anilistId == null || anilistId === "")) return;
  try {
    const meta = await api.meta(cleaned || title || "", anilistId);
    if (seq != null && seq !== state.detailSeq) return;
    if (!meta || !state.detail) return;
    if (state.detailLink && state.detail.link && state.detailLink !== state.detail.link) {
      /* keep — link da fonte pode diferir do state */
    }
    state.detailMeta = meta;
    const map = {};
    for (const ep of meta.episode_thumbs || []) {
      const n = String(ep.number ?? "").trim();
      if (!n) continue;
      map[n] = {
        title: ep.title || "",
        thumbnail: ep.thumbnail || "",
      };
    }
    state.detailEpisodeMeta = map;
    applyAniListMeta(meta);
    const select = $("#season-select");
    const seasons = state.detail?.seasons || [];
    if (seasons.length) {
      const idx = select ? Number(select.value) || 0 : 0;
      renderSeasonEpisodes(seasons[idx] || seasons[0]);
    }
  } catch {
    /* meta opcional — ficha da fonte já está renderizada */
  }
}
