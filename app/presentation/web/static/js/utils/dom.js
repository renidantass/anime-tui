export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export const PLACEHOLDER_POSTER =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="300" viewBox="0 0 200 300">' +
    '<rect width="100%" height="100%" fill="#090a12"/>' +
    '<line x1="0" y1="0" x2="200" y2="300" stroke="#00f0ff" stroke-width="0.5" opacity="0.15"/>' +
    '<line x1="200" y1="0" x2="0" y2="300" stroke="#00f0ff" stroke-width="0.5" opacity="0.15"/>' +
    '<rect x="20" y="20" width="160" height="260" fill="none" stroke="#00f0ff" stroke-width="1" stroke-dasharray="4,4" opacity="0.25"/>' +
    '<text x="50%" y="48%" dominant-baseline="middle" text-anchor="middle" font-family="monospace" font-size="10" fill="#ff0055" font-weight="bold" letter-spacing="2">[ NO SIGNAL ]</text>' +
    '<text x="50%" y="56%" dominant-baseline="middle" text-anchor="middle" font-family="monospace" font-size="8" fill="#00f0ff" opacity="0.7">SIGNAL LOST</text>' +
    "</svg>"
  );

export function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function setText(sel, text) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (el) el.textContent = text ?? "";
}

export function setHtml(sel, html) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (el) el.innerHTML = html ?? "";
}

export function playIcon(size = 16) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>`;
}

export function posterStyle(url) {
  if (!url) return "";
  return `background-image:url('${url}')`;
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export function skeletonShelf(count = 8) {
  return Array.from({ length: count }, (_, i) => `
    <article class="skel-card" style="animation-delay:${(i * 0.04).toFixed(2)}s">
      <div class="skel-card-poster"></div>
      <div class="skel-card-body">
        <div class="skel-line skel-line--mid"></div>
        <div class="skel-line skel-line--narrow"></div>
      </div>
    </article>
  `).join("");
}

export function skeletonEpisodes(count = 6) {
  return Array.from({ length: count }, (_, i) => `
    <div class="ep-skeleton" style="animation-delay:${(i * 0.05).toFixed(2)}s">
      <div class="ep-skeleton-thumb"></div>
      <div class="ep-skeleton-body">
        <div class="ep-skeleton-line ep-skeleton-line--mid"></div>
        <div class="ep-skeleton-line ep-skeleton-line--narrow"></div>
      </div>
      <div class="ep-skeleton-play"></div>
    </div>
  `).join("");
}

export function showGenreSkeletons(count = 6) {
  const scroller = $("#genre-scroller");
  if (!scroller) return;
  const frag = document.createDocumentFragment();
  for (let i = 0; i < count; i++) {
    const el = document.createElement("article");
    el.className = "skel-card";
    el.style.animationDelay = `${(i * 0.04).toFixed(2)}s`;
    el.innerHTML = `<div class="skel-card-poster"></div><div class="skel-card-body"><div class="skel-line skel-line--mid"></div><div class="skel-line skel-line--narrow"></div></div>`;
    frag.appendChild(el);
  }
  scroller.appendChild(frag);
}

export function removeGenreSkeletons() {
  const scroller = $("#genre-scroller");
  if (!scroller) return;
  scroller.querySelectorAll(".skel-card").forEach((n) => n.remove());
}

export function removeOneGenreSkeleton() {
  const scroller = $("#genre-scroller");
  if (!scroller) return;
  const first = scroller.querySelector(".skel-card");
  if (first) first.remove();
}
