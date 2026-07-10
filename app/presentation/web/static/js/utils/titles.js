/** Extrai nº do episódio de título/URL (espelha o backend). */
function extractEpisodeNumber(...parts) {
  const patterns = [
    /\bs\d{1,2}\s*e\s*(\d{1,4})\b/i,
    /\b(?:epis[oó]dios?|episodes?|cap[ií]tulos?|capitulos?)\s*[#.:\-–—]?\s*(\d{1,4})\b/i,
    /\beps?\.?\s*[#.:\-–—]?\s*(\d{1,4})\b/i,
    /\bcap\.?\s*[#.:\-–—]?\s*(\d{1,4})\b/i,
    /(?:^|[\s\-–—|/])e\s*(\d{1,4})\b/i,
    /#\s*(\d{1,4})\b/,
    /[\-–—:|]\s*(\d{1,4})\s*$/,
    /^(\d{1,4})$/,
  ];
  const urlPatterns = [
    /(?:episodio|episode|episodios|episodes|ep)[_/\-]?(\d{1,4})/i,
    /\/e(\d{1,4})(?:\/|$)/i,
    /[_-](\d{1,4})(?:\/|$|\.)/,
  ];

  const clean = (raw) => {
    if (!raw) return null;
    const m = String(raw).match(/(\d+)/);
    if (!m) return null;
    const n = m[1];
    if (n.length === 4 && (n.startsWith("19") || n.startsWith("20"))) return null;
    return String(parseInt(n, 10));
  };

  for (const part of parts) {
    if (!part) continue;
    let text = String(part);
    try {
      text = decodeURIComponent(text);
    } catch {
      /* keep raw */
    }
    const isUrl = text.includes("://") || text.startsWith("/");
    if (isUrl) {
      let path = text;
      try {
        path = new URL(text, "https://x").pathname;
      } catch {
        /* keep */
      }
      for (const re of urlPatterns) {
        const all = [...path.matchAll(new RegExp(re.source, re.flags + "g"))];
        if (all.length) {
          const n = clean(all[all.length - 1][1]);
          if (n) return n;
        }
      }
      text = path.replace(/[/_-]+/g, " ");
    }
    for (const re of patterns) {
      const m = text.match(re);
      if (m) {
        const n = clean(m[1]);
        if (n) return n;
      }
    }
  }
  return "";
}

export function resolveEpisodeNumber(known, ...parts) {
  const k = String(known ?? "").trim();
  if (k && k !== "?" && k !== "0") return k;
  return extractEpisodeNumber(...parts) || k || "?";
}

export function formatEpLabel(number) {
  const n = String(number ?? "").trim();
  if (!n || n === "?" || n === "0") return "Ep";
  return `Ep ${n}`;
}

export function stripEpisodeSuffix(text, number) {
  let t = String(text ?? "").trim();
  if (!t) return "";
  const patterns = [
    /\s*[\-–—:|·•]\s*(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}\s*$/i,
    /\s+(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}\s*$/i,
    /\s+s\d{1,2}\s*e\s*\d{1,4}\s*$/i,
    /\s*[\-–—:|]\s*\d{1,4}\s*$/,
  ];
  for (let i = 0; i < 3; i++) {
    const prev = t;
    for (const re of patterns) t = t.replace(re, "").trim();
    const n = String(number ?? "").trim();
    if (n && n !== "?" && n !== "0") {
      const esc = n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      t = t
        .replace(
          new RegExp(
            `\\s*[\\-–—:|·•]?\\s*(?:epis[oó]dios?|episodes?|eps?\\.?|cap\\.?)\\s*[#.:]?\\s*0*${esc}\\s*$`,
            "i"
          ),
          ""
        )
        .trim();
    }
    if (t === prev) break;
  }
  return t;
}

export function isOnlyEpisodeLabel(text) {
  return /^(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}$/i.test(
    String(text ?? "").trim()
  );
}

export function stripTitleVariants(title) {
  let t = String(title || "").trim();
  if (!t) return "";
  t = t
    .replace(/\b(?:dublado|legendado|audiodescrito)\b/gi, " ")
    .replace(/\b(?:dub|leg)\b/gi, " ")
    .replace(/[(\[]\s*(?:dub|leg|dublado|legendado|pt[- ]?br|ptbr)\s*[)\]]/gi, " ")
    .replace(/\b(?:full\s*)?hd\b/gi, " ")
    .replace(/\b\d{3,4}p\b/gi, " ")
    .replace(/\b(?:online|assistir|completo)\b/gi, " ")
    .replace(/\s*[\-|–—:]\s*$/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s\-–—|:]+|[\s\-–—|:]+$/g, "")
    .trim();
  return t;
}

export function normalizeWatchTitles(animeTitle, episodeTitle, number) {
  const num = resolveEpisodeNumber(number, episodeTitle, animeTitle);
  let anime = stripTitleVariants(stripEpisodeSuffix(animeTitle, num));
  let ep = stripEpisodeSuffix(episodeTitle, num);
  ep = stripTitleVariants(ep);

  if (isOnlyEpisodeLabel(episodeTitle) || isOnlyEpisodeLabel(ep)) ep = "";
  if (ep && anime && ep.toLowerCase() === anime.toLowerCase()) ep = "";

  if (!anime) {
    anime =
      stripTitleVariants(stripEpisodeSuffix(episodeTitle, num)) ||
      stripTitleVariants(String(animeTitle || episodeTitle || "Anime").trim()) ||
      "Anime";
    if (isOnlyEpisodeLabel(anime)) {
      anime = stripTitleVariants(String(animeTitle || "Anime").trim()) || "Anime";
    }
  }

  const epLabel = formatEpLabel(num);
  const episodeLine = ep ? `${epLabel} · ${ep}` : epLabel;

  return {
    animeTitle: anime,
    episodeTitle: ep,
    number: num,
    episodeLine,
  };
}

export function cleanTitleForAniList(title) {
  let t = String(title || "").trim();
  if (!t) return "";
  const noise = [
    /\btodos\s+os\s+epis[oó]dios?\b.*$/i,
    /\ball\s+episodes?\b.*$/i,
    /\bonline\b.*$/i,
    /\bassistir\b.*$/i,
    /\bcompleto\b/gi,
    /\bdublado\b/gi,
    /\blegendado\b/gi,
    /\bhd\b/gi,
    /\bfull\s*hd\b/gi,
    /\b\d{3,4}p\b/gi,
  ];
  for (const re of noise) t = t.replace(re, " ");
  t = t.replace(/\s*[\-|–—:]\s*$/g, "").replace(/\s+/g, " ").trim();
  return t;
}
