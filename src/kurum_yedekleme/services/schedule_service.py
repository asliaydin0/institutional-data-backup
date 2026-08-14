"""GUI'den bağımsız otomatik yedekleme zamanlayıcısı (Windows Service içinde)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable, Optional

from kurum_yedekleme.config.schema import ScheduleConfig
from kurum_yedekleme.config.writer import validate_schedule_time
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
    pending_area_count: int
    message: str = "Bugünün otomatik yedeklemesi henüz yapılmadı."


class ScheduleService:
    """
    Günlük otomatik yedekleme.

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

    @property
    def schedule(self) -> ScheduleConfig:
        with self._lock:
            return self._schedule

    @property
    def last_job(self) -> Optional[JobResult]:
        return self._last_job

    def update_schedule(self, schedule: ScheduleConfig) -> None:
        validate_schedule_time(schedule.time)
        with self._lock:
            self._schedule = schedule
            self._pending_missed_check = True
        self._idle.set()
        logger.info(
            "Zamanlayıcı güncellendi: enabled=%s time=%s",
            schedule.enabled,
            schedule.time,
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
                "Zamanlayıcı başlatıldı (enabled=%s, time=%s, poll=%.0fs)",
                self._schedule.enabled,
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
        if not self._is_scheduled_moment(moment, schedule.time):
            return False
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

        scheduled_today = datetime.combine(
            moment.date(), self._parse_hhmm(schedule.time), tzinfo=moment.tzinfo
        )
        if moment < scheduled_today:
            return None

        pending = self._pending_automatic_areas()
        if not pending:
            return None
        return MissedBackupInfo(
            scheduled_time=schedule.time,
            pending_area_count=len(pending),
        )

    def run_missed_if_needed(self, now: Optional[datetime] = None) -> bool:
        info = self.check_missed_backup(now=now)
        if info is None:
            return False
        logger.info(
            "Kaçırılmış otomatik yedek tespit edildi (%s alan). Başlatılıyor.",
            info.pending_area_count,
            operation="start",
        )
        return self.run_automatic_if_needed(now=now)

    def run_automatic_if_needed(self, now: Optional[datetime] = None) -> bool:
        pending = self._pending_automatic_areas()
        if not pending:
            logger.debug("Otomatik yedek: bekleyen alan yok.")
            return False
        if self._backups.is_busy:
            logger.info(
                "Zamanı geldi ancak başka bir yedekleme sürüyor; atlanıyor."
            )
            return False
        logger.info(
            "Otomatik yedekleme başlıyor (%s alan)",
            len(pending),
            operation="start",
        )
        try:
            self._last_job = self._backups.run(
                pending,
                backup_type=BackupType.AUTOMATIC,
                skip_successful_automatic_today=True,
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
        target = self._parse_hhmm(schedule.time)
        today_run = datetime.combine(moment.date(), target, tzinfo=moment.tzinfo)
        if moment < today_run:
            return today_run
        tomorrow = moment.date() + timedelta(days=1)
        return datetime.combine(tomorrow, target, tzinfo=moment.tzinfo)

    def _pending_automatic_areas(self) -> list[BackupArea]:
        pending: list[BackupArea] = []
        for area in self._areas.list_enabled():
            if area.id is None:
                pending.append(area)
                continue
            if not self._history.has_successful_automatic_today(area.id):
                pending.append(area)
        return pending

    def _consume_missed_check(self) -> bool:
        with self._lock:
            pending = self._pending_missed_check
            self._pending_missed_check = False
            return pending

    def _loop(self) -> None:
        # Servis / TEST MODE oturum açılışında kaçırılmış yedek
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
    def _parse_hhmm(value: str) -> time:
        hour_s, minute_s = validate_schedule_time(value).split(":")
        return time(hour=int(hour_s), minute=int(minute_s))

    @staticmethod
    def _is_scheduled_moment(moment: datetime, schedule_time: str) -> bool:
        target = ScheduleService._parse_hhmm(schedule_time)
        return moment.hour == target.hour and moment.minute == target.minute
