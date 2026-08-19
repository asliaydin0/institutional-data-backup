"""Eski yedek temizliği — yalnızca hedef ZIP dosyalarını siler."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.core.retention import RetentionResult, purge_old_backups
from kurum_yedekleme.services.disk_space import (
    ensure_backup_root_writable,
    validate_production_backup_root,
)
from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("Retention")

_STATE_FILE = "retention_state.json"


@dataclass(frozen=True)
class RetentionRunRecord:
    ran_at: datetime
    period_key: str | None
    status: str
    deleted_files: int
    deleted_bytes: int
    removed_dirs: int
    kept_files: int
    cutoff_date: str
    deleted_paths: list[str]
    errors: list[str]
    keep_days: int
    backup_root: str

    @property
    def status_label_tr(self) -> str:
        return {
            "SUCCESS": "Başarılı",
            "PARTIAL": "Kısmi",
            "FAILED": "Başarısız",
        }.get(self.status, self.status)

    @property
    def ok(self) -> bool:
        return self.status == "SUCCESS"


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
        previous = self._settings
        self._settings = settings
        if self._plan_changed(previous, settings):
            self.release_period_lock()
            logger.info(
                "Temizlik planı değişti; bugünkü tekrar çalıştırma serbest "
                "(saat/saklama/kök güncellendi)."
            )

    def run_if_due(self, period_key: str) -> RetentionResult | None:
        if not self._settings.retention.enabled:
            return None
        if self._load_state() == period_key:
            logger.info(
                "Temizlik atlandı: bu dönem zaten çalıştı (%s). "
                "Yeni bir deneme için saati veya saklama süresini değiştirin.",
                period_key,
            )
            return None
        result = self.run_now(period_key=period_key)
        return result

    def run_now(self, period_key: str | None = None) -> RetentionResult:
        retention = self._settings.retention
        root = self._prepare_root()
        logger.info(
            "Eski yedek temizliği başlıyor (keep_days=%s, kök=%s)",
            retention.keep_days,
            root,
            operation="start",
        )
        try:
            result = purge_old_backups(
                root,
                keep_days=retention.keep_days,
            )
        except Exception as exc:
            logger.exception("Temizlik beklenmeyen hata")
            result = RetentionResult(errors=[str(exc)])
        self._save_run(period_key, result, root)
        if result.errors:
            logger.warning(
                "Temizlik tamamlandı ancak %s hata var: %s dosya silindi",
                len(result.errors),
                result.deleted_files,
                operation="finish",
            )
        else:
            logger.info(
                "Temizlik başarılı: %s dosya silindi, %s boş klasör, "
                "%s ZIP korundu (saklama %s gün)",
                result.deleted_files,
                result.removed_dirs,
                result.kept_files,
                retention.keep_days,
                operation="finish",
            )
        return result

    def last_run(self) -> RetentionRunRecord | None:
        raw = self._read_state_raw()
        if not raw:
            return None
        ran_at_raw = str(raw.get("ran_at") or "").strip()
        if not ran_at_raw:
            return None
        try:
            ran_at = datetime.fromisoformat(ran_at_raw)
        except ValueError:
            return None
        paths = raw.get("deleted_paths") or []
        errors = raw.get("errors") or []
        return RetentionRunRecord(
            ran_at=ran_at,
            period_key=str(raw.get("period_key") or "") or None,
            status=str(raw.get("status") or "SUCCESS"),
            deleted_files=int(raw.get("deleted_files") or 0),
            deleted_bytes=int(raw.get("deleted_bytes") or 0),
            removed_dirs=int(raw.get("removed_dirs") or 0),
            kept_files=int(raw.get("kept_files") or 0),
            cutoff_date=str(raw.get("cutoff_date") or ""),
            deleted_paths=[str(p) for p in paths],
            errors=[str(e) for e in errors],
            keep_days=int(raw.get("keep_days") or 0),
            backup_root=str(raw.get("backup_root") or ""),
        )

    def last_period_key(self) -> str | None:
        raw = self._read_state_raw()
        if not raw:
            return None
        if str(raw.get("status") or "") == "FAILED" and not raw.get("period_key"):
            return None
        key = str(raw.get("period_key") or "").strip()
        return key or None

    def release_period_lock(self) -> None:
        """Aynı gün/hafta içinde plan değişince tekrar çalışmaya izin ver."""
        raw = self._read_state_raw()
        if not raw or not raw.get("period_key"):
            return
        raw["period_key"] = None
        try:
            self._state_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Temizlik dönem kilidi kaldırılamadı: %s", exc)

    @staticmethod
    def _plan_changed(previous: AppSettings, current: AppSettings) -> bool:
        old = previous.retention
        new = current.retention
        return (
            previous.backup_root != current.backup_root
            or old.enabled != new.enabled
            or old.keep_days != new.keep_days
            or old.frequency != new.frequency
            or old.time != new.time
            or old.weekday != new.weekday
            or old.day_of_month != new.day_of_month
        )

    def _prepare_root(self) -> Path:
        root = Path(self._settings.backup_root)
        if not self._test_mode:
            validate_production_backup_root(root)
        return ensure_backup_root_writable(root)

    def _load_state(self) -> str | None:
        return self.last_period_key()

    def _read_state_raw(self) -> dict | None:
        if not self._state_path.is_file():
            return None
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        if not isinstance(raw, dict):
            return None
        return raw

    def _save_run(
        self,
        period_key: str | None,
        result: RetentionResult,
        root: Path,
    ) -> None:
        if result.errors and not result.deleted_files:
            status = "FAILED"
            saved_period = None
        elif result.errors:
            status = "PARTIAL"
            saved_period = period_key
        else:
            status = "SUCCESS"
            saved_period = period_key
        payload = {
            "period_key": saved_period,
            "ran_at": datetime.now().astimezone().isoformat(),
            "status": status,
            "deleted_files": result.deleted_files,
            "deleted_bytes": result.deleted_bytes,
            "removed_dirs": result.removed_dirs,
            "kept_files": result.kept_files,
            "cutoff_date": result.cutoff_date,
            "deleted_paths": result.deleted_paths,
            "errors": result.errors[:20],
            "keep_days": self._settings.retention.keep_days,
            "backup_root": str(root),
        }
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._state_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Temizlik durumu yazılamadı: %s", exc)
