from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote, urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def validate_response(response: requests.Response) -> bool:
    return 200 <= response.status_code < 300


def _strip_accents(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def _clean_num(raw: str) -> str | None:
    """Normaliza dígitos (remove zeros à esquerda, rejeita anos óbvios sozinhos)."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw.isdigit():
        # "12.5" / "12v2" — pega só o inteiro inicial
        m = re.match(r"(\d+)", raw)
        if not m:
            return None
        raw = m.group(1)
    # evita ano sozinho como "episódio"
    if len(raw) == 4 and raw.startswith(("19", "20")):
        return None
    # remove zeros à esquerda, mas mantém "0" se for o caso
    cleaned = str(int(raw))
    return cleaned


# Padrões do mais específico ao mais genérico (sobre *texto* já normalizado).
# Evita número solto no fim do título ("Nome 2" = temporada, não episódio).
_EP_PATTERNS: list[re.Pattern[str]] = [
    # S01E12 / s1e12
    re.compile(r"\bs\d{1,2}\s*e\s*(\d{1,4})\b", re.I),
    # Episódio 12 / Episodio 12 / Episode 12 / Capítulo 12 / Capitulo 12
    re.compile(
        r"\b(?:episodios?|episodes?|capitulos?|cap[ií]tulos?)\s*[#.:\-–—]?\s*(\d{1,4})\b",
        re.I,
    ),
    # Ep 12 / Ep.12 / EP - 12 / Eps 3
    re.compile(r"\beps?\.?\s*[#.:\-–—]?\s*(\d{1,4})\b", re.I),
    # Cap. 12 / Cap 12
    re.compile(r"\bcap\.?\s*[#.:\-–—]?\s*(\d{1,4})\b", re.I),
    # E12 / E 12 (token sozinho ou com separador; não "e" de frase)
    re.compile(r"(?:^|[\s\-–—|/])e\s*(\d{1,4})\b", re.I),
    # #12
    re.compile(r"#\s*(\d{1,4})\b"),
    # " - 12" / " – 12" / ": 12" no final (badge estilo lista)
    re.compile(r"[\-–—:|]\s*(\d{1,4})\s*$"),
    # string que é só o número (badge "12")
    re.compile(r"^(\d{1,4})$"),
]

_URL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:episodio|episode|episodios|episodes|ep)[_/\-]?(\d{1,4})",
        re.I,
    ),
    re.compile(r"/e(\d{1,4})(?:/|$)", re.I),
    re.compile(r"[_-](\d{1,4})(?:/|$|\.)"),
]


def extract_episode_number(*parts: str, default: str = "?") -> str:
    """Extrai número de episódio de título, badge, slug de URL, etc.

    Aceita vários pedaços (título + link) e devolve o primeiro match confiável.
    """
    for part in parts:
        if not part:
            continue
        text = unquote(str(part)).replace("_", " ").replace("+", " ")
        # path de URL → espaços
        if "://" in text or text.startswith("/"):
            try:
                path = urlparse(text).path if "://" in text else text
            except Exception:
                path = text
            n = _extract_from_url(path)
            if n:
                return n
            text = path.replace("/", " ").replace("-", " ")

        n = _extract_from_text(text)
        if n:
            return n

        # tenta sem acentos
        n = _extract_from_text(_strip_accents(text))
        if n:
            return n

    return default


def _extract_from_text(text: str) -> str | None:
    if not text:
        return None
    # colapsa espaços
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    for pat in _EP_PATTERNS:
        m = pat.search(text)
        if m:
            num = _clean_num(m.group(1))
            if num is not None:
                return num
    return None


def _extract_from_url(path: str) -> str | None:
    if not path:
        return None
    path = unquote(path)
    for pat in _URL_PATTERNS:
        # pega o *último* match (slug costuma terminar com o ep)
        matches = list(pat.finditer(path))
        if matches:
            num = _clean_num(matches[-1].group(1))
            if num is not None:
                return num
    return None


def get_episode_number(*parts: str, default: str = "?") -> str:
    """Compat: extrai número de episódio de título(s) e/ou URL."""
    return extract_episode_number(*parts, default=default)


def is_unknown_episode_number(value: str | None) -> bool:
    v = (value or "").strip()
    return not v or v in {"?", "0", "00", "000"}


_EP_SUFFIX_RES: list[re.Pattern[str]] = [
    # " - Episódio 12" / " | Ep 3" / ": Episode 1"
    re.compile(
        r"\s*[\-–—:|·•]\s*(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}\s*$",
        re.I,
    ),
    # " Episódio 12" / " Ep 3" no final
    re.compile(
        r"\s+(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}\s*$",
        re.I,
    ),
    # " S01E12" no final
    re.compile(r"\s+s\d{1,2}\s*e\s*\d{1,4}\s*$", re.I),
    # " - 12" só se for bem no fim e curto
    re.compile(r"\s*[\-–—:|]\s*\d{1,4}\s*$"),
]

_ONLY_EP_LABEL = re.compile(
    r"^(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?|cap[ií]tulos?)\s*[#.:]?\s*\d{1,4}$",
    re.I,
)


def strip_episode_suffix(text: str, number: str | None = None) -> str:
    """Remove 'Episódio N' / 'Ep N' do título para evitar 'Ep 1 · Episodio 1'."""
    t = (text or "").strip()
    if not t:
        return ""
    for _ in range(3):
        prev = t
        for pat in _EP_SUFFIX_RES:
            t = pat.sub("", t).strip()
        if number and not is_unknown_episode_number(number):
            n = re.escape(str(int(str(number).strip()) if str(number).strip().isdigit() else number))
            t = re.sub(
                rf"\s*[\-–—:|·•]?\s*(?:epis[oó]dios?|episodes?|eps?\.?|cap\.?)\s*[#.:]?\s*0*{n}\s*$",
                "",
                t,
                flags=re.I,
            ).strip()
        if t == prev:
            break
    return t


def is_only_episode_label(text: str) -> bool:
    return bool(_ONLY_EP_LABEL.match((text or "").strip()))


# Variações de fonte BR (áudio/qualidade) — NÃO remove temporada (S2, Temporada 2).
_TITLE_VARIANT_RE = re.compile(
    r"\b(?:dublado|legendado|audiodescrito)\b"
    r"|\b(?:dub|leg)\b"
    r"|[(\[]\s*(?:dub|leg|dublado|legendado|pt[- ]?br|ptbr)\s*[)\]]"
    r"|\b(?:full\s*)?hd\b"
    r"|\b\d{3,4}p\b"
    r"|\b(?:online|assistir|completo)\b",
    re.I,
)

_TITLE_HAS_VARIANT_RE = re.compile(
    r"\b(?:dublado|legendado|audiodescrito|dub|leg)\b"
    r"|[(\[]\s*(?:dub|leg|dublado|legendado)\s*[)\]]"
    r"|\b(?:full\s*)?hd\b"
    r"|\b\d{3,4}p\b",
    re.I,
)


def strip_title_variants(title: str) -> str:
    """Remove ruído de variação (Dublado, Legendado, 1080p…) sem tocar em temporada."""
    t = (title or "").strip()
    if not t:
        return ""
    t = _TITLE_VARIANT_RE.sub(" ", t)
    t = re.sub(r"\s*[\-|–—:]\s*$", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -–—|:")
    return t


def title_has_variant_noise(title: str) -> bool:
    """True se o título carrega marcadores de dublado/qualidade."""
    return bool(_TITLE_HAS_VARIANT_RE.search(title or ""))


def prefer_display_title(current: str, candidate: str) -> str:
    """Prefere o título mais “limpo” (sem Dublado/HD) ao mesclar entradas."""
    cur = (current or "").strip()
    cand = (candidate or "").strip()
    if not cur:
        return cand
    if not cand:
        return cur
    cur_noisy = title_has_variant_noise(cur)
    cand_noisy = title_has_variant_noise(cand)
    if cur_noisy and not cand_noisy:
        return cand
    if cand_noisy and not cur_noisy:
        return cur
    # empate: o mais curto costuma ser o canônico
    return cur if len(cur) <= len(cand) else cand


# Áudio: dublado | legendado | original (sem marcador = em geral legendado nas fontes BR)
_DUB_RE = re.compile(
    r"\bdublado\b|\b(?:pt[- ]?br\s+)?dub\b|[(\[]\s*dub\s*[)\]]|/dub(?:lado)?(?:/|$)",
    re.I,
)
_SUB_RE = re.compile(
    r"\blegendado\b|\bleg\b|[(\[]\s*leg\s*[)\]]|/leg(?:endado)?(?:/|$)",
    re.I,
)


def detect_audio_variant(title: str = "", link: str = "") -> str:
    """Detecta variante de áudio a partir do título/URL da fonte.

    Returns:
        "dublado" | "legendado" | "original"
    """
    blob = f"{title or ''} {link or ''}"
    if _DUB_RE.search(blob):
        return "dublado"
    if _SUB_RE.search(blob):
        return "legendado"
    return "original"


def audio_variant_label(variant: str) -> str:
    v = (variant or "").strip().lower()
    if v == "dublado":
        return "Dublado"
    if v == "legendado":
        return "Legendado"
    return "Legendado"  # original sem marcador ≈ legendado nas fontes BR


def normalize_watch_titles(
    anime_title: str,
    episode_title: str = "",
    episode_number: str = "",
) -> tuple[str, str, str]:
    """Normaliza títulos de histórico/player sem redundância de episódio.

    Returns:
        (anime_title, episode_title, episode_number)
        episode_title vazio se for só "Episódio N" (o número já basta).
    """
    num = episode_number if not is_unknown_episode_number(episode_number) else ""
    if not num:
        num = extract_episode_number(episode_title, anime_title, default="")

    anime = strip_episode_suffix(anime_title, num or None)
    ep = strip_episode_suffix(episode_title, num or None)

    if is_only_episode_label(episode_title) or is_only_episode_label(ep):
        ep = ""
    if ep and anime and ep.casefold() == anime.casefold():
        ep = ""
    if not anime:
        anime = strip_episode_suffix(episode_title, num or None) or (anime_title or episode_title or "Anime")
        if is_only_episode_label(anime):
            anime = anime_title or "Anime"

    return anime.strip(), ep.strip(), (num or episode_number or "?").strip()
