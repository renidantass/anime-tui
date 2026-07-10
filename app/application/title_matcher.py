"""Normalização e matching de títulos — funções puras sem estado."""

import re
import unicodedata

from app.application.title_utils import (
    detect_audio_variant,
    extract_episode_number,
    is_unknown_episode_number,
    normalize_watch_titles,
    prefer_display_title,
    strip_title_variants,
)
from app.application.dtos import SourceInfo


def normalize_text(text: str) -> str:
    t = text.lower().strip()
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    t = re.sub(r"[-–—:_/|]", " ", t)
    t = re.sub(r"\bepisodio\b", "ep", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def catalog_key(title: str) -> str:
    return normalize_text(strip_title_variants(title or ""))


def ep_key(ep) -> str:
    number = ep.number if not is_unknown_episode_number(ep.number) else ""
    if not number:
        number = extract_episode_number(ep.title, getattr(ep, "link", "") or "", default="")
    anime_t, _, num = normalize_watch_titles(ep.title or "", ep.title or "", number)
    base = catalog_key(anime_t or ep.title or "")
    if num and not is_unknown_episode_number(num):
        n = str(int(num)) if str(num).strip().isdigit() else str(num).strip()
        return f"{base}|{n}"
    return catalog_key(ep.title or "")


def anime_key(anime) -> str:
    return catalog_key(getattr(anime, "title", "") or "")


def append_source(bucket: list[SourceInfo], *, name: str, video_src: str,
                  link: str, color: str, title: str = "") -> None:
    link = (link or "").strip()
    variant = detect_audio_variant(title, link)
    for s in bucket:
        if link and s.link and s.link == link:
            return
        if s.name == name and (s.variant or "original") == variant:
            return
    bucket.append(SourceInfo(name=name, video_src=video_src or "", link=link,
                             color=color or "", variant=variant, title=title or ""))


def best_title_score(source_title: str, anilist_keys: set[str],
                     anilist_titles: list[str]) -> float:
    sk = normalize_text(source_title)
    if not sk:
        return 0.0
    sk_clean = re.sub(r"\b(dublado|legendado|audiodescrito|ova|ona|movie|filme|special|especiais?)\b",
                      " ", sk)
    sk_clean = re.sub(r"\s+", " ", sk_clean).strip()
    best = 0.0
    for ak in anilist_keys:
        if not ak:
            continue
        if sk == ak or sk_clean == ak:
            return 1.0
        if sk_clean.startswith(ak + " ") or sk.startswith(ak + " "):
            best = max(best, 0.92); continue
        if sk_clean.startswith(ak) and len(sk_clean) - len(ak) <= 4:
            best = max(best, 0.88); continue
        if ak.startswith(sk_clean) and len(sk_clean) >= 10:
            ratio = len(sk_clean) / max(len(ak), 1)
            if ratio >= 0.75:
                best = max(best, 0.8 * ratio)
        sim = _title_similarity(sk_clean, ak)
        extra = max(0, len(sk_clean.split()) - len(ak.split()))
        if extra >= 2: sim *= 0.55
        elif extra == 1: sim *= 0.85
        best = max(best, sim)
    for t in anilist_titles:
        best = max(best, _title_similarity(sk_clean, normalize_text(t)))
    return best


def titles_match(source_title: str, anilist_keys: set[str],
                 anilist_titles: list[str]) -> bool:
    return best_title_score(source_title, anilist_keys, anilist_titles) >= 0.62


def _title_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a).split(), normalize_text(b).split()
    if not na or not nb:
        return 0.0
    inter = len(set(na) & set(nb))
    return inter / max(len(set(na)), len(set(nb)))
