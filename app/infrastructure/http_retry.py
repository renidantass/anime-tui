"""Retry com exponential backoff para requisições HTTP."""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 30.0


def retry_request(
    method: str,
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 20,
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY,
    max_delay: float = MAX_DELAY,
    **kwargs,
) -> requests.Response | None:
    fetcher = (session or requests).request
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            resp = fetcher(method, url, timeout=timeout, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < max_retries:
                    delay = min(base_delay * (2**attempt), max_delay)
                    logger.debug(
                        "HTTP %d de %s — retry %d/%d em %.1fs",
                        resp.status_code,
                        url[:80],
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            if attempt < max_retries:
                delay = min(base_delay * (2**attempt), max_delay)
                logger.debug(
                    "%s em %s — retry %d/%d em %.1fs",
                    type(e).__name__,
                    url[:80],
                    attempt + 1,
                    max_retries,
                    delay,
                )
                time.sleep(delay)
        except requests.RequestException as e:
            last_exc = e
            break

    if last_exc:
        logger.debug("Requisição falhou após %d tentativas: %s", max_retries + 1, last_exc)
    return None
