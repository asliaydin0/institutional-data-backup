"""Yeniden deneme yardımcısı."""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExhaustedError(Exception):
    """Tüm yeniden denemeler tükendi."""

    def __init__(self, message: str, *, last_error: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.last_error = last_error


class RetryPolicy:
    """Geçici hatalarda üstel geri çekilmeli yeniden deneme."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay_seconds: float = 5.0,
        backoff_multiplier: float = 2.0,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts en az 1 olmalıdır.")
        self.max_attempts = max_attempts
        self.initial_delay_seconds = initial_delay_seconds
        self.backoff_multiplier = backoff_multiplier
        self._sleep = sleep_fn

    def run(
        self,
        operation: Callable[[], T],
        *,
        is_retryable: Optional[Callable[[BaseException], bool]] = None,
        operation_name: str = "işlem",
    ) -> T:
        """
        İşlemi politikaya göre çalıştırır.

        is_retryable False dönerse hemen yükseltir.
        """
        delay = self.initial_delay_seconds
        last_error: Optional[BaseException] = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                logger.info(
                    "%s denemesi %s/%s",
                    operation_name,
                    attempt,
                    self.max_attempts,
                )
                return operation()
            except Exception as exc:  # noqa: BLE001 — retry kararı burada
                last_error = exc
                retryable = True if is_retryable is None else is_retryable(exc)
                if not retryable:
                    logger.error(
                        "%s yeniden denenemeyen hata: %s",
                        operation_name,
                        exc,
                    )
                    raise
                if attempt >= self.max_attempts:
                    break
                logger.warning(
                    "%s başarısız (deneme %s/%s): %s — %.1fs sonra yeniden...",
                    operation_name,
                    attempt,
                    self.max_attempts,
                    exc,
                    delay,
                )
                self._sleep(delay)
                delay *= self.backoff_multiplier

        raise RetryExhaustedError(
            f"{operation_name} {self.max_attempts} denemede başarısız oldu: {last_error}",
            last_error=last_error,
        )
