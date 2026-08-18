"""Eski yedek temizliği zamanlayıcısı (Windows Service içinde)."""

from __future__ import annotations

import threading
from datetime import datetime, time, timedelta
from typing import Callable, Optional

from kurum_yedekleme.config.retention_schema import RetentionConfig
from kurum_yedekleme.config.writer import validate_retention_settings, validate_schedule_time
from kurum_yedekleme.core.lock import BackupInProgressError
from kurum_yedekleme.services.backup_manager import BackupManager
from kurum_yedekleme.services.retention_service import RetentionService
from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("RetentionScheduler")

Clock = Callable[[], datetime]


class RetentionScheduler:
    def __init__(
        self,
        retention: RetentionConfig,
        retention_service: RetentionService,
        backup_manager: BackupManager,
        *,
        poll_interval_seconds: float = 20.0,
        clock: Optional[Clock] = None,
    ) -> None:
        self._retention = retention
        self._service = retention_service
        self._backups = backup_manager
        self._poll_interval = max(1.0, float(poll_interval_seconds))
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._stop_event = threading.Event()
        self._idle = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._fired_minute: Optional[tuple[int, int, int, int, int]] = None

    @property
    def retention(self) -> RetentionConfig:
        with self._lock:
            return self._retention

    def update_retention(self, retention: RetentionConfig) -> None:
        validate_retention_settings(retention)
        with self._lock:
            self._retention = retention
            self._fired_minute = None
        self._idle.set()
        logger.info(
            "Temizlik zamanlayıcısı güncellendi: enabled=%s freq=%s time=%s keep=%s gün",
            retention.enabled,
            retention.frequency,
            retention.time,
            retention.keep_days,
        )

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._idle.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="RetentionScheduler",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "Temizlik zamanlayıcısı başlatıldı (enabled=%s, freq=%s, time=%s)",
                self._retention.enabled,
                self._retention.frequency,
                self._retention.time,
            )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self._idle.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        logger.info("Temizlik zamanlayıcısı durduruldu.")

    def tick(self, now: Optional[datetime] = None) -> bool:
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()
        with self._lock:
            retention = self._retention
        if not retention.enabled:
            return False
        if not self._is_due(moment, retention):
            return False
        minute_key = (
            moment.year,
            moment.month,
            moment.day,
            moment.hour,
            moment.minute,
        )
        if self._fired_minute == minute_key:
            return False
        self._fired_minute = minute_key
        return self._run_for_period(moment, retention)

    def run_missed_if_needed(self, now: Optional[datetime] = None) -> bool:
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()
        with self._lock:
            retention = self._retention
        if not retention.enabled:
            return False
        period_key = self._period_key(moment, retention)
        if self._service.last_period_key() == period_key:
            return False
        if not self._period_window_started(moment, retention):
            return False
        logger.info(
            "Kaçırılmış temizlik tespit edildi (dönem=%s). Başlatılıyor.",
            period_key,
            operation="start",
        )
        return self._run_for_period(moment, retention)

    def _run_for_period(self, moment: datetime, retention: RetentionConfig) -> bool:
        if self._backups.is_busy:
            logger.info("Yedekleme sürüyor; temizlik ertelendi.")
            return False
        period_key = self._period_key(moment, retention)
        try:
            result = self._service.run_if_due(period_key)
        except BackupInProgressError:
            logger.warning("Temizlik: eşzamanlı yedekleme engeli.")
            return False
        except Exception:
            logger.exception("Temizlik hatası")
            return False
        if result is None:
            return False
        logger.info(
            "Temizlik bitti: %s dosya silindi",
            result.deleted_files,
            operation="finish",
        )
        return True

    def _loop(self) -> None:
        try:
            self.run_missed_if_needed()
        except Exception:
            logger.exception("Açılış missed-retention kontrolü hatası")
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Temizlik zamanlayıcı tick hatası")
            self._idle.wait(self._poll_interval)
            self._idle.clear()

    @staticmethod
    def _parse_hhmm(value: str) -> time:
        hour_s, minute_s = validate_schedule_time(value).split(":")
        return time(hour=int(hour_s), minute=int(minute_s))

    def _is_due(self, moment: datetime, retention: RetentionConfig) -> bool:
        target = self._parse_hhmm(retention.time)
        if moment.hour != target.hour or moment.minute != target.minute:
            return False
        freq = retention.frequency
        if freq == "daily":
            return True
        if freq == "weekly":
            return moment.weekday() == int(retention.weekday)
        if freq == "monthly":
            return moment.day == int(retention.day_of_month)
        return False

    def _period_window_started(self, moment: datetime, retention: RetentionConfig) -> bool:
        target = self._parse_hhmm(retention.time)
        scheduled = datetime.combine(moment.date(), target, tzinfo=moment.tzinfo)
        if moment < scheduled:
            return False
        freq = retention.frequency
        if freq == "daily":
            return True
        if freq == "weekly":
            return moment.weekday() == int(retention.weekday)
        if freq == "monthly":
            return moment.day >= int(retention.day_of_month)
        return False

    @staticmethod
    def _period_key(moment: datetime, retention: RetentionConfig) -> str:
        freq = retention.frequency
        if freq == "daily":
            return moment.strftime("%Y-%m-%d")
        if freq == "weekly":
            year, week, _ = moment.isocalendar()
            return f"{year}-W{week:02d}"
        if freq == "monthly":
            return moment.strftime("%Y-%m")
        return moment.strftime("%Y-%m-%d")

    def next_run_at(self, now: Optional[datetime] = None) -> Optional[datetime]:
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()
        with self._lock:
            retention = self._retention
        if not retention.enabled:
            return None
        target = self._parse_hhmm(retention.time)
        candidate = datetime.combine(moment.date(), target, tzinfo=moment.tzinfo)
        for _ in range(400):
            if candidate >= moment and self._matches_frequency(candidate, retention):
                return candidate
            candidate += timedelta(days=1)
        return None

    def _matches_frequency(self, moment: datetime, retention: RetentionConfig) -> bool:
        if retention.frequency == "daily":
            return True
        if retention.frequency == "weekly":
            return moment.weekday() == int(retention.weekday)
        if retention.frequency == "monthly":
            return moment.day == int(retention.day_of_month)
        return False
