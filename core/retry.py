"""
Universal retry / exponential-backoff decorator for PolyBot.

Usage:
    from core.retry import with_retry

    @with_retry(max_attempts=4, base_delay=1.0, label="Gamma API")
    def get_markets():
        ...

    # Or inline:
    result = with_retry(label="CLOB order")(post_order)(args)

Handles:
  - HTTP 429 (rate limit) — respects Retry-After header if present
  - Transient network errors (ConnectionError, Timeout)
  - Any other exception up to max_attempts
"""

from __future__ import annotations

import functools
import os
import time
from typing import Callable, Type
from loguru import logger

import requests


def with_retry(
    max_attempts: int = None,
    base_delay: float = None,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retriable_exceptions: tuple[Type[Exception], ...] = (
        Exception,
    ),
    label: str = "call",
) -> Callable:
    """
    Decorator factory.  Apply to any function that calls an external API.

    Args:
        max_attempts: Total attempts (including first). Defaults to CB_MAX_RETRY_ATTEMPTS env or 5.
        base_delay:   Initial delay in seconds. Defaults to CB_BASE_RETRY_DELAY env or 1.0.
        max_delay:    Maximum delay between retries (caps exponential growth).
        backoff_factor: Multiplier between retries (default 2 → 1s, 2s, 4s, 8s…).
        retriable_exceptions: Exception types to retry on.
        label:        Human-readable name for logging.
    """
    _max_attempts = max_attempts or int(os.getenv("CB_MAX_RETRY_ATTEMPTS", "5"))
    _base_delay = base_delay or float(os.getenv("CB_BASE_RETRY_DELAY", "1.0"))

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            delay = _base_delay

            for attempt in range(1, _max_attempts + 1):
                try:
                    result = fn(*args, **kwargs)
                    return result
                except retriable_exceptions as exc:
                    last_exc = exc
                    is_rate_limit = (
                        isinstance(exc, requests.exceptions.HTTPError)
                        and exc.response is not None
                        and exc.response.status_code == 429
                    )

                    if is_rate_limit:
                        retry_after = int(
                            exc.response.headers.get("Retry-After", delay)
                        )
                        logger.warning(
                            f"[Retry/{label}] Rate-limited (429). "
                            f"Waiting {retry_after}s before retry {attempt}/{_max_attempts}…"
                        )
                        time.sleep(retry_after)
                    elif attempt < _max_attempts:
                        logger.warning(
                            f"[Retry/{label}] Attempt {attempt}/{_max_attempts} failed: {exc}. "
                            f"Retrying in {delay:.1f}s…"
                        )
                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        logger.error(
                            f"[Retry/{label}] All {_max_attempts} attempts exhausted. "
                            f"Last error: {exc}"
                        )

            raise last_exc  # Re-raise after all attempts exhausted

        return wrapper

    return decorator


# ── Convenience pre-configured variants ──────────────────────────────────────

def gamma_retry(fn: Callable) -> Callable:
    """Retry decorator tuned for Gamma API calls."""
    return with_retry(max_attempts=4, base_delay=2.0, label="Gamma")(fn)


def clob_retry(fn: Callable) -> Callable:
    """Retry decorator tuned for CLOB API calls."""
    return with_retry(max_attempts=3, base_delay=1.5, label="CLOB")(fn)


def falcon_retry(fn: Callable) -> Callable:
    """Retry decorator tuned for Falcon / Heisenberg API calls."""
    return with_retry(max_attempts=3, base_delay=2.0, label="Falcon")(fn)
