"""Orquestra stream / download / fallbacks a partir de :class:`PlayContext`."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import requests

from app.domain import PlayContext
from app.infrastructure.blogger_extractor import is_blogger_url
from app.infrastructure.config import load as load_config
from app.infrastructure.player.base import (
    CACHE_DIR,
    PlayRequest,
    PositionCallback,
    ProgressCallback,
    StatusCallback,
    popen,
)
from app.infrastructure.player.download import cache_path_for, download_video
from app.infrastructure.player.registry import (
    PLAYER_AUTO,
    PLAYER_BROWSER,
    VALID_PLAYERS,
    get_backend,
    is_player_available,
    try_play,
)
from app.infrastructure.security import is_safe_url
from app.infrastructure.sources._playback import resolve_blogger_context
from app.infrastructure.sources._utils import HEADERS

logger = logging.getLogger(__name__)


def _notify(status: StatusCallback | None, msg: str) -> None:
    if status:
        try:
            status(msg)
        except Exception:
            logger.debug("status callback falhou", exc_info=True)


def _as_context(value: PlayContext | str) -> PlayContext:
    if isinstance(value, PlayContext):
        return value
    # string legada: sem metadados de fonte — só browser/página
    return PlayContext.page(value)


def _finalize_context(
    ctx: PlayContext,
    *,
    session: requests.Session,
    status: StatusCallback | None,
) -> PlayContext:
    """Resolve embeds ainda pendentes (ex.: Blogger token → googlevideo).

    A source entrega URL + headers; a resolução técnica do player embutido
    Blogger fica aqui para ter retry + feedback na UI (como antes).
    """
    url = (ctx.url or "").strip()
    if not url or not is_blogger_url(url):
        return ctx

    _notify(status, "Resolvendo URL do vídeo…")
    page = ctx.page_url or url
    resolved = resolve_blogger_context(url, page_url=page, session=session)
    if resolved is None:
        # retry único com sessão limpa
        resolved = resolve_blogger_context(url, page_url=page, session=None)
    if resolved is None:
        logger.warning("Não foi possível resolver embed Blogger: %s…", url[:80])
        _notify(status, "Erro ao extrair stream do Blogger")
        # mantém embed; is_direct=False para cair no browser, não no mpv com token
        return PlayContext(
            url=url,
            referer=ctx.referer,
            origin=ctx.origin,
            is_direct=False,
            page_url=page,
            cache_key=ctx.cache_key or url,
        )
    return resolved


def _open_local_file(
    path: Path,
    *,
    preferred: str = PLAYER_AUTO,
    start_at: float = 0.0,
    on_position: PositionCallback | None = None,
) -> bool:
    path = path.resolve()
    try:
        path.relative_to(CACHE_DIR.resolve())
    except ValueError:
        logger.warning("Recusando abrir arquivo fora do cache: %s", path)
        return False
    if not path.is_file():
        return False

    if preferred == PLAYER_BROWSER:
        logger.warning("Browser não é suportado para arquivo local de cache")
        preferred = PLAYER_AUTO

    if try_play(
        preferred,
        PlayRequest(
            target=str(path),
            stream=False,
            start_at=start_at,
            on_position=on_position,
        ),
    ):
        return True

    xdg = shutil.which("xdg-open")
    if xdg:
        proc = popen([xdg, str(path)])
        if proc is not None:
            logger.info("Reproduzindo com xdg-open: %s", path)
            return True

    logger.error("Nenhum player disponível para %s", path)
    return False


def open_video(
    context: PlayContext | str,
    *,
    progress: ProgressCallback | None = None,
    status: StatusCallback | None = None,
    force_download: bool = False,
    player: str | None = None,
    start_at: float = 0.0,
    on_position: PositionCallback | None = None,
) -> bool:
    """Toca o vídeo descrito por *context* (fornecido pela fonte).

    Args:
        context: PlayContext da fonte (ou str legada = página).
        start_at: segundos de onde retomar.
        on_position: callback (pos, duration) enquanto o player roda (mpv/VLC).

    Returns:
        True se o player foi lançado com sucesso.
    """
    ctx = _as_context(context)
    url = (ctx.url or "").strip()
    if not url:
        return False

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
        ctx = _finalize_context(ctx, session=sess, status=status)
        url = (ctx.url or "").strip()
        if not url:
            return False

        page_url = ctx.page_url or url
        stream_url = url
        is_direct = ctx.is_direct
        referer = ctx.referer or ""

        if is_direct and not is_safe_url(stream_url, allow_http=True, resolve_dns=True):
            _notify(status, "Stream bloqueado por política de segurança")
            return False

        if preferred == PLAYER_BROWSER:
            _notify(status, "Abrindo no navegador…")
            open_u = stream_url if is_direct else page_url
            # preferir página do episódio se stream ainda for embed não resolvido
            if is_blogger_url(open_u):
                open_u = page_url
            browser = get_backend(PLAYER_BROWSER)
            if browser and browser.play(PlayRequest(target=open_u, stream=True)):
                return True
            _notify(status, "Erro ao abrir navegador")
            return False

        if preferred not in (PLAYER_AUTO, PLAYER_BROWSER) and not is_player_available(preferred):
            _notify(
                status,
                f"{preferred} não encontrado no PATH — tentando fallback…",
            )
            logger.warning("Player preferido '%s' indisponível", preferred)

        if start_at > 1:
            _notify(status, f"Retomando em {int(start_at)}s…")

        req = PlayRequest(
            target=stream_url,
            stream=True,
            referer=referer,
            start_at=start_at,
            on_position=on_position,
        )

        # 1) Stream nativo
        if is_direct and not force_download and not is_blogger_url(stream_url):
            _notify(status, f"Abrindo no player ({preferred})…")
            if try_play(preferred, req):
                return True
            logger.warning("Stream no player falhou; tentando download")

        # 2) Download + arquivo local
        if is_direct and not is_blogger_url(stream_url):
            try:
                dest = cache_path_for(ctx.cache_key or stream_url)
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
                    referer=ctx.referer,
                    origin=ctx.origin,
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
        open_u = page_url
        if is_direct and stream_url and not is_blogger_url(stream_url):
            open_u = stream_url
        browser = get_backend(PLAYER_BROWSER)
        if browser and browser.play(PlayRequest(target=open_u, stream=True)):
            return True
        _notify(status, "Não foi possível abrir o vídeo")
        return False
    finally:
        sess.close()
