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
};

export function imgUrl(url) {
  if (!url) return "";
  if (url.startsWith("data:") || url.startsWith("/")) return url;
  return `/api/image?url=${encodeURIComponent(url)}`;
}
