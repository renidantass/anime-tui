"""Resolve e reproduz vídeos (com suporte a Blogger token).

Estratégia:
1. Extrai stream direto se for URL Blogger.
2. Toca no player configurado (mpv / vlc / auto / browser).
3. Acompanha progresso via IPC (mpv) ou RC (VLC) e reporta em *on_position*.
4. Fallbacks: gstreamer, download+arquivo, navegador.

Chame :func:`open_video` via ``asyncio.to_thread`` em contextos async.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import shutil
import socket
import stat
import subprocess
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Callable

import requests

from app.infrastructure.blogger_extractor import extract_best_url, is_blogger_url
from app.infrastructure.config import (
    PLAYER_AUTO,
    PLAYER_AUTO_ORDER,
    PLAYER_BROWSER,
    PLAYER_GSTREAMER,
    PLAYER_MPV,
    PLAYER_VLC,
    VALID_PLAYERS,
    load as load_config,
)
from app.infrastructure.security import is_safe_url, safe_player_url
from app.infrastructure.sources._utils import HEADERS

_IPC_DIR = Path.home() / ".cache" / "animes-tui" / "ipc"

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".cache" / "animes-tui" / "videos"
_DEFAULT_UA = HEADERS.get(
    "User-Agent",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
_BLOGGER_REFERER = "https://www.blogger.com/"
_TOPANIMES_REFERER = "https://topanimes.net/"
_ALIBABA_PLAYER_REFERER = "https://sk-ru.alibabacdn.net/"

ProgressCallback = Callable[[int, int | None], None]
StatusCallback = Callable[[str], None]
PositionCallback = Callable[[float, float], None]
"""(position_seconds, duration_seconds) — chamado periodicamente e no fim."""


def infer_http_referer(stream_url: str, fallback: str = _BLOGGER_REFERER) -> str:
    """Escolhe Referer HTTP adequado ao host do stream (anti-leech)."""
    u = (stream_url or "").lower()
    if "googlevideo.com" in u or "blogger.com" in u:
        return _BLOGGER_REFERER
    if "incvideo" in u or "csst.online" in u:
        return "https://www.incvideo1.online/"
    if "1a-1791.com" in u or "alibabacdn" in u or "sk-ru." in u:
        return _ALIBABA_PLAYER_REFERER
    if (
        "topanimes.net" in u
        or "b-cdn.net" in u
        or "doce-de-leite" in u
        or "bunny" in u
    ):
        return _TOPANIMES_REFERER
    if "goyabu" in u:
        return "https://goyabu.io/"
    return fallback


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


def is_player_available(name: str) -> bool:
    """Verifica se o executável do player está no PATH."""
    if name == PLAYER_BROWSER:
        return True
    if name == PLAYER_AUTO:
        return any(is_player_available(p) for p in PLAYER_AUTO_ORDER) or bool(
            shutil.which("ffplay")
        )
    if name in (PLAYER_MPV, PLAYER_VLC):
        return bool(shutil.which(name))
    if name == PLAYER_GSTREAMER:
        return bool(shutil.which("gst-launch-1.0"))
    return bool(shutil.which(name))


def download_video(
    stream_url: str,
    dest: Path,
    *,
    referer: str = _BLOGGER_REFERER,
    progress: ProgressCallback | None = None,
    session: requests.Session | None = None,
) -> Path:
    """Baixa o stream para *dest* (resume se parcial). Retorna o path final."""
    if not is_safe_url(stream_url, allow_http=True, resolve_dns=True):
        raise ValueError("URL de download bloqueada por política de segurança")

    # só permite escrever dentro do cache do app
    dest = dest.resolve()
    cache_root = _CACHE_DIR.resolve()
    try:
        dest.relative_to(cache_root)
    except ValueError as e:
        raise ValueError("destino de cache inválido") from e

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


def _popen(args: list[str]) -> subprocess.Popen | None:
    try:
        return subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        logger.warning("Falha ao executar %s: %s", args[0], e)
        return None


def _ensure_ipc_dir() -> Path:
    _IPC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _IPC_DIR.chmod(0o700)
    except OSError:
        pass
    return _IPC_DIR


def _mpv_args(
    target: str,
    *,
    stream: bool,
    referer: str = _BLOGGER_REFERER,
    start_at: float = 0.0,
    ipc_path: str | None = None,
) -> list[str]:
    exe = shutil.which("mpv")
    if not exe:
        return []
    args = [exe, "--force-window=immediate", "--keep-open=no", "--no-terminal"]
    if ipc_path:
        args.append(f"--input-ipc-server={ipc_path}")
    if start_at and start_at > 1:
        args.append(f"--start={start_at}")
    if stream:
        args += [
            f"--referrer={referer}",
            f"--user-agent={_DEFAULT_UA}",
        ]
    # '--' impede que a URL seja interpretada como opção do mpv
    args += ["--", target]
    return args


def _vlc_args(
    target: str,
    *,
    stream: bool,
    referer: str = _BLOGGER_REFERER,
    start_at: float = 0.0,
    rc_host: str | None = None,
    rc_passwd: str | None = None,
) -> list[str]:
    """Monta argv do VLC.

    Headers HTTP de stream precisam ir como *input options* **depois** do MRL.
    """
    exe = shutil.which("vlc")
    if not exe:
        return []
    args = [exe]
    if start_at and start_at > 1:
        args.append(f"--start-time={int(start_at)}")
    if rc_host:
        # VLC 3.x: RC só em loopback + senha aleatória
        args += [
            "--extraintf",
            "rc",
            f"--rc-host={rc_host}",
        ]
        if rc_passwd:
            args.append(f"--rc-passwd={rc_passwd}")
    args.append(target)
    if stream:
        args += [
            f":http-user-agent={_DEFAULT_UA}",
            f":http-referrer={referer}",
        ]
    return args


def _ffplay_args(
    target: str,
    *,
    stream: bool,
    referer: str = _BLOGGER_REFERER,
    start_at: float = 0.0,
) -> list[str]:
    exe = shutil.which("ffplay")
    if not exe:
        return []
    args = [exe, "-autoexit"]
    if start_at and start_at > 1:
        args += ["-ss", str(start_at)]
    if stream:
        args += [
            "-headers",
            f"Referer: {referer}\r\nUser-Agent: {_DEFAULT_UA}\r\n",
        ]
    # ffplay também aceita '--' em builds recentes; URL por último
    args.append(target)
    return args


def _stream_with_gstreamer(stream_url: str, *, start_at: float = 0.0) -> subprocess.Popen | None:
    """Stream HTTP com headers corretos via gst-launch (souphttpsrc)."""
    safe = safe_player_url(stream_url)
    if not safe:
        return None
    gst = shutil.which("gst-launch-1.0")
    if not gst:
        return None
    # souphttpsrc: location como propriedade (sem shell)
    if start_at and start_at > 1:
        args = [
            gst,
            "-e",
            "playbin",
            f"uri={safe}",
        ]
        logger.info("GStreamer playbin (start_at ignorado no stream)")
        return _popen(args)

    args = [
        gst,
        "-e",
        "souphttpsrc",
        f"location={safe}",
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


# ── Progresso (mpv IPC / VLC RC) ─────────────────────────────────────────────


def _mpv_command(ipc_path: str, command: list) -> dict | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(ipc_path)
            payload = (json.dumps({"command": command}) + "\n").encode()
            sock.sendall(payload)
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            if not data:
                return None
            return json.loads(data.decode())
    except (OSError, json.JSONDecodeError, TimeoutError):
        return None


def _monitor_mpv(
    proc: subprocess.Popen,
    ipc_path: str,
    on_position: PositionCallback | None,
    poll_interval: float = 2.0,
) -> None:
    # espera o socket
    for _ in range(50):
        if Path(ipc_path).exists() or proc.poll() is not None:
            break
        time.sleep(0.1)

    last_pos, last_dur = 0.0, 0.0
    while proc.poll() is None:
        if on_position and Path(ipc_path).exists():
            pos_r = _mpv_command(ipc_path, ["get_property", "time-pos"])
            dur_r = _mpv_command(ipc_path, ["get_property", "duration"])
            try:
                if pos_r and pos_r.get("error") == "success" and pos_r.get("data") is not None:
                    last_pos = float(pos_r["data"])
                if dur_r and dur_r.get("error") == "success" and dur_r.get("data") is not None:
                    last_dur = float(dur_r["data"])
                if last_pos > 0 or last_dur > 0:
                    on_position(last_pos, last_dur)
            except (TypeError, ValueError):
                pass
        time.sleep(poll_interval)

    # leitura final
    if on_position and Path(ipc_path).exists():
        pos_r = _mpv_command(ipc_path, ["get_property", "time-pos"])
        dur_r = _mpv_command(ipc_path, ["get_property", "duration"])
        try:
            if pos_r and pos_r.get("error") == "success" and pos_r.get("data") is not None:
                last_pos = float(pos_r["data"])
            if dur_r and dur_r.get("error") == "success" and dur_r.get("data") is not None:
                last_dur = float(dur_r["data"])
            if last_pos > 0 or last_dur > 0:
                on_position(last_pos, last_dur)
        except (TypeError, ValueError):
            pass

    try:
        Path(ipc_path).unlink(missing_ok=True)
    except OSError:
        pass


def _vlc_rc_cmd(
    host: str,
    port: int,
    cmd: str,
    *,
    passwd: str | None = None,
) -> str | None:
    try:
        with socket.create_connection((host, port), timeout=1.0) as sock:
            sock.settimeout(1.0)
            # drena banner / prompt de senha
            try:
                banner = sock.recv(4096)
            except OSError:
                banner = b""
            if passwd:
                # Com --rc-passwd o VLC exige a senha na primeira linha
                sock.sendall((passwd + "\n").encode())
                time.sleep(0.08)
                try:
                    sock.recv(4096)
                except OSError:
                    pass
            sock.sendall((cmd.strip() + "\n").encode())
            time.sleep(0.05)
            data = b""
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data or len(data) > 256:
                        break
            except OSError:
                pass
            text = data.decode(errors="replace")
            lines = [
                ln.strip()
                for ln in text.replace(">", "\n").splitlines()
                if ln.strip() and not ln.strip().startswith("VLC")
            ]
            return lines[-1] if lines else None
    except OSError:
        return None


def _monitor_vlc(
    proc: subprocess.Popen,
    rc_host: str,
    on_position: PositionCallback | None,
    poll_interval: float = 2.0,
    rc_passwd: str | None = None,
) -> None:
    host, _, port_s = rc_host.partition(":")
    try:
        port = int(port_s or "0")
    except ValueError:
        port = 0
    if not port:
        proc.wait()
        return

    for _ in range(40):
        if proc.poll() is not None:
            return
        if _vlc_rc_cmd(host, port, "status", passwd=rc_passwd) is not None:
            break
        time.sleep(0.15)

    last_pos, last_dur = 0.0, 0.0
    while proc.poll() is None:
        if on_position:
            t = _vlc_rc_cmd(host, port, "get_time", passwd=rc_passwd)
            l = _vlc_rc_cmd(host, port, "get_length", passwd=rc_passwd)
            try:
                if t is not None and t.lstrip("-").isdigit():
                    last_pos = float(t)
                if l is not None and l.lstrip("-").isdigit():
                    last_dur = float(l)
                if last_pos > 0 or last_dur > 0:
                    on_position(last_pos, last_dur)
            except (TypeError, ValueError):
                pass
        time.sleep(poll_interval)

    if on_position and (last_pos > 0 or last_dur > 0):
        on_position(last_pos, last_dur)


def _start_progress_monitor(
    name: str,
    proc: subprocess.Popen,
    *,
    ipc_path: str | None = None,
    rc_host: str | None = None,
    rc_passwd: str | None = None,
    on_position: PositionCallback | None = None,
) -> None:
    if not on_position:
        return

    def _run():
        try:
            if name == PLAYER_MPV and ipc_path:
                _monitor_mpv(proc, ipc_path, on_position)
            elif name == PLAYER_VLC and rc_host:
                _monitor_vlc(
                    proc, rc_host, on_position, rc_passwd=rc_passwd
                )
            else:
                proc.wait()
        except Exception:
            logger.debug("monitor de progresso falhou", exc_info=True)

    threading.Thread(target=_run, daemon=True).start()


def _launch_named_player(
    name: str,
    target: str,
    *,
    stream: bool,
    referer: str = _BLOGGER_REFERER,
    start_at: float = 0.0,
    on_position: PositionCallback | None = None,
) -> bool:
    """Lança um player específico. *name*: mpv | vlc | gstreamer | ffplay."""
    # streams remotos: validar URL; arquivos locais: path sob cache ou existente
    if stream:
        safe = safe_player_url(target)
        if not safe:
            logger.warning("Player recusou URL insegura: %s…", target[:80])
            return False
        target = safe
    else:
        p = Path(target)
        if not p.is_file():
            return False
        # só toca arquivos sob o cache do app (evita path injection)
        try:
            p.resolve().relative_to(_CACHE_DIR.resolve())
        except ValueError:
            logger.warning("Arquivo fora do cache recusado: %s", p)
            return False
        target = str(p.resolve())

    ipc_path: str | None = None
    rc_host: str | None = None
    rc_passwd: str | None = None
    args: list[str] = []

    if name == PLAYER_MPV:
        if on_position is not None or start_at > 1:
            ipc_dir = _ensure_ipc_dir()
            ipc_path = str(
                ipc_dir / f"mpv-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
            )
        args = _mpv_args(
            target,
            stream=stream,
            referer=referer,
            start_at=start_at,
            ipc_path=ipc_path,
        )
    elif name == PLAYER_VLC:
        if on_position is not None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            rc_host = f"127.0.0.1:{port}"
            rc_passwd = secrets.token_urlsafe(18)
        args = _vlc_args(
            target,
            stream=stream,
            referer=referer,
            start_at=start_at,
            rc_host=rc_host,
            rc_passwd=rc_passwd,
        )
    elif name == "ffplay":
        args = _ffplay_args(
            target, stream=stream, referer=referer, start_at=start_at
        )
    elif name == PLAYER_GSTREAMER:
        if not stream:
            gst = shutil.which("gst-launch-1.0")
            if not gst:
                return False
            uri = Path(target).resolve().as_uri()
            args = [gst, "-e", "playbin", f"uri={uri}"]
            proc = _popen(args)
            if proc is None:
                return False
            logger.info("Reproduzindo arquivo com gstreamer: %s", target)
            return True
        proc = _stream_with_gstreamer(target, start_at=start_at)
        return proc is not None
    else:
        return False

    if not args:
        return False

    logger.info("Reproduzindo com %s: %s…", name, target[:80])
    proc = _popen(args)
    if proc is None:
        return False

    # restringe permissões do socket mpv assim que existir
    if ipc_path:
        def _chmod_sock():
            for _ in range(50):
                if Path(ipc_path).exists():
                    try:
                        os.chmod(ipc_path, stat.S_IRUSR | stat.S_IWUSR)
                    except OSError:
                        pass
                    return
                time.sleep(0.05)

        threading.Thread(target=_chmod_sock, daemon=True).start()

    if on_position is not None and name in (PLAYER_MPV, PLAYER_VLC):
        _start_progress_monitor(
            name,
            proc,
            ipc_path=ipc_path,
            rc_host=rc_host,
            rc_passwd=rc_passwd,
            on_position=on_position,
        )
    return True


def _player_fallback_order(preferred: str) -> list[str]:
    """Ordem de tentativa: preferido primeiro, depois os demais + ffplay."""
    if preferred == PLAYER_BROWSER:
        return []
    if preferred == PLAYER_AUTO:
        return [*PLAYER_AUTO_ORDER, "ffplay"]
    rest = [p for p in PLAYER_AUTO_ORDER if p != preferred]
    return [preferred, *rest, "ffplay"]


def _stream_with_player(
    stream_url: str,
    *,
    preferred: str = PLAYER_AUTO,
    referer: str = _BLOGGER_REFERER,
    start_at: float = 0.0,
    on_position: PositionCallback | None = None,
) -> bool:
    """Toca a URL direta com o player preferido (+ fallbacks)."""
    if preferred == PLAYER_BROWSER:
        return False
    if not safe_player_url(stream_url):
        return False

    for name in _player_fallback_order(preferred):
        if _launch_named_player(
            name,
            stream_url,
            stream=True,
            referer=referer,
            start_at=start_at,
            on_position=on_position,
        ):
            return True
    return False


def _open_local_file(
    path: Path,
    *,
    preferred: str = PLAYER_AUTO,
    start_at: float = 0.0,
    on_position: PositionCallback | None = None,
) -> bool:
    path = path.resolve()
    try:
        path.relative_to(_CACHE_DIR.resolve())
    except ValueError:
        logger.warning("Recusando abrir arquivo fora do cache: %s", path)
        return False
    if not path.is_file():
        return False

    if preferred == PLAYER_BROWSER:
        # não abre file:// arbitrário no browser a partir de conteúdo remoto
        logger.warning("Browser não é suportado para arquivo local de cache")
        preferred = PLAYER_AUTO

    for name in _player_fallback_order(preferred):
        if _launch_named_player(
            name,
            str(path),
            stream=False,
            start_at=start_at,
            on_position=on_position,
        ):
            return True

    xdg = shutil.which("xdg-open")
    if xdg:
        proc = _popen([xdg, str(path)])
        if proc is not None:
            logger.info("Reproduzindo com xdg-open: %s", path)
            return True

    logger.error("Nenhum player disponível para %s", path)
    return False


def has_stream_player() -> bool:
    return is_player_available(PLAYER_AUTO)


def open_video(
    url: str,
    *,
    progress: ProgressCallback | None = None,
    status: StatusCallback | None = None,
    force_download: bool = False,
    player: str | None = None,
    start_at: float = 0.0,
    on_position: PositionCallback | None = None,
) -> bool:
    """Extrai (se Blogger) e toca o vídeo.

    Args:
        start_at: segundos de onde retomar.
        on_position: callback (pos, duration) enquanto o player roda (mpv/VLC).

    Returns:
        True se o player foi lançado com sucesso.
    """
    if not url:
        return False

    # página/episode/token: precisa ser URL http(s) segura
    if not is_safe_url(url, allow_http=True, resolve_dns=False):
        _notify(status, "URL inicial bloqueada por segurança")
        return False

    preferred = player or load_config().player
    if preferred not in VALID_PLAYERS:
        preferred = PLAYER_AUTO

    start_at = max(0.0, float(start_at or 0.0))

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
            return False

        if not is_safe_url(stream_url, allow_http=True, resolve_dns=True):
            _notify(status, "Stream bloqueado por política de segurança")
            return False

        low = stream_url.lower()
        is_direct = (
            is_blogger_url(url)
            or "googlevideo.com" in low
            or ".mp4" in low
            or ".m3u8" in low
            or "mime=video" in low
            or "cdn_stream" in low
        )

        if preferred == PLAYER_BROWSER:
            _notify(status, "Abrindo no navegador…")
            try:
                # só http(s) — nunca file://
                open_u = stream_url if is_direct else url
                if not is_safe_url(open_u, allow_http=True, resolve_dns=True):
                    return False
                webbrowser.open(open_u)
                return True
            except Exception as e:
                _notify(status, f"Erro: {e}")
                return False

        if preferred not in (PLAYER_AUTO, PLAYER_BROWSER) and not is_player_available(
            preferred
        ):
            _notify(
                status,
                f"{preferred} não encontrado no PATH — tentando fallback…",
            )
            logger.warning("Player preferido '%s' indisponível", preferred)

        if start_at > 1:
            _notify(status, f"Retomando em {int(start_at)}s…")

        stream_referer = infer_http_referer(stream_url)

        # 1) Stream nativo
        if is_direct and not force_download:
            _notify(status, f"Abrindo no player ({preferred})…")
            if _stream_with_player(
                stream_url,
                preferred=preferred,
                referer=stream_referer,
                start_at=start_at,
                on_position=on_position,
            ):
                return True
            logger.warning("Stream no player falhou; tentando download")

        # 2) Download + arquivo local
        if is_direct:
            try:
                dest = _cache_path_for(url if is_blogger_url(url) else stream_url)
                if dest.exists() and dest.stat().st_size > 0:
                    _notify(status, "Abrindo do cache…")
                    return _open_local_file(
                        dest,
                        preferred=preferred,
                        start_at=start_at,
                        on_position=on_position,
                    )

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
                return _open_local_file(
                    path,
                    preferred=preferred,
                    start_at=start_at,
                    on_position=on_position,
                )
            except Exception as e:
                logger.warning("Download falhou: %s", e)
                _notify(status, f"Falha no download: {e}")

        # 3) Browser (somente http/https seguro)
        _notify(status, "Abrindo no navegador…")
        try:
            open_u = stream_url if stream_url != url else url
            if not is_safe_url(open_u, allow_http=True, resolve_dns=True):
                _notify(status, "URL final bloqueada por segurança")
                return False
            webbrowser.open(open_u)
            return True
        except Exception as e:
            logger.error("Falha ao abrir vídeo: %s", e)
            _notify(status, f"Erro: {e}")
            return False
    finally:
        sess.close()
