/** Cliente HTTP da API web. */

const BASE = "";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j);
    } catch {
      /* ignore */
    }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => request("/api/health"),
  episodes: () => request("/api/episodes"),
  search: (q) => request(`/api/search?q=${encodeURIComponent(q)}`),
  genres: () => request("/api/genres"),
  genreCatalog: (genre, page = 1, perPage = 20) =>
    request(
      `/api/genres/catalog?genre=${encodeURIComponent(genre)}&page=${page}&per_page=${perPage}`
    ),
  genreResolve: (items) =>
    request("/api/genres/resolve", {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  browseGenre: (genre, page = 1, perPage = 12) =>
    request(
      `/api/genres/browse?genre=${encodeURIComponent(genre)}&page=${page}&per_page=${perPage}`
    ),
  meta: (title = "", id = null) => {
    const q = new URLSearchParams();
    if (title) q.set("title", title);
    if (id != null && id !== "") q.set("id", String(id));
    return request(`/api/meta?${q.toString()}`);
  },
  /** Timestamps de OP/ED (AniSkip) via proxy do backend. */
  skipTimes: (malId, episode, episodeLength = 0, types = "op") => {
    const q = new URLSearchParams();
    q.set("mal_id", String(malId));
    q.set("episode", String(episode));
    q.set("episode_length", String(episodeLength ?? 0));
    if (types) q.set("types", types);
    return request(`/api/skip-times?${q.toString()}`);
  },
  calendar: (days = 7, checkSources = false) =>
    request(
      `/api/calendar?days=${encodeURIComponent(days)}&check_sources=${
        checkSources ? "true" : "false"
      }`
    ),
  anime: (link) => request(`/api/anime?link=${encodeURIComponent(link)}`),
  play: (body) =>
    request("/api/play", { method: "POST", body: JSON.stringify(body) }),
  history: (dedupe = true, mode = "anime") =>
    request(
      `/api/history?dedupe=${dedupe ? "true" : "false"}&mode=${encodeURIComponent(mode)}`
    ),
  addHistory: (body) =>
    request("/api/history", { method: "POST", body: JSON.stringify(body) }),
  progress: (body) =>
    request("/api/history/progress", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  clearHistory: () => request("/api/history", { method: "DELETE" }),
  watchLater: () => request("/api/watch-later"),
  addWatchLater: (body) =>
    request("/api/watch-later", { method: "POST", body: JSON.stringify(body) }),
  removeWatchLater: (title) =>
    request(`/api/watch-later/${encodeURIComponent(title)}`, { method: "DELETE" }),
  clearWatchLater: () => request("/api/watch-later", { method: "DELETE" }),
  sources: () => request("/api/sources"),
  setSource: (id, enabled) =>
    request(`/api/sources/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  refreshSourcesHealth: () =>
    request("/api/sources/health", { method: "POST" }),
  refreshSourceHealth: (id) =>
    request(`/api/sources/${encodeURIComponent(id)}/health`, {
      method: "POST",
    }),
  openingMark: (animeTitle, seasonNumber = 1) => {
    const q = new URLSearchParams();
    q.set("anime_title", animeTitle);
    q.set("season_number", String(seasonNumber));
    return request(`/api/opening-marks?${q.toString()}`);
  },
  saveOpeningMark: (body) =>
    request("/api/opening-marks", { method: "POST", body: JSON.stringify(body) }),
};

export function imgUrl(url) {
  if (!url) return "";
  if (url.startsWith("data:") || url.startsWith("/")) return url;
  if (url.startsWith("//")) return `/api/image?url=${encodeURIComponent("https:" + url)}`;
  return `/api/image?url=${encodeURIComponent(url)}`;
}
