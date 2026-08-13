"""Kurumsal bileşen logları (modül + işlem alanları)."""

from __future__ import annotations

import logging
from typing import Any, MutableMapping

# Logger adı → kısa bileşen adı (GUI / dosya satırında görünür)
COMPONENT_ALIASES: dict[str, str] = {
    "kurum_yedekleme.app": "App",
    "kurum_yedekleme.core.backup_engine": "BackupEngine",
    "kurum_yedekleme.core.zipper": "ZipEngine",
    "kurum_yedekleme.core.transfer": "TransferService",
    "kurum_yedekleme.core.integrity": "IntegrityService",
    "kurum_yedekleme.core.retry": "Retry",
    "kurum_yedekleme.services.schedule_service": "BackupScheduler",
    "kurum_yedekleme.services.backup_service": "BackupService",
    "kurum_yedekleme.services.history_service": "HistoryService",
    "kurum_yedekleme.services.autostart": "Autostart",
    "kurum_yedekleme.utils.logging_setup": "Logging",
}


def component_from_logger_name(name: str) -> str:
    """Logger adından kısa bileşen adı üretir."""
    if name in COMPONENT_ALIASES:
        return COMPONENT_ALIASES[name]
    for prefix, alias in COMPONENT_ALIASES.items():
        if name.startswith(prefix + ".") or name == prefix:
            return alias
    # kurum_yedekleme.foo.bar → Bar
    tail = name.rsplit(".", 1)[-1]
    parts = [p for p in tail.replace("-", "_").split("_") if p]
    if not parts:
        return name or "App"
    return "".join(p[:1].upper() + p[1:] for p in parts)


class ComponentLoggerAdapter(logging.LoggerAdapter):
    """
    extra: component, operation

    Kullanım:
        log = get_logger("BackupEngine")
        log.info("Kaynak taranıyor", operation="scan")
    """

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        extra = dict(kwargs.get("extra") or {})
        extra.setdefault("component", self.extra.get("component", "App"))
        operation = kwargs.pop("operation", None)
        if operation is not None:
            extra["operation"] = str(operation)
        else:
            extra.setdefault("operation", self.extra.get("operation", "-"))
        kwargs["extra"] = extra
        return msg, kwargs

    def with_operation(self, operation: str) -> "ComponentLoggerAdapter":
        """Aynı bileşende varsayılan işlem adı ile yeni adapter."""
        return ComponentLoggerAdapter(
            self.logger,
            {
                "component": self.extra.get("component", "App"),
                "operation": operation,
            },
        )


def get_logger(
    component: str,
    *,
    operation: str = "-",
) -> ComponentLoggerAdapter:
    """Kurumsal bileşen logger'ı (adı doğrudan satırda görünür)."""
    base = logging.getLogger(f"kurum.{component}")
    return ComponentLoggerAdapter(
        base,
        {"component": component, "operation": operation},
    )


def ensure_record_fields(record: logging.LogRecord) -> None:
    """Formatter için component / operation alanlarını doldurur."""
    if not getattr(record, "component", None):
        record.component = component_from_logger_name(record.name)  # type: ignore[attr-defined]
    if not getattr(record, "operation", None):
        record.operation = "-"  # type: ignore[attr-defined]
