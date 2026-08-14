"""Yedekleme öncesi dry-run (ZIP oluşturmaz)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.db.models import BackupArea
from kurum_yedekleme.services.config_validation import (
    ValidationResult,
    validate_production_settings,
)
from kurum_yedekleme.services.disk_space import (
    DiskSpaceInfo,
    can_read_directory,
    disk_usage_for,
    estimate_source_bytes,
    is_e_drive,
)
from kurum_yedekleme.utils.formatting import format_bytes
from kurum_yedekleme.utils.paths import resolve_under_root
from kurum_yedekleme.utils.windows_paths import to_path

_MARGIN_BYTES = 64 * 1024 * 1024


@dataclass
class CheckItem:
    key: str
    label: str
    ok: bool
    detail: str = ""


@dataclass
class PreflightReport:
    checks: list[CheckItem] = field(default_factory=list)
    source_bytes: int = 0
    dest_free: Optional[DiskSpaceInfo] = None
    config: Optional[ValidationResult] = None

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def format_user_report(self) -> str:
        lines: list[str] = []
        for item in self.checks:
            mark = "✓" if item.ok else "✗"
            line = f"{mark} {item.label}"
            if item.detail:
                line += f" — {item.detail}"
            lines.append(line)
        if self.source_bytes:
            lines.append("")
            lines.append(
                f"Kaynak toplam boyut (tahmini): {format_bytes(self.source_bytes)}"
            )
        if self.dest_free is not None:
            lines.append(
                f"Hedef boş alan: {format_bytes(self.dest_free.free_bytes)}"
            )
        return "\n".join(lines)


def run_preflight(
    settings: AppSettings,
    areas: list[BackupArea],
    *,
    test_mode: bool = False,
) -> PreflightReport:
    report = PreflightReport()
    if not test_mode:
        config = validate_production_settings(settings)
        report.config = config
        report.checks.append(
            CheckItem(
                key="config",
                label="Config geçerli",
                ok=config.ok,
                detail=(
                    "tüm alanlar uygun" if config.ok else "; ".join(config.issues[:5])
                ),
            )
        )

    root = Path(settings.backup_root)
    if test_mode:
        drive_ok = True
        drive_detail = f"TEST MODE kök: {root}"
    else:
        drive_ok = is_e_drive(root)
        drive_detail = str(root)
    report.checks.append(
        CheckItem(
            key="e_drive",
            label="E: yedek kökü",
            ok=drive_ok,
            detail=drive_detail,
        )
    )

    enabled = [a for a in areas if a.is_active]
    source_ok_all = True
    source_details: list[str] = []
    total_source = 0
    for area in enabled:
        path = to_path(area.source_path)
        ok, detail = can_read_directory(path)
        source_details.append(f"{area.name}: {detail}")
        if not ok:
            source_ok_all = False
        else:
            total_source += estimate_source_bytes(path)
    if not enabled:
        source_ok_all = False
        source_details.append("etkin alan yok")
    report.source_bytes = total_source
    report.checks.append(
        CheckItem(
            key="source",
            label="Kaynaklar erişilebilir",
            ok=source_ok_all,
            detail="; ".join(source_details),
        )
    )

    write_ok = False
    write_detail = ""
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".kurum_yedekleme_probe.tmp"
        probe.write_bytes(b"ok")
        probe.unlink()
        write_ok = True
        write_detail = str(root)
    except OSError as exc:
        write_detail = str(exc)
    report.checks.append(
        CheckItem(
            key="dest_write",
            label="E:\\Yedekler yazılabilir",
            ok=write_ok,
            detail=write_detail,
        )
    )

    space_ok = write_ok
    space_detail = ""
    needed = total_source + _MARGIN_BYTES
    if write_ok:
        try:
            dest_info = disk_usage_for(root)
            report.dest_free = dest_info
            if dest_info.free_bytes < needed:
                space_ok = False
                space_detail = (
                    f"yetersiz (gerekli ~{format_bytes(needed)}, "
                    f"boş {format_bytes(dest_info.free_bytes)})"
                )
            else:
                space_detail = f"OK ({format_bytes(dest_info.free_bytes)})"
        except OSError as exc:
            space_ok = False
            space_detail = str(exc)
    report.checks.append(
        CheckItem(
            key="disk",
            label="Disk alanı yeterli",
            ok=space_ok,
            detail=space_detail,
        )
    )

    data_dir = resolve_under_root(settings.app.data_dir)
    report.checks.append(
        CheckItem(
            key="data",
            label="Veri klasörü",
            ok=True,
            detail=str(data_dir),
        )
    )
    return report
