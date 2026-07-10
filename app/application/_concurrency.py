"""Utilitários de concorrência — fan-out pattern para fontes e serviços."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from concurrent.futures import Future, as_completed

logger = logging.getLogger(__name__)


def fan_out(
    executor,
    fn: Callable,
    items: Iterable,
    *,
    strategy: str = "collect",
) -> list:
    """Dispara fn(item) em paralelo.

    strategy:
      'collect' — coleta todos os resultados (ignora erros).
      'first'   — retorna o primeiro resultado com sucesso, cancela os demais.

    Erros são logados e ignorados silenciosamente.
    """
    futures: dict[Future, object] = {executor.submit(fn, item): item for item in items}
    results: list = []

    for future in as_completed(futures):
        item = futures[future]
        try:
            result = future.result()
        except Exception:
            logger.debug("fan_out falhou para %s", item, exc_info=True)
            continue
        if strategy == "first" and result:
            for f in futures:
                f.cancel()
            return [result]
        if result:
            results.append(result)

    return results
