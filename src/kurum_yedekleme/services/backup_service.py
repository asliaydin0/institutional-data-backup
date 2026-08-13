"""UI ile çekirdek arasındaki yedekleme servisi."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.core.backup_engine import BackupEngine, BackupResult
from kurum_yedekleme.services.config_validation import (
    ProductionConfigError,
    validate_production_settings,
)
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.services.preflight import (
    InsufficientDiskSpaceError,
    assert_disk_space_for_backup,
)

logger = logging.getLogger(__name__)


class BackupInProgressError(RuntimeError):
    """Aynı anda yalnızca bir yedekleme çalışabilir."""


class BackupService:
    """Manuel / zamanlanmış yedekleme — tek job kilidi ile."""

    def __init__(
        self,
        settings: AppSettings,
        history_service: Optional[HistoryService] = None,
        *,
        test_mode: bool = False,
    ) -> None:
        self._settings = settings
        self._engine = BackupEngine(settings)
        self._history = history_service
        self._lock = threading.Lock()
        self._busy = False
        self._test_mode = bool(test_mode)

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def test_mode(self) -> bool:
        return self._test_mode

    def set_test_mode(self, enabled: bool) -> None:
        self._test_mode = bool(enabled)

    def update_settings(self, settings: AppSettings) -> None:
        """Yapılandırma değişince motoru yeniler (job yokken)."""
        with self._lock:
            if self._busy:
                raise BackupInProgressError(
                    "Yedekleme sürerken ayarlar güncellenemez."
                )
            self._settings = settings
            self._engine = BackupEngine(settings)

    def start_manual_backup(self) -> str:
        """Manuel yedekleme çalıştırır, geçmişe kaydeder, Türkçe özet döner."""
        logger.info("Manuel yedekleme isteği alındı.")
        try:
            result = self.run_backup(trigger="manual")
            return result.format_report()
        except BackupInProgressError:
            return (
                "Şu anda başka bir yedekleme devam ediyor. "
                "Lütfen bitmesini bekleyin."
            )
        except (ProductionConfigError, InsufficientDiskSpaceError) as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Manuel yedekleme başarısız")
            return f"Yedekleme başlatılamadı:\n{exc}"

    def run_backup(self, **kwargs) -> BackupResult:
        """Programatik yedekleme — eşzamanlı ikinci işi reddeder."""
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            raise BackupInProgressError(
                "Aynı anda yalnızca bir yedekleme çalışabilir."
            )
        self._busy = True
        try:
            return self._run_locked(**kwargs)
        finally:
            self._busy = False
            self._lock.release()

    def _is_test_context(self, kwargs: dict) -> bool:
        if kwargs.get("skip_production_guards"):
            return True
        if self._test_mode:
            return True
        if os.environ.get("KURUM_YEDEKLEME_TEST_MODE", "").strip() in {
            "1",
            "true",
            "TRUE",
            "yes",
        }:
            return True
        return False

    def _run_locked(self, **kwargs) -> BackupResult:
        test_ctx = self._is_test_context(kwargs)

        # Production güvenlik: config + disk (TEST MODE / birim testleri hariç)
        if not test_ctx:
            result = validate_production_settings(self._settings)
            result.raise_if_invalid()
            assert_disk_space_for_backup(self._settings)

        source = kwargs.get("source")
        if source is None:
            enabled = [s for s in self._settings.sources if s.enabled]
            source_path = enabled[0].path if enabled else ""
        else:
            source_path = str(getattr(source, "path", source))

        destination = kwargs.get("destination")
        if destination is not None:
            dest_path = str(destination)
        else:
            dest_path = self._settings.destination.unc_path

        trigger = str(kwargs.get("trigger", "manual"))
        record_id: Optional[int] = None
        if self._history is not None:
            record_id = self._history.start_run(
                source_path=source_path,
                destination_path=dest_path,
            )

        try:
            # Test yardımcıları engine'e sızmasın
            engine_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k not in {"skip_production_guards"}
            }
            result = self._engine.run_backup(**engine_kwargs)

            # Production safety: transfer başarısız / hash yoksa SUCCESS sayma
            if (
                not test_ctx
                and result.success
                and engine_kwargs.get("transfer", True)
            ):
                if not result.remote_path or not result.local_sha256:
                    result.success = False
                    result.status = "BAŞARISIZ"
                    result.message = (
                        "Aktarım veya SHA-256 doğrulaması tamamlanmadan "
                        "yedekleme SUCCESS olamaz."
                    )
                    logger.error(result.message)

            if self._history is not None and record_id is not None:
                self._history.complete_from_result(record_id, result)
            logger.info(
                "Yedekleme bitti (trigger=%s, success=%s)",
                trigger,
                result.success,
            )
            return result
        except Exception as exc:
            if self._history is not None and record_id is not None:
                self._history.mark_failed(record_id, error_message=str(exc))
            raise
