"""Production yapılandırma doğrulama."""

from __future__ import annotations

from dataclasses import dataclass, field

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.config.writer import validate_schedule_time
from kurum_yedekleme.services.disk_space import (
    BackupRootError,
    validate_production_backup_root,
)


class ProductionConfigError(ValueError):
    def __init__(self, missing_fields: list[str], *, detail: str = "") -> None:
        self.missing_fields = list(missing_fields)
        header = "Production yapılandırması tamamlanmamış."
        lines = [header, ""]
        if self.missing_fields:
            lines.append("Eksik veya geçersiz alanlar:")
            for item in self.missing_fields:
                lines.append(f"  • {item}")
        if detail:
            lines.append("")
            lines.append(detail)
        super().__init__("\n".join(lines))


@dataclass
class ValidationResult:
    ok: bool
    issues: list[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ProductionConfigError(self.issues)


def validate_production_settings(settings: AppSettings) -> ValidationResult:
    issues: list[str] = []
    if not str(settings.backup_root).strip():
        issues.append("backup_root — boş")
    else:
        try:
            validate_production_backup_root(settings.backup_root)
        except BackupRootError as exc:
            issues.append(f"backup_root — {exc}")

    try:
        validate_schedule_time(settings.schedule.time)
    except Exception as exc:  # noqa: BLE001
        issues.append(
            f"backup_time — geçersiz saat: {settings.schedule.time!r} ({exc})"
        )

    if settings.retry.max_attempts < 1:
        issues.append(
            f"retry_count — en az 1 olmalı (şu an: {settings.retry.max_attempts})"
        )
    level = settings.zip.compresslevel
    if level < 0 or level > 9:
        issues.append(f"compression_level — 0–9 arası olmalı (şu an: {level})")

    return ValidationResult(ok=not issues, issues=issues)
