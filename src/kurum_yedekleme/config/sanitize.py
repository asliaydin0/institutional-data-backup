"""Eski yapılandırma anahtarlarını tespit etme ve temizleme."""

from __future__ import annotations

from typing import Any

OBSOLETE_ROOT_KEYS = (
    "sources",
    "destination",
    "integrity",
    "security",
    "autostart",
)

OBSOLETE_APP_KEYS = ("temp_dir",)
OBSOLETE_SCHEDULE_KEYS = ("days",)


def find_obsolete_config_keys(raw: dict[str, Any]) -> list[str]:
    """Yapılandırmada kullanılmayan eski anahtarları listeler."""
    found: list[str] = []
    for key in OBSOLETE_ROOT_KEYS:
        if key in raw:
            found.append(key)
    app = raw.get("app")
    if isinstance(app, dict):
        for key in OBSOLETE_APP_KEYS:
            if key in app:
                found.append(f"app.{key}")
    schedule = raw.get("schedule")
    if isinstance(schedule, dict):
        for key in OBSOLETE_SCHEDULE_KEYS:
            if key in schedule:
                found.append(f"schedule.{key}")
    return found


def sanitize_config_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Eski anahtarları kaldırır; geçerli ayarları korur."""
    cleaned = dict(raw)
    for key in OBSOLETE_ROOT_KEYS:
        cleaned.pop(key, None)
    app = cleaned.get("app")
    if isinstance(app, dict):
        app = dict(app)
        for key in OBSOLETE_APP_KEYS:
            app.pop(key, None)
        cleaned["app"] = app
    schedule = cleaned.get("schedule")
    if isinstance(schedule, dict):
        schedule = dict(schedule)
        for key in OBSOLETE_SCHEDULE_KEYS:
            schedule.pop(key, None)
        cleaned["schedule"] = schedule
    retry = cleaned.get("retry")
    if isinstance(retry, dict):
        retry = dict(retry)
        retry.pop("count", None)
        retry.pop("delay", None)
        cleaned["retry"] = retry
    return cleaned
