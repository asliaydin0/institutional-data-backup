"""Production yapılandırma doğrulama — PLACEHOLDER / eksik alan engeli."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kurum_yedekleme.config.schema import AppSettings
from kurum_yedekleme.config.writer import validate_schedule_time

# Açık placeholder / örnek kalıplar (büyük/küçük harf duyarsız)
_PLACEHOLDER_PATTERNS = (
    r"placeholder",
    r"\byol\b",
    r"kaynak_klasoru",
    r"kaynak_klasörü",
    r"\\\\sunucu\\",
    r"//sunucu/",
    r"ornek-sunucu",
    r"örnek-sunucu",
    r"example\.com",
    r"changeme",
    r"todo",
    r"FIXME",
    r"C:/YOL/",
    r"C:\\YOL\\",
)


class ProductionConfigError(ValueError):
    """Production yapılandırması eksik veya geçersiz."""

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


def _looks_placeholder(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return True
    return False


def validate_production_settings(settings: AppSettings) -> ValidationResult:
    """
    Production yedekleme için config alanlarını doğrular.

    TEST MODE yollarını kabul etmez; PLACEHOLDER / boş değerleri reddeder.
    """
    issues: list[str] = []

    enabled = [s for s in settings.sources if s.enabled]
    if not enabled:
        issues.append("source_paths — etkin kaynak klasör yok")
    else:
        for src in enabled:
            if _looks_placeholder(src.path):
                issues.append(
                    f"source_paths ({src.id}) — boş veya PLACEHOLDER: {src.path!r}"
                )

    dest = (settings.destination.unc_path or "").strip()
    if _looks_placeholder(dest):
        issues.append(f"destination_path — boş veya PLACEHOLDER: {dest!r}")
    dest_l = dest.lower().replace("\\", "/")
    if (
        "test_data" in dest_l
        or "test_server" in dest_l
        or "kurumyedekleme_test" in dest_l
    ):
        issues.append(
            f"destination_path — test yolu production için uygun değil: {dest!r}"
        )

    temp = (settings.app.temp_dir or "").strip()
    if _looks_placeholder(temp):
        issues.append(f"temp_path — boş veya PLACEHOLDER: {temp!r}")
    # Test/geçici yollar production'da istenmez
    temp_l = temp.lower().replace("\\", "/")
    if "test_data" in temp_l or "kurumyedekleme_test" in temp_l:
        issues.append(
            "temp_path — test yolu (test_data / KurumYedekleme_Test) "
            "production için uygun değil"
        )

    for src in enabled:
        src_l = (src.path or "").lower().replace("\\", "/")
        if "test_data" in src_l or "kurumyedekleme_test" in src_l:
            issues.append(
                f"source_paths ({src.id}) — test yolu production için uygun değil: "
                f"{src.path!r}"
            )

    try:
        validate_schedule_time(settings.schedule.time)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"backup_time — geçersiz saat: {settings.schedule.time!r} ({exc})")

    if settings.retry.max_attempts < 1:
        issues.append(
            f"retry_count — en az 1 olmalı (şu an: {settings.retry.max_attempts})"
        )
    if settings.retry.initial_delay_seconds < 0:
        issues.append(
            f"retry_delay — negatif olamaz (şu an: {settings.retry.initial_delay_seconds})"
        )
    level = settings.zip.compresslevel
    if level < 0 or level > 9:
        issues.append(f"compression_level — 0–9 arası olmalı (şu an: {level})")

    return ValidationResult(ok=not issues, issues=issues)


def format_validation_message(result: ValidationResult) -> str:
    if result.ok:
        return "Config geçerli."
    try:
        raise ProductionConfigError(result.issues)
    except ProductionConfigError as exc:
        return str(exc)
