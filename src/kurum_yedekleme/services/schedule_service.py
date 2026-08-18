"""GUI'den bağımsız otomatik yedekleme zamanlayıcısı (Windows Service içinde)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from kurum_yedekleme.config.periodic import (
    PeriodicTiming,
    is_period_due,
    next_period_run_at,
    period_slot_passed,
)
from kurum_yedekleme.config.schema import ScheduleConfig
from kurum_yedekleme.config.writer import validate_schedule_settings
from kurum_yedekleme.core.lock import BackupInProgressError
from kurum_yedekleme.db.models import BackupArea, BackupType
from kurum_yedekleme.services.area_service import AreaService
from kurum_yedekleme.services.backup_manager import BackupManager, JobResult
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("BackupScheduler")

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class MissedBackupInfo:
    scheduled_time: str
    frequency: str
    pending_area_count: int
    message: str = "Bu dönemin otomatik yedeklemesi henüz yapılmadı."


class ScheduleService:
    """
    Günlük / haftalık / aylık otomatik yedekleme.

    Üretimde yalnızca Windows Service bu servisi start() eder; GUI
    zamanlayıcı çalıştırmaz. TEST MODE GUI oturumunda pencere açıkken
    start() edilir (servis kurulumu yoktur).
    """

    def __init__(
        self,
        schedule: ScheduleConfig,
        backup_manager: BackupManager,
        area_service: AreaService,
        history_service: HistoryService,
        *,
        poll_interval_seconds: float = 20.0,
        clock: Optional[Clock] = None,
    ) -> None:
        self._schedule = schedule
        self._backups = backup_manager
        self._areas = area_service
        self._history = history_service
        self._poll_interval = max(1.0, float(poll_interval_seconds))
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._stop_event = threading.Event()
        self._idle = threading.Event()
        self._pending_missed_check = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._last_job: Optional[JobResult] = None
        self._fired_minute: Optional[tuple[int, int, int, int, int]] = None

    @property
    def schedule(self) -> ScheduleConfig:
        with self._lock:
            return self._schedule

    @property
    def last_job(self) -> Optional[JobResult]:
        return self._last_job

    def update_schedule(self, schedule: ScheduleConfig) -> None:
        validated = validate_schedule_settings(schedule)
        with self._lock:
            self._schedule = validated
            self._pending_missed_check = True
            self._fired_minute = None
        self._idle.set()
        logger.info(
            "Zamanlayıcı güncellendi: enabled=%s freq=%s time=%s",
            validated.enabled,
            validated.frequency,
            validated.time,
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
                name="BackupScheduleService",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "Zamanlayıcı başlatıldı (enabled=%s, freq=%s, time=%s, poll=%.0fs)",
                self._schedule.enabled,
                self._schedule.frequency,
                self._schedule.time,
                self._poll_interval,
            )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self._idle.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        logger.info("Zamanlayıcı durduruldu.")

    def tick(self, now: Optional[datetime] = None) -> bool:
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()

        with self._lock:
            schedule = self._schedule

        if not schedule.enabled:
            return False
        timing = self._timing(schedule)
        if not is_period_due(moment, timing):
            return False

        minute_key = (
            moment.year,
            moment.month,
            moment.day,
            moment.hour,
            moment.minute,
        )
        with self._lock:
            if self._fired_minute == minute_key:
                return False
            self._fired_minute = minute_key

        return self.run_automatic_if_needed(now=moment)

    def check_missed_backup(
        self, now: Optional[datetime] = None
    ) -> Optional[MissedBackupInfo]:
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()

        with self._lock:
            schedule = self._schedule
        if not schedule.enabled:
            return None

        timing = self._timing(schedule)
        if not period_slot_passed(moment, timing):
            return None

        pending = self._pending_automatic_areas(now=moment, schedule=schedule)
        if not pending:
            return None
        return MissedBackupInfo(
            scheduled_time=schedule.time,
            frequency=schedule.frequency,
            pending_area_count=len(pending),
        )

    def run_missed_if_needed(self, now: Optional[datetime] = None) -> bool:
        info = self.check_missed_backup(now=now)
        if info is None:
            return False
        logger.info(
            "Kaçırılmış otomatik yedek tespit edildi (%s alan, %s). Başlatılıyor.",
            info.pending_area_count,
            info.frequency,
            operation="start",
        )
        return self.run_automatic_if_needed(now=now)

    def run_automatic_if_needed(self, now: Optional[datetime] = None) -> bool:
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()

        with self._lock:
            schedule = self._schedule

        pending = self._pending_automatic_areas(now=moment, schedule=schedule)
        if not pending:
            logger.debug("Otomatik yedek: bekleyen alan yok.")
            return False
        if self._backups.is_busy:
            logger.info(
                "Zamanı geldi ancak başka bir yedekleme sürüyor; atlanıyor."
            )
            return False
        logger.info(
            "Otomatik yedekleme başlıyor (%s alan, %s)",
            len(pending),
            schedule.frequency,
            operation="start",
        )
        try:
            self._last_job = self._backups.run(
                pending,
                backup_type=BackupType.AUTOMATIC,
                skip_successful_automatic_in_period=True,
                schedule_frequency=schedule.frequency,
            )
        except BackupInProgressError:
            logger.warning("Otomatik yedekleme: eşzamanlı iş engellendi.")
            return False
        except Exception:
            logger.exception("Otomatik yedekleme hatası")
            return False
        return True

    def next_run_at(self, now: Optional[datetime] = None) -> Optional[datetime]:
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()
        with self._lock:
            schedule = self._schedule
        if not schedule.enabled:
            return None
        return next_period_run_at(moment, self._timing(schedule))

    def _pending_automatic_areas(
        self,
        *,
        now: datetime,
        schedule: ScheduleConfig,
    ) -> list[BackupArea]:
        pending: list[BackupArea] = []
        for area in self._areas.list_enabled():
            if area.id is None:
                pending.append(area)
                continue
            if not self._history.has_successful_automatic_in_period(
                area.id,
                schedule.frequency,
                now=now,
            ):
                pending.append(area)
        return pending

    def _consume_missed_check(self) -> bool:
        with self._lock:
            pending = self._pending_missed_check
            self._pending_missed_check = False
            return pending

    def _loop(self) -> None:
        try:
            self.run_missed_if_needed()
        except Exception:
            logger.exception("Açılış missed-backup kontrolü hatası")
        while not self._stop_event.is_set():
            if self._consume_missed_check():
                try:
                    self.run_missed_if_needed()
                except Exception:
                    logger.exception("Ayar sonrası missed-backup kontrolü hatası")
            try:
                self.tick()
            except Exception:
                logger.exception("Zamanlayıcı tick hatası")
            self._idle.wait(self._poll_interval)
            self._idle.clear()

    @staticmethod
    def _timing(schedule: ScheduleConfig) -> PeriodicTiming:
        return PeriodicTiming(
            frequency=schedule.frequency,
            time=schedule.time,
            weekday=schedule.weekday,
            day_of_month=schedule.day_of_month,
        )
