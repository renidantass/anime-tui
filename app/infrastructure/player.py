"""Resolve e reproduz vídeos (com suporte a Blogger token).

Estratégia:
1. Extrai stream direto se for URL Blogger.
2. Tenta tocar a URL no player nativo (mpv/vlc/ffplay) — sem baixar tudo.
3. Se não houver player de stream, baixa para o cache e abre o arquivo
   (xdg-open / browser).

Chame :func:`open_video` via ``asyncio.to_thread`` em contextos async.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Callable

import requests

from app.infrastructure.blogger_extractor import extract_best_url, is_blogger_url
from app.infrastructure.sources._utils import HEADERS

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".cache" / "animes-tui" / "videos"
_STREAM_PLAYERS = ("mpv", "vlc", "ffplay")
_DEFAULT_UA = HEADERS.get(
    "User-Agent",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
_BLOGGER_REFERER = "https://www.blogger.com/"

ProgressCallback = Callable[[int, int | None], None]
StatusCallback = Callable[[str], None]


def _cache_path_for(url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:24]
    return _CACHE_DIR / f"{digest}.mp4"


def resolve_stream_url(url: str) -> str:
    """Converte URL embutida (Blogger etc.) em stream direto, se possível."""
    if is_blogger_url(url):
        return extract_best_url(url)
    return url


def _notify(status: StatusCallback | None, msg: str) -> None:
    if status:
        try:
            status(msg)
        except Exception:
            logger.debug("status callback falhou", exc_info=True)


def download_video(
    stream_url: str,
    dest: Path,
    *,
    referer: str = "https://www.blogger.com/",
    progress: ProgressCallback | None = None,
    session: requests.Session | None = None,
) -> Path:
    """Baixa o stream para *dest* (resume se parcial). Retorna o path final."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")

    own = session is None
    sess = session or requests.Session()
    sess.headers.update(HEADERS)

    headers = {
        "Referer": referer,
        "Origin": "https://www.blogger.com",
    }

    try:
        if dest.exists() and dest.stat().st_size > 0:
            logger.info("Cache hit: %s", dest.name)
            if progress:
                size = dest.stat().st_size
                progress(size, size)
            return dest

        start = partial.stat().st_size if partial.exists() else 0
        if start:
            headers["Range"] = f"bytes={start}-"

        resp = sess.get(stream_url, headers=headers, stream=True, timeout=60)
        try:
            if resp.status_code == 416:
                resp.close()
                partial.unlink(missing_ok=True)
                start = 0
                headers.pop("Range", None)
                resp = sess.get(stream_url, headers=headers, stream=True, timeout=60)

            resp.raise_for_status()

            total: int | None = None
            cr = resp.headers.get("Content-Range")
            if cr and "/" in cr:
                try:
                    total = int(cr.rsplit("/", 1)[1])
                except ValueError:
                    total = None
            elif resp.headers.get("Content-Length"):
                try:
                    total = start + int(resp.headers["Content-Length"])
                except ValueError:
                    total = None

            mode = "ab" if start and resp.status_code == 206 else "wb"
            if mode == "wb":
                start = 0

            downloaded = start
            with open(partial, mode) as f:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
        finally:
            resp.close()

        partial.replace(dest)
        logger.info("Download concluído: %s (%s bytes)", dest.name, dest.stat().st_size)
        return dest
    finally:
        if own:
            sess.close()


def _popen(args: list[str]) -> bool:
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError as e:
        logger.warning("Falha ao executar %s: %s", args[0], e)
        return False


def _stream_with_player(stream_url: str, *, referer: str = _BLOGGER_REFERER) -> bool:
    """Toca a URL direta sem baixar o arquivo inteiro."""
    for name in _STREAM_PLAYERS:
        exe = shutil.which(name)
        if not exe:
            continue
        if name == "mpv":
            args = [
                exe,
                f"--referrer={referer}",
                f"--user-agent={_DEFAULT_UA}",
                "--force-window=immediate",
                stream_url,
            ]
        elif name == "vlc":
            args = [
                exe,
                "--http-referrer",
                referer,
                "--http-user-agent",
                _DEFAULT_UA,
                stream_url,
            ]
        else:  # ffplay
            args = [
                exe,
                "-headers",
                f"Referer: {referer}\r\nUser-Agent: {_DEFAULT_UA}\r\n",
                "-autoexit",
                stream_url,
            ]
        logger.info("Streaming com %s", name)
        if _popen(args):
            return True

    # Fallback: GStreamer (comum em desktops Linux sem mpv/vlc)
    if _stream_with_gstreamer(stream_url):
        return True
    return False


def _stream_with_gstreamer(stream_url: str) -> bool:
    """Stream HTTP com headers corretos via gst-launch (souphttpsrc)."""
    gst = shutil.which("gst-launch-1.0")
    if not gst:
        return False
    # playbin não envia UA/Referer de forma confiável; souphttpsrc + decodebin sim.
    args = [
        gst,
        "-e",
        "souphttpsrc",
        f"location={stream_url}",
        f"user-agent={_DEFAULT_UA}",
        "!",
        "decodebin",
        "name=d",
        "d.",
        "!",
        "queue",
        "!",
        "videoconvert",
        "!",
        "autovideosink",
        "d.",
        "!",
        "queue",
        "!",
        "audioconvert",
        "!",
        "audioresample",
        "!",
        "autoaudiosink",
    ]
    logger.info("Streaming com gst-launch-1.0")
    return _popen(args)

def _open_local_file(path: Path) -> bool:
    for name in _STREAM_PLAYERS:
        exe = shutil.which(name)
        if exe and _popen([exe, str(path)]):
            logger.info("Reproduzindo arquivo com %s: %s", name, path)
            return True

    xdg = shutil.which("xdg-open")
    if xdg and _popen([xdg, str(path)]):
        logger.info("Reproduzindo com xdg-open: %s", path)
        return True

    try:
        webbrowser.open(path.as_uri())
        return True
    except Exception as e:
        logger.error("Nenhum player disponível: %s", e)
        return False


def has_stream_player() -> bool:
    return any(shutil.which(name) for name in _STREAM_PLAYERS) or bool(
        shutil.which("gst-launch-1.0")
    )

def open_video(
    url: str,
    *,
    progress: ProgressCallback | None = None,
    status: StatusCallback | None = None,
    force_download: bool = False,
) -> bool:
    """Extrai (se Blogger) e toca o vídeo.

    Por padrão tenta **stream** no mpv/vlc/ffplay (rápido). Só baixa o
    arquivo inteiro se não houver player de stream ou se
    ``force_download=True``.

    Returns:
        True se o player foi lançado com sucesso.
    """
    if not url:
        return False

    sess = requests.Session()
    sess.headers.update(HEADERS)

    try:
        _notify(status, "Resolvendo URL do vídeo…")
        try:
            if is_blogger_url(url):
                stream_url = extract_best_url(url, session=sess)
            else:
                stream_url = url
        except Exception as e:
            logger.warning("Falha ao resolver stream de '%s': %s", url[:80], e)
            _notify(status, f"Erro ao extrair vídeo: {e}")
            try:
                webbrowser.open(url)
                return True
            except Exception:
                return False

        is_direct = (
            is_blogger_url(url)
            or "googlevideo.com" in stream_url
            or stream_url.endswith(".mp4")
            or "mime=video" in stream_url
        )

        # 1) Stream nativo — não espera baixar 200MB+
        if is_direct and not force_download:
            if has_stream_player():
                _notify(status, "Abrindo no player…")
                if _stream_with_player(stream_url):
                    return True
                logger.warning("Player de stream falhou; tentando download")
            else:
                logger.info("Nenhum player de stream; indo para download")

        # 2) Download + arquivo local
        if is_direct:
            try:
                dest = _cache_path_for(url if is_blogger_url(url) else stream_url)
                if dest.exists() and dest.stat().st_size > 0:
                    _notify(status, "Abrindo do cache…")
                    return _open_local_file(dest)

                _notify(status, "Baixando vídeo… (pode demorar)")

                def _progress(done: int, total: int | None) -> None:
                    if progress:
                        progress(done, total)
                    if status and total and total > 0:
                        pct = min(100, int(done * 100 / total))
                        mb_done = done / (1024 * 1024)
                        mb_total = total / (1024 * 1024)
                        status(f"Baixando… {pct}% ({mb_done:.0f}/{mb_total:.0f} MB)")
                    elif status:
                        status(f"Baixando… {done / (1024 * 1024):.0f} MB")

                path = download_video(
                    stream_url,
                    dest,
                    progress=_progress,
                    session=sess,
                )
                _notify(status, "Abrindo vídeo…")
                return _open_local_file(path)
            except Exception as e:
                logger.warning("Download falhou: %s", e)
                _notify(status, f"Falha no download: {e}")

        # 3) Browser
        _notify(status, "Abrindo no navegador…")
        try:
            webbrowser.open(stream_url if stream_url != url else url)
            return True
        except Exception as e:
            logger.error("Falha ao abrir vídeo: %s", e)
            _notify(status, f"Erro: {e}")
            return False
    finally:
        sess.close()
