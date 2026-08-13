"""Eski çekirdek zamanlayıcı — ScheduleService'e yönlendirir."""

from __future__ import annotations

from kurum_yedekleme.services.schedule_service import ScheduleService

# Geriye dönük import uyumluluğu
BackupScheduler = ScheduleService

__all__ = ["BackupScheduler", "ScheduleService"]
