"""Eski yedek temizliği — yalnızca hedef ZIP dosyalarını siler."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.core.retention import RetentionResult, purge_old_backups
from kurum_yedekleme.services.disk_space import (
    ensure_backup_root_writable,
    validate_production_backup_root,
)

logger = logging.getLogger(__name__)

_STATE_FILE = "retention_state.json"


@dataclass(frozen=True)
class RetentionState:
    period_key: str
    ran_at: str


class RetentionService:
    def __init__(
        self,
        settings: AppSettings,
        *,
        data_dir: Path,
        test_mode: bool = False,
    ) -> None:
        self._settings = settings
        self._data_dir = Path(data_dir)
        self._test_mode = bool(test_mode)
        self._state_path = self._data_dir / _STATE_FILE

    @property
    def config(self):
        return self._settings.retention

    def update_settings(self, settings: AppSettings) -> None:
        self._settings = settings

    def run_if_due(self, period_key: str) -> RetentionResult | None:
        if not self._settings.retention.enabled:
            return None
        if self._load_state() == period_key:
            logger.debug("Temizlik bu dönemde zaten çalıştı: %s", period_key)
            return None
        result = self.run_now()
        self._save_state(period_key)
        return result

    def run_now(self) -> RetentionResult:
        retention = self._settings.retention
        root = self._prepare_root()
        logger.info(
            "Eski yedek temizliği başlıyor (keep_days=%s, kök=%s)",
            retention.keep_days,
            root,
            operation="start",
        )
        result = purge_old_backups(
            root,
            keep_days=retention.keep_days,
        )
        if result.errors:
            logger.warning(
                "Temizlik tamamlandı ancak %s hata var",
                len(result.errors),
            )
        return result

    def last_period_key(self) -> str | None:
        if not self._state_path.is_file():
            return None
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            return str(raw.get("period_key") or "") or None
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    def _prepare_root(self) -> Path:
        root = Path(self._settings.backup_root)
        if not self._test_mode:
            validate_production_backup_root(root)
        return ensure_backup_root_writable(root)

    def _load_state(self) -> str | None:
        if not self._state_path.is_file():
            return None
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            key = str(raw.get("period_key") or "").strip()
            return key or None
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    def _save_state(self, period_key: str) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = RetentionState(
            period_key=period_key,
            ran_at=datetime.now().astimezone().isoformat(),
        )
        try:
            self._state_path.write_text(
                json.dumps(
                    {"period_key": payload.period_key, "ran_at": payload.ran_at},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Temizlik durumu yazılamadı: %s", exc)
