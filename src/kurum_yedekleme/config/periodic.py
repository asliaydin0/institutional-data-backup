"""Günlük / haftalık / aylık periyodik zamanlama yardımcıları."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

PERIOD_FREQUENCIES = ("daily", "weekly", "monthly")
DEFAULT_PERIOD_FREQUENCY = "daily"
DEFAULT_PERIOD_WEEKDAY = 6
DEFAULT_PERIOD_DAY_OF_MONTH = 1


@dataclass(frozen=True)
class PeriodicTiming:
    frequency: str = DEFAULT_PERIOD_FREQUENCY
    time: str = "02:00"
    weekday: int = DEFAULT_PERIOD_WEEKDAY
    day_of_month: int = DEFAULT_PERIOD_DAY_OF_MONTH


def parse_hhmm(value: str) -> time:
    from kurum_yedekleme.config.writer import validate_schedule_time

    hour_s, minute_s = validate_schedule_time(value).split(":")
    return time(hour=int(hour_s), minute=int(minute_s))


def is_period_due(moment: datetime, timing: PeriodicTiming) -> bool:
    target = parse_hhmm(timing.time)
    if moment.hour != target.hour or moment.minute != target.minute:
        return False
    freq = timing.frequency
    if freq == "daily":
        return True
    if freq == "weekly":
        return moment.weekday() == int(timing.weekday)
    if freq == "monthly":
        return moment.day == int(timing.day_of_month)
    return False


def period_window_started(moment: datetime, timing: PeriodicTiming) -> bool:
    target = parse_hhmm(timing.time)
    scheduled = datetime.combine(moment.date(), target, tzinfo=moment.tzinfo)
    if moment < scheduled:
        return False
    freq = timing.frequency
    if freq == "daily":
        return True
    if freq == "weekly":
        return moment.weekday() == int(timing.weekday)
    if freq == "monthly":
        return moment.day >= int(timing.day_of_month)
    return False


def period_key(moment: datetime, frequency: str) -> str:
    if frequency == "daily":
        return moment.strftime("%Y-%m-%d")
    if frequency == "weekly":
        year, week, _ = moment.isocalendar()
        return f"{year}-W{week:02d}"
    if frequency == "monthly":
        return moment.strftime("%Y-%m")
    return moment.strftime("%Y-%m-%d")


def period_bounds_utc(
    moment: datetime, frequency: str
) -> tuple[datetime, datetime]:
    """Geçerli periyodun UTC başlangıç/bitiş anları (yerel takvime göre)."""
    if moment.tzinfo is None:
        moment = moment.astimezone()
    local = moment.astimezone()
    tz = local.tzinfo

    if frequency == "daily":
        start_local = datetime.combine(local.date(), time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1) - timedelta(seconds=1)
    elif frequency == "weekly":
        week_start = local.date() - timedelta(days=local.weekday())
        start_local = datetime.combine(week_start, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=7) - timedelta(seconds=1)
    elif frequency == "monthly":
        start_local = datetime.combine(
            date(local.year, local.month, 1), time.min, tzinfo=tz
        )
        if local.month == 12:
            next_month = date(local.year + 1, 1, 1)
        else:
            next_month = date(local.year, local.month + 1, 1)
        end_local = datetime.combine(next_month, time.min, tzinfo=tz) - timedelta(
            seconds=1
        )
    else:
        start_local = datetime.combine(local.date(), time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1) - timedelta(seconds=1)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def next_period_run_at(moment: datetime, timing: PeriodicTiming) -> datetime | None:
    if moment.tzinfo is None:
        moment = moment.astimezone()
    target = parse_hhmm(timing.time)
    candidate = datetime.combine(moment.date(), target, tzinfo=moment.tzinfo)
    for _ in range(400):
        if candidate >= moment and _matches_frequency(candidate, timing):
            return candidate
        candidate += timedelta(days=1)
    return None


def _matches_frequency(moment: datetime, timing: PeriodicTiming) -> bool:
    if timing.frequency == "daily":
        return True
    if timing.frequency == "weekly":
        return moment.weekday() == int(timing.weekday)
    if timing.frequency == "monthly":
        return moment.day == int(timing.day_of_month)
    return False


def frequency_label_tr(frequency: str) -> str:
    labels = {"daily": "Günlük", "weekly": "Haftalık", "monthly": "Aylık"}
    return labels.get(frequency, frequency)


def scheduled_run_in_period(moment: datetime, timing: PeriodicTiming) -> datetime:
    """Geçerli periyot içindeki planlanmış çalışma anı."""
    if moment.tzinfo is None:
        moment = moment.astimezone()
    target = parse_hhmm(timing.time)
    freq = timing.frequency
    if freq == "daily":
        return datetime.combine(moment.date(), target, tzinfo=moment.tzinfo)
    if freq == "weekly":
        week_start = moment.date() - timedelta(days=moment.weekday())
        scheduled_date = week_start + timedelta(days=int(timing.weekday))
        return datetime.combine(scheduled_date, target, tzinfo=moment.tzinfo)
    if freq == "monthly":
        scheduled_date = date(moment.year, moment.month, int(timing.day_of_month))
        return datetime.combine(scheduled_date, target, tzinfo=moment.tzinfo)
    return datetime.combine(moment.date(), target, tzinfo=moment.tzinfo)


def period_slot_passed(moment: datetime, timing: PeriodicTiming) -> bool:
    return moment >= scheduled_run_in_period(moment, timing)
