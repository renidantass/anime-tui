"""Implementações concretas de :class:`VideoBackend`."""

from __future__ import annotations

import json
import logging
import os
import socket
import stat
import subprocess
import threading
import time
import uuid
import webbrowser
from contextlib import suppress
from pathlib import Path

from app.infrastructure.player.base import (
    DEFAULT_UA,
    PlayRequest,
    PositionCallback,
    VideoBackend,
    ensure_ipc_dir,
    popen,
    which,
)
from app.infrastructure.security import is_safe_url, safe_player_url

logger = logging.getLogger(__name__)


def _process_stayed_up(proc: subprocess.Popen, wait: float = 0.35) -> bool:
    """True se o processo ainda está vivo após *wait* (filtra crash imediato)."""
    time.sleep(wait)
    code = proc.poll()
    if code is not None:
        logger.warning("Player encerrou cedo (exit=%s)", code)
        return False
    return True


# ── Helpers de IPC / RC ──────────────────────────────────────────────────────


def _mpv_command(ipc_path: str, command: list) -> dict | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(ipc_path)
            sock.sendall((json.dumps({"command": command}) + "\n").encode())
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            return json.loads(data.decode()) if data else None
    except (OSError, json.JSONDecodeError, TimeoutError):
        return None


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
            with suppress(OSError):
                sock.recv(4096)
            if passwd:
                sock.sendall((passwd + "\n").encode())
                time.sleep(0.08)
                with suppress(OSError):
                    sock.recv(4096)
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
            lines = [
                ln.strip()
                for ln in data.decode(errors="replace").replace(">", "\n").splitlines()
                if ln.strip() and not ln.strip().startswith("VLC")
            ]
            return lines[-1] if lines else None
    except OSError:
        return None


def _poll_position(
    proc: subprocess.Popen,
    on_position: PositionCallback,
    read_pos_dur,
    *,
    wait_ready=None,
    poll_interval: float = 2.0,
    final_on_exit: bool = True,
) -> None:
    """Loop genérico de progresso: *read_pos_dur* → (pos, dur) | None."""
    if wait_ready:
        wait_ready()

    last_pos, last_dur = 0.0, 0.0
    while proc.poll() is None:
        pair = read_pos_dur()
        if pair is not None:
            pos, dur = pair
            if pos is not None:
                last_pos = pos
            if dur is not None:
                last_dur = dur
            if last_pos > 0 or last_dur > 0:
                on_position(last_pos, last_dur)
        time.sleep(poll_interval)

    if final_on_exit and (last_pos > 0 or last_dur > 0):
        pair = read_pos_dur()
        if pair is not None:
            pos, dur = pair
            if pos is not None:
                last_pos = pos
            if dur is not None:
                last_dur = dur
        if last_pos > 0 or last_dur > 0:
            on_position(last_pos, last_dur)


# ── Backends ─────────────────────────────────────────────────────────────────


class MpvBackend(VideoBackend):
    id = "mpv"
    label = "mpv"
    binary = "mpv"
    install_hint = "sudo apt install mpv"
    supports_progress = True

    def _launch(self, request: PlayRequest) -> bool:
        exe = which("mpv")
        if not exe:
            return False

        ipc_path: str | None = None
        if request.on_position is not None or request.start_at > 1:
            ipc_path = str(ensure_ipc_dir() / f"mpv-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock")

        # --ytdl=no: evita youtube-dl/yt-dlp (403 em CDNs com anti-leech)
        args = [
            exe,
            "--force-window=immediate",
            "--keep-open=no",
            "--no-terminal",
            "--ytdl=no",
        ]
        if ipc_path:
            args.append(f"--input-ipc-server={ipc_path}")
        if request.start_at and request.start_at > 1:
            args.append(f"--start={request.start_at}")
        if request.stream:
            args += [f"--user-agent={DEFAULT_UA}"]
            if request.referer:
                args.append(f"--referrer={request.referer}")
        args += ["--", request.target]

        logger.info("Reproduzindo com mpv: %s…", request.target[:80])
        proc = popen(args)
        if proc is None or not _process_stayed_up(proc):
            return False

        if ipc_path:
            self._chmod_socket_async(ipc_path)
            self._start_monitor(proc, request.on_position, ipc_path=ipc_path)
        return True

    @staticmethod
    def _chmod_socket_async(ipc_path: str) -> None:
        def _chmod_sock() -> None:
            for _ in range(50):
                if Path(ipc_path).exists():
                    with suppress(OSError):
                        os.chmod(ipc_path, stat.S_IRUSR | stat.S_IWUSR)
                    return
                time.sleep(0.05)

        threading.Thread(target=_chmod_sock, daemon=True).start()

    def _monitor(
        self,
        proc: subprocess.Popen,
        on_position: PositionCallback,
        **ctx,
    ) -> None:
        ipc_path: str = ctx["ipc_path"]

        def wait_ready() -> None:
            for _ in range(50):
                if Path(ipc_path).exists() or proc.poll() is not None:
                    break
                time.sleep(0.1)

        def read_pos_dur():
            if not Path(ipc_path).exists():
                return None
            pos_r = _mpv_command(ipc_path, ["get_property", "time-pos"])
            dur_r = _mpv_command(ipc_path, ["get_property", "duration"])
            pos = dur = None
            try:
                if pos_r and pos_r.get("error") == "success" and pos_r.get("data") is not None:
                    pos = float(pos_r["data"])
                if dur_r and dur_r.get("error") == "success" and dur_r.get("data") is not None:
                    dur = float(dur_r["data"])
            except (TypeError, ValueError):
                return None
            return pos, dur

        try:
            _poll_position(
                proc,
                on_position,
                read_pos_dur,
                wait_ready=wait_ready,
                final_on_exit=True,
            )
            # leitura final mesmo se last_* estava em zero (socket ainda vivo)
            if Path(ipc_path).exists():
                pair = read_pos_dur()
                if pair and (pair[0] or pair[1]):
                    on_position(pair[0] or 0.0, pair[1] or 0.0)
        finally:
            with suppress(OSError):
                Path(ipc_path).unlink(missing_ok=True)


class VlcBackend(VideoBackend):
    id = "vlc"
    label = "VLC"
    binary = "vlc"
    install_hint = "sudo apt install vlc"
    supports_progress = True

    def _launch(self, request: PlayRequest) -> bool:
        exe = which("vlc")
        if not exe:
            return False

        # Progresso via RC só em loopback. NÃO usar --rc-passwd: em VLC 3.x
        # Ubuntu a opção não existe e o processo encerra na hora.
        rc_host: str | None = None
        if request.on_position is not None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            rc_host = f"127.0.0.1:{port}"

        args = [exe]
        if request.start_at and request.start_at > 1:
            args.append(f"--start-time={int(request.start_at)}")
        if rc_host:
            args += ["--extraintf", "rc", f"--rc-host={rc_host}"]
        args.append(request.target)
        if request.stream:
            args.append(f":http-user-agent={DEFAULT_UA}")
            if request.referer:
                args.append(f":http-referrer={request.referer}")

        logger.info("Reproduzindo com vlc: %s…", request.target[:80])
        proc = popen(args)
        if proc is None or not _process_stayed_up(proc):
            return False

        if rc_host:
            self._start_monitor(
                proc,
                request.on_position,
                rc_host=rc_host,
                rc_passwd=None,
            )
        return True

    def _monitor(
        self,
        proc: subprocess.Popen,
        on_position: PositionCallback,
        **ctx,
    ) -> None:
        rc_host: str = ctx["rc_host"]
        rc_passwd: str | None = ctx.get("rc_passwd")
        host, _, port_s = rc_host.partition(":")
        try:
            port = int(port_s or "0")
        except ValueError:
            port = 0
        if not port:
            proc.wait()
            return

        def wait_ready() -> None:
            for _ in range(40):
                if proc.poll() is not None:
                    return
                if _vlc_rc_cmd(host, port, "status", passwd=rc_passwd) is not None:
                    break
                time.sleep(0.15)

        def read_pos_dur():
            t = _vlc_rc_cmd(host, port, "get_time", passwd=rc_passwd)
            length = _vlc_rc_cmd(host, port, "get_length", passwd=rc_passwd)
            pos = dur = None
            try:
                if t is not None and t.lstrip("-").isdigit():
                    pos = float(t)
                if length is not None and length.lstrip("-").isdigit():
                    dur = float(length)
            except (TypeError, ValueError):
                return None
            return pos, dur

        _poll_position(
            proc,
            on_position,
            read_pos_dur,
            wait_ready=wait_ready,
            final_on_exit=True,
        )


class GstreamerBackend(VideoBackend):
    id = "gstreamer"
    label = "GStreamer"
    binary = "gst-launch-1.0"
    install_hint = "sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good"

    def is_available(self) -> bool:
        return bool(which("gst-launch-1.0"))

    def _launch(self, request: PlayRequest) -> bool:
        gst = which("gst-launch-1.0")
        if not gst:
            return False

        if not request.stream:
            uri = Path(request.target).resolve().as_uri()
            args = [gst, "-e", "playbin", f"uri={uri}"]
            logger.info("Reproduzindo arquivo com gstreamer: %s", request.target)
            return popen(args) is not None

        safe = safe_player_url(request.target)
        if not safe:
            return False

        if request.start_at and request.start_at > 1:
            args = [gst, "-e", "playbin", f"uri={safe}"]
            logger.info("GStreamer playbin (start_at ignorado no stream)")
            return popen(args) is not None

        args = [
            gst,
            "-e",
            "souphttpsrc",
            f"location={safe}",
            f"user-agent={DEFAULT_UA}",
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
        return popen(args) is not None


class FfplayBackend(VideoBackend):
    id = "ffplay"
    label = "ffplay"
    binary = "ffplay"
    selectable = False  # só fallback

    def _launch(self, request: PlayRequest) -> bool:
        exe = which("ffplay")
        if not exe:
            return False
        args = [exe, "-autoexit"]
        if request.start_at and request.start_at > 1:
            args += ["-ss", str(request.start_at)]
        if request.stream:
            hdr = f"User-Agent: {DEFAULT_UA}\r\n"
            if request.referer:
                hdr = f"Referer: {request.referer}\r\n{hdr}"
            args += ["-headers", hdr]
        args.append(request.target)
        logger.info("Reproduzindo com ffplay: %s…", request.target[:80])
        proc = popen(args)
        return proc is not None and _process_stayed_up(proc)


class BrowserBackend(VideoBackend):
    id = "browser"
    label = "Navegador"
    binary = None  # sempre “disponível”

    def _launch(self, request: PlayRequest) -> bool:
        # só http(s); nunca file://
        url = request.target
        if not is_safe_url(url, allow_http=True, resolve_dns=True):
            return False
        try:
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error("Falha ao abrir navegador: %s", e)
            return False


class AutoBackend(VideoBackend):
    """Marcador de preferência — a orquestração resolve a cadeia de fallbacks."""

    id = "auto"
    label = "Automático"
    binary = None

    def is_available(self) -> bool:
        from app.infrastructure.player.registry import auto_chain_available

        return auto_chain_available()

    def _launch(self, request: PlayRequest) -> bool:
        # não lança sozinho; open_video / try_play usam a cadeia
        return False
