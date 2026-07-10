export function detectAudioVariant(title = "", link = "") {
  const blob = `${title || ""} ${link || ""}`;
  if (
    /\bdublado\b/i.test(blob) ||
    /\b(?:pt[- ]?br\s+)?dub\b/i.test(blob) ||
    /[(\[]\s*dub\s*[)\]]/i.test(blob) ||
    /\/dub(?:lado)?(?:\/|$)/i.test(blob)
  ) {
    return "dublado";
  }
  if (
    /\blegendado\b/i.test(blob) ||
    /\bleg\b/i.test(blob) ||
    /[(\[]\s*leg\s*[)\]]/i.test(blob) ||
    /\/leg(?:endado)?(?:\/|$)/i.test(blob)
  ) {
    return "legendado";
  }
  return "original";
}

export function audioBucket(variant) {
  return variant === "dublado" ? "dublado" : "legendado";
}

export function resolveSourceVariant(s) {
  return s?.variant || detectAudioVariant(s?.title || "", s?.link || "");
}

export function hasAudioChoice(sources) {
  const linked = (sources || []).filter((s) => s?.link);
  if (linked.length < 2) return false;
  const buckets = new Set(linked.map((s) => audioBucket(resolveSourceVariant(s))));
  return buckets.has("dublado") && buckets.has("legendado");
}

export function sourcesForAudioBucket(sources, bucket) {
  return (sources || []).filter(
    (s) => s?.link && audioBucket(resolveSourceVariant(s)) === bucket
  );
}

export function audioOptionMeta(bucket, sources) {
  const names = [...new Set(sources.map((s) => s.name).filter(Boolean))];
  if (bucket === "dublado") {
    return {
      key: "dublado",
      label: "Dublado",
      hint: names.length
        ? `Áudio em português · ${names.join(" · ")}`
        : "Áudio em português",
      accent: "var(--sakura)",
    };
  }
  return {
    key: "legendado",
    label: "Legendado",
    hint: names.length
      ? `Áudio original · ${names.join(" · ")}`
      : "Áudio original com legendas",
    accent: "var(--cyan)",
  };
}
