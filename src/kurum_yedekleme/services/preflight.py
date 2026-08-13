"""Yedekleme öncesi dry-run / preflight (dosya ZIP'lemez)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.services.config_validation import (
    ValidationResult,
    validate_production_settings,
)
from kurum_yedekleme.services.disk_space import (
    DiskSpaceInfo,
    disk_usage_for,
    estimate_source_bytes,
)
from kurum_yedekleme.utils.formatting import format_bytes
from kurum_yedekleme.utils.paths import resolve_under_root
from kurum_yedekleme.utils.windows_paths import is_path_accessible, to_path

# Temp + hedef için kaynak boyutuna ek güvenlik payı
_MARGIN_BYTES = 64 * 1024 * 1024  # 64 MiB


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
    temp_free: Optional[DiskSpaceInfo] = None
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
            lines.append(f"Kaynak toplam boyut (tahmini): {format_bytes(self.source_bytes)}")
        if self.temp_free is not None:
            lines.append(
                f"Temp boş alan: {format_bytes(self.temp_free.free_bytes)}"
            )
        if self.dest_free is not None:
            lines.append(
                f"Hedef boş alan: {format_bytes(self.dest_free.free_bytes)}"
            )
        needed = self.source_bytes + _MARGIN_BYTES
        if self.source_bytes:
            lines.append(f"Gerekli alan (yaklaşık, pay dahil): {format_bytes(needed)}")
        return "\n".join(lines)


def _can_read_dir(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "klasör yok"
    if not path.is_dir():
        return False, "klasör değil"
    try:
        next(path.iterdir(), None)
        # En az bir dosyayı okumayı dene (varsa)
        for child in path.rglob("*"):
            if child.is_file() and not child.is_symlink():
                with child.open("rb") as handle:
                    handle.read(1)
                break
        return True, "okunabilir"
    except PermissionError:
        return False, "okuma izni yok"
    except OSError as exc:
        return False, str(exc)


def probe_destination_writable(dest_root: Path) -> tuple[bool, str]:
    """
    Hedefte küçük test dosyası oluşturup siler (gerçek yedek yok).

    Returns:
        (ok, mesaj)
    """
    root = to_path(dest_root)
    if not is_path_accessible(root):
        return False, "hedef erişilemiyor veya yok"
    if not root.is_dir():
        return False, "hedef bir klasör değil"

    probe_dir = root / ".kurum_yedekleme_probe"
    name = f"write_test_{uuid.uuid4().hex}.tmp"
    probe_file = probe_dir / name
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_file.write_bytes(b"kurum-yedekleme-probe\n")
        data = probe_file.read_bytes()
        if data != b"kurum-yedekleme-probe\n":
            return False, "yazılan içerik doğrulanamadı"
        probe_file.unlink()
        # Boş probe klasörünü kaldırmayı dene
        try:
            probe_dir.rmdir()
        except OSError:
            pass
        return True, "yazma/silme başarılı"
    except PermissionError:
        return False, "yazma izni yok"
    except OSError as exc:
        return False, f"yazma testi başarısız: {exc}"
    finally:
        try:
            if probe_file.exists():
                probe_file.unlink()
        except OSError:
            pass


def run_preflight(
    settings: AppSettings,
    *,
    require_production_config: bool = True,
    min_free_multiplier: float = 1.0,
) -> PreflightReport:
    """
    Yapılandırma dry-run: ZIP / gerçek yedek oluşturmaz.
    """
    report = PreflightReport()

    if require_production_config:
        config = validate_production_settings(settings)
        report.config = config
        report.checks.append(
            CheckItem(
                key="config",
                label="Config geçerli",
                ok=config.ok,
                detail=("tüm alanlar uygun" if config.ok else "; ".join(config.issues[:5])),
            )
        )
        if not config.ok:
            # Config geçersizse diğer kontroller yanıltıcı olabilir; yine de dene
            pass

    enabled = [s for s in settings.sources if s.enabled]
    source_ok_all = True
    source_details: list[str] = []
    total_source = 0
    for src in enabled:
        path = to_path(src.path)
        ok, detail = _can_read_dir(path)
        source_details.append(f"{src.id}: {detail}")
        if not ok:
            source_ok_all = False
        else:
            total_source += estimate_source_bytes(path)
    if not enabled:
        source_ok_all = False
        source_details.append("etkin kaynak yok")
    report.source_bytes = total_source
    report.checks.append(
        CheckItem(
            key="source",
            label="Kaynak erişilebilir",
            ok=source_ok_all,
            detail="; ".join(source_details),
        )
    )
    report.checks.append(
        CheckItem(
            key="source_read",
            label="Kaynak okuma izni var",
            ok=source_ok_all,
            detail="salt okuma denemesi",
        )
    )

    dest = to_path(settings.destination.unc_path)
    dest_access = is_path_accessible(dest) and dest.is_dir()
    report.checks.append(
        CheckItem(
            key="dest_access",
            label="Sunucu erişilebilir",
            ok=dest_access,
            detail=str(dest),
        )
    )

    write_ok, write_detail = (False, "atlandı")
    if dest_access:
        write_ok, write_detail = probe_destination_writable(dest)
    report.checks.append(
        CheckItem(
            key="dest_write",
            label="Yazma izni var",
            ok=write_ok,
            detail=write_detail,
        )
    )

    temp = resolve_under_root(settings.app.temp_dir)
    temp_ok = False
    temp_detail = ""
    try:
        temp.mkdir(parents=True, exist_ok=True)
        probe = temp / f".write_probe_{os.getpid()}.tmp"
        probe.write_bytes(b"ok")
        probe.unlink()
        temp_ok = True
        temp_detail = str(temp)
    except OSError as exc:
        temp_detail = str(exc)
    report.checks.append(
        CheckItem(
            key="temp",
            label="Temp yazılabilir",
            ok=temp_ok,
            detail=temp_detail,
        )
    )

    needed = int(total_source * min_free_multiplier) + _MARGIN_BYTES
    space_ok = True
    space_parts: list[str] = []
    try:
        temp_info = disk_usage_for(temp)
        report.temp_free = temp_info
        if temp_info.free_bytes < needed:
            space_ok = False
            space_parts.append(
                f"temp yetersiz (gerekli ~{format_bytes(needed)}, "
                f"boş {format_bytes(temp_info.free_bytes)})"
            )
        else:
            space_parts.append(f"temp OK ({format_bytes(temp_info.free_bytes)})")
    except OSError as exc:
        space_ok = False
        space_parts.append(f"temp disk okunamadı: {exc}")

    if dest_access:
        try:
            dest_info = disk_usage_for(dest)
            report.dest_free = dest_info
            if dest_info.free_bytes < needed:
                space_ok = False
                space_parts.append(
                    f"hedef yetersiz (gerekli ~{format_bytes(needed)}, "
                    f"boş {format_bytes(dest_info.free_bytes)})"
                )
            else:
                space_parts.append(f"hedef OK ({format_bytes(dest_info.free_bytes)})")
        except OSError as exc:
            space_ok = False
            space_parts.append(f"hedef disk okunamadı: {exc}")

    report.checks.append(
        CheckItem(
            key="disk",
            label="Temp alanı yeterli",
            ok=space_ok and temp_ok,
            detail="; ".join(space_parts),
        )
    )

    return report


class InsufficientDiskSpaceError(RuntimeError):
    """Yedekleme için disk alanı yetersiz."""


def assert_disk_space_for_backup(
    settings: AppSettings,
    *,
    source_bytes: Optional[int] = None,
) -> None:
    """Backup öncesi temp + hedef boş alan kontrolü."""
    enabled = [s for s in settings.sources if s.enabled]
    total = source_bytes
    if total is None:
        total = 0
        for src in enabled:
            total += estimate_source_bytes(to_path(src.path))
    needed = total + _MARGIN_BYTES
    temp = resolve_under_root(settings.app.temp_dir)
    dest = to_path(settings.destination.unc_path)

    problems: list[str] = []
    try:
        temp_info = disk_usage_for(temp)
        if temp_info.free_bytes < needed:
            problems.append(
                f"Temp: gerekli {format_bytes(needed)}, "
                f"mevcut {format_bytes(temp_info.free_bytes)} ({temp})"
            )
    except OSError as exc:
        problems.append(f"Temp disk alanı okunamadı: {exc}")

    try:
        dest_info = disk_usage_for(dest)
        if dest_info.free_bytes < needed:
            problems.append(
                f"Sunucu: gerekli {format_bytes(needed)}, "
                f"mevcut {format_bytes(dest_info.free_bytes)} ({dest})"
            )
    except OSError as exc:
        problems.append(f"Sunucu disk alanı okunamadı: {exc}")

    if problems:
        raise InsufficientDiskSpaceError(
            "Yeterli disk alanı yok; yedekleme başlatılmadı.\n\n"
            + "\n".join(problems)
            + f"\n\nKaynak toplam (tahmini): {format_bytes(total)}"
        )
