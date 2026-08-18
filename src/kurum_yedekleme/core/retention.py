"""Eski yedek ZIP dosyalarını güvenli şekilde siler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from kurum_yedekleme.core.filenames import parse_backup_folder_date
from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("Retention")


@dataclass
class RetentionResult:
    deleted_files: int = 0
    deleted_bytes: int = 0
    removed_dirs: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _parse_date_folder(name: str) -> date | None:
    return parse_backup_folder_date(name)


def purge_old_backups(
    backup_root: Path,
    *,
    keep_days: int,
    now: datetime | None = None,
) -> RetentionResult:
    """
  Yapı: <backup_root>/<Alan>/<YYYY-MM-DD_HH-MM-SS>/*.zip
  (eski yedekler: <Alan>/<YYYY-MM-DD>/*.zip)

  keep_days'den eski tarih klasörlerindeki .zip dosyalarını siler.
  Kaynak klasörlere veya .tmp dosyalarına dokunmaz.
    """
    root = Path(backup_root)
    result = RetentionResult()
    if keep_days < 1:
        result.errors.append("keep_days en az 1 olmalıdır.")
        return result
    if not root.is_dir():
        logger.info("Temizlik atlandı — yedek kökü yok: %s", root)
        return result

    moment = now or datetime.now().astimezone()
    if moment.tzinfo is None:
        moment = moment.astimezone()
    cutoff = moment.date() - timedelta(days=int(keep_days))

    try:
        area_dirs = [p for p in root.iterdir() if p.is_dir()]
    except OSError as exc:
        result.errors.append(f"Yedek kökü okunamadı: {exc}")
        return result

    for area_dir in area_dirs:
        try:
            date_dirs = [p for p in area_dir.iterdir() if p.is_dir()]
        except OSError as exc:
            result.errors.append(f"{area_dir.name}: {exc}")
            continue
        for date_dir in date_dirs:
            folder_date = _parse_date_folder(date_dir.name)
            if folder_date is None:
                continue
            if folder_date >= cutoff:
                continue
            try:
                zip_files = [p for p in date_dir.iterdir() if p.is_file() and p.suffix.lower() == ".zip"]
            except OSError as exc:
                result.errors.append(f"{date_dir}: {exc}")
                continue
            for zip_path in zip_files:
                try:
                    size = zip_path.stat().st_size
                    zip_path.unlink()
                    result.deleted_files += 1
                    result.deleted_bytes += size
                    logger.info(
                        "Eski yedek silindi: %s (%s bayt)",
                        zip_path,
                        size,
                        operation="delete",
                    )
                except OSError as exc:
                    result.errors.append(f"{zip_path}: {exc}")
            try:
                remaining = list(date_dir.iterdir())
            except OSError as exc:
                result.errors.append(f"{date_dir}: {exc}")
                continue
            if not remaining:
                try:
                    date_dir.rmdir()
                    result.removed_dirs += 1
                    logger.info("Boş tarih klasörü silindi: %s", date_dir)
                except OSError as exc:
                    result.errors.append(f"{date_dir}: {exc}")

    if result.deleted_files:
        logger.info(
            "Temizlik tamamlandı: %s dosya, %s boş klasör",
            result.deleted_files,
            result.removed_dirs,
            operation="finish",
        )
    return result
