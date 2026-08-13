"""GUI'den bağımsız otomatik yedekleme zamanlayıcı servisi."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable, Optional

from kurum_yedekleme.config.schema import ScheduleConfig
from kurum_yedekleme.config.writer import validate_schedule_time
from kurum_yedekleme.services.backup_service import (
    BackupInProgressError,
    BackupService,
)
from kurum_yedekleme.services.history_service import HistoryService
from kurum_yedekleme.services.schedule_state import ScheduleStateStore
from kurum_yedekleme.utils.app_logger import get_logger

logger = get_logger("BackupScheduler")

Clock = Callable[[], datetime]
BackupRunner = Callable[[], None]


@dataclass(frozen=True)
class MissedBackupInfo:
    """Kaçırılmış günlük otomatik yedekleme bilgisi."""

    scheduled_time: str
    today: date
    message: str = (
        "Bugünün otomatik yedeklemesi henüz yapılmamış. "
        "Şimdi başlatmak ister misiniz?"
    )


class ScheduleService:
    """
    Günlük otomatik yedekleme zamanlayıcısı.

    GUI'den bağımsızdır; arka plan thread'i ile periyodik kontrol yapar.
    """

    def __init__(
        self,
        schedule: ScheduleConfig,
        backup_service: BackupService,
        *,
        state_store: ScheduleStateStore,
        history_service: Optional[HistoryService] = None,
        poll_interval_seconds: float = 20.0,
        clock: Optional[Clock] = None,
        backup_runner: Optional[BackupRunner] = None,
    ) -> None:
        self._schedule = schedule
        self._backup_service = backup_service
        self._state = state_store
        self._history = history_service
        self._poll_interval = max(1.0, float(poll_interval_seconds))
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._backup_runner = backup_runner or self._default_run_auto_backup

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    @property
    def schedule(self) -> ScheduleConfig:
        with self._lock:
            return self._schedule

    def update_schedule(self, schedule: ScheduleConfig) -> None:
        """Çalışma zamanında zamanlamayı günceller (ayarlar kaydından)."""
        validate_schedule_time(schedule.time)
        with self._lock:
            self._schedule = schedule
        logger.info(
            "Zamanlayıcı güncellendi: enabled=%s time=%s",
            schedule.enabled,
            schedule.time,
        )

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Arka plan zamanlayıcı thread'ini başlatır."""
        with self._lock:
            if self.is_running:
                return
            self._stop_event.clear()
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
        """Zamanlayıcıyı durdurur."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        logger.info("Zamanlayıcı durduruldu.")

    def tick(self, now: Optional[datetime] = None) -> bool:
        """
        Tek kontrol adımı (test / manuel tetik).

        Returns:
            Otomatik yedekleme başlatıldıysa True.
        """
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()

        with self._lock:
            schedule = self._schedule

        if not schedule.enabled:
            return False

        if not self._is_scheduled_moment(moment, schedule.time):
            return False

        if self._already_ran_today(moment.date()):
            logger.debug(
                "Bugün otomatik yedekleme zaten çalıştı (%s)", moment.date()
            )
            return False

        if self._backup_service.is_busy:
            logger.info(
                "Zamanı geldi ancak başka bir yedekleme sürüyor; atlanıyor."
            )
            return False

        logger.info(
            "Yedekleme başlatıldı",
            operation="start",
        )
        logger.info(
            "Otomatik yedekleme tetikleniyor (%s %s)",
            moment.date(),
            schedule.time,
            operation="start",
        )
        # Günü işaretle — aynı gün ikinci otomatik başlamasın
        self._state.set_last_auto_run_date(moment.date())
        try:
            self._backup_runner()
        except BackupInProgressError:
            logger.warning("Otomatik yedekleme: eşzamanlı iş engellendi.")
            return False
        except Exception:
            logger.exception("Otomatik yedekleme hatası")
            return False
        return True

    def check_missed_backup(
        self, now: Optional[datetime] = None
    ) -> Optional[MissedBackupInfo]:
        """
        Bilgisayar planlanan saatte kapalıysa / uygulama geç açıldıysa
        kaçırılmış günlük yedeği tespit eder.
        """
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()

        with self._lock:
            schedule = self._schedule

        if not schedule.enabled:
            return None

        today = moment.date()
        scheduled_today = datetime.combine(
            today, self._parse_hhmm(schedule.time), tzinfo=moment.tzinfo
        )
        if moment < scheduled_today:
            return None

        if self._already_ran_today(today):
            return None

        # Son başarılı yedekleme bugün mü?
        if self._history is not None:
            last_ok = self._history.get_last_successful()
            if last_ok is not None:
                last_local = last_ok.backup_start_time.astimezone(moment.tzinfo)
                if last_local.date() == today:
                    return None

        # Aynı oturum/gün içinde bir kez sor
        prompted = self._state.get_missed_prompt_date()
        if prompted == today:
            return None

        return MissedBackupInfo(scheduled_time=schedule.time, today=today)

    def acknowledge_missed_prompt(self, today: Optional[date] = None) -> None:
        """Kaçırılmış yedek sorusunun gösterildiğini işaretler."""
        day = today or self._clock().date()
        self._state.set_missed_prompt_date(day)

    def next_run_at(self, now: Optional[datetime] = None) -> Optional[datetime]:
        """Bir sonraki planlanan otomatik yedekleme zamanı (yerel)."""
        moment = now or self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()
        with self._lock:
            schedule = self._schedule
        if not schedule.enabled:
            return None
        target = self._parse_hhmm(schedule.time)
        today_run = datetime.combine(moment.date(), target, tzinfo=moment.tzinfo)
        if moment < today_run and not self._already_ran_today(moment.date()):
            return today_run
        from datetime import timedelta

        tomorrow = moment.date() + timedelta(days=1)
        return datetime.combine(tomorrow, target, tzinfo=moment.tzinfo)

    def mark_auto_run_for_today(self, today: Optional[date] = None) -> None:
        """Bugün otomatik yedeklemenin başlatıldığını kalıcı olarak işaretler."""
        day = today or self._clock().date()
        self._state.set_last_auto_run_date(day)
        self._state.set_missed_prompt_date(day)

    def run_missed_backup_now(self) -> None:
        """Kullanıcı onayı sonrası kaçırılmış yedeği başlatır."""
        self.mark_auto_run_for_today()
        self._backup_runner()

    def _default_run_auto_backup(self) -> None:
        self._backup_service.run_backup(trigger="schedule")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Zamanlayıcı tick hatası")
            self._stop_event.wait(self._poll_interval)

    def _already_ran_today(self, today: date) -> bool:
        last = self._state.get_last_auto_run_date()
        return last == today

    @staticmethod
    def _parse_hhmm(value: str) -> time:
        hour_s, minute_s = validate_schedule_time(value).split(":")
        return time(hour=int(hour_s), minute=int(minute_s))

    @staticmethod
    def _is_scheduled_moment(moment: datetime, schedule_time: str) -> bool:
        """Belirlenen HH:MM dakikası içinde mi?"""
        target = ScheduleService._parse_hhmm(schedule_time)
        return moment.hour == target.hour and moment.minute == target.minute
