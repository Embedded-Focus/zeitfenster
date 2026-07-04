from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog

from zeitfenster.caldav_client import BusyInterval, fetch_busy_intervals
from zeitfenster.config import AppConfig, WorkingHours
from zeitfenster.ics_client import fetch_busy_intervals_ics
from zeitfenster.parsing import parse_duration, parse_time_range

logger = structlog.get_logger()

_WEEKDAY_ATTRS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class FreeSlot:
    start: datetime
    end: datetime
    duration: timedelta


def merge_intervals(intervals: list[BusyInterval]) -> list[BusyInterval]:
    if not intervals:
        return []
    sorted_intervals = sorted(intervals)
    merged = [sorted_intervals[0]]
    for current in sorted_intervals[1:]:
        prev = merged[-1]
        if current.start <= prev.end:
            if current.end > prev.end:
                merged[-1] = BusyInterval(start=prev.start, end=current.end)
        else:
            merged.append(current)
    return merged


def apply_buffer(
    intervals: list[BusyInterval], buffer: timedelta
) -> list[BusyInterval]:
    if not buffer:
        return intervals
    buffered = []
    for iv in intervals:
        buffered.append(BusyInterval(start=iv.start - buffer, end=iv.end + buffer))
    return buffered


def _normalize_datetime(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _normalize_busy_intervals(
    intervals: list[BusyInterval],
    tz: ZoneInfo,
) -> list[BusyInterval]:
    return [
        BusyInterval(
            start=_normalize_datetime(iv.start, tz),
            end=_normalize_datetime(iv.end, tz),
        )
        for iv in intervals
    ]


def _get_working_ranges(
    working_hours: WorkingHours, day: datetime
) -> list[tuple[datetime, datetime]]:
    weekday_attr = _WEEKDAY_ATTRS[day.weekday()]
    ranges_str: list[str] = getattr(working_hours, weekday_attr)
    result = []
    for r in ranges_str:
        start_time, end_time = parse_time_range(r)
        result.append(
            (
                day.replace(
                    hour=start_time.hour,
                    minute=start_time.minute,
                    second=0,
                    microsecond=0,
                ),
                day.replace(
                    hour=end_time.hour,
                    minute=end_time.minute,
                    second=0,
                    microsecond=0,
                ),
            )
        )
    return result


def _generate_candidate_slots(
    working_ranges: list[tuple[datetime, datetime]],
    slot_duration: timedelta,
) -> list[FreeSlot]:
    candidates = []
    for range_start, range_end in working_ranges:
        current = range_start
        while current + slot_duration <= range_end:
            candidates.append(
                FreeSlot(
                    start=current, end=current + slot_duration, duration=slot_duration
                )
            )
            current += slot_duration
    return candidates


def _overlaps_any(slot: FreeSlot, busy: list[BusyInterval]) -> bool:
    for iv in busy:
        if slot.start < iv.end and slot.end > iv.start:
            return True
    return False


def compute_free_slots(
    busy_intervals: list[BusyInterval],
    config: AppConfig,
) -> dict[str, list[FreeSlot]]:
    tz = ZoneInfo(config.rules.timezone)
    buffer = parse_duration(config.rules.buffer)
    minimum_notice = parse_duration(config.rules.minimum_notice)
    horizon = parse_duration(config.rules.horizon)

    normalized_busy = _normalize_busy_intervals(busy_intervals, tz)
    buffered = apply_buffer(normalized_busy, buffer)
    merged = merge_intervals(buffered)

    now = datetime.now(tz)
    earliest = now + minimum_notice
    latest = now + horizon

    result: dict[str, list[FreeSlot]] = {}

    for duration_str in config.rules.slot_durations:
        slot_duration = parse_duration(duration_str)
        free: list[FreeSlot] = []

        current_day = earliest.replace(hour=0, minute=0, second=0, microsecond=0)
        while current_day < latest:
            working_ranges = _get_working_ranges(
                config.rules.working_hours, current_day
            )
            candidates = _generate_candidate_slots(working_ranges, slot_duration)

            for slot in candidates:
                if slot.start < earliest or slot.end > latest:
                    continue
                if not _overlaps_any(slot, merged):
                    free.append(slot)

            current_day += timedelta(days=1)

        result[duration_str] = free

    return result


def intersect_free_slots(
    slot_sets: list[dict[str, list[FreeSlot]]],
) -> dict[str, list[FreeSlot]]:
    if not slot_sets:
        return {}
    if len(slot_sets) == 1:
        return slot_sets[0]

    all_durations = set()
    for s in slot_sets:
        all_durations.update(s.keys())

    result: dict[str, list[FreeSlot]] = {}
    for duration in all_durations:
        sets_of_keys: list[set[tuple[datetime, datetime]]] = []
        for s in slot_sets:
            slots = s.get(duration, [])
            sets_of_keys.append({(slot.start, slot.end) for slot in slots})
        common = sets_of_keys[0].intersection(*sets_of_keys[1:])
        first_slots = slot_sets[0].get(duration, [])
        result[duration] = [s for s in first_slots if (s.start, s.end) in common]
    return result


def fetch_and_compute(config: AppConfig) -> dict[str, list[FreeSlot]]:
    tz = ZoneInfo(config.rules.timezone)
    now = datetime.now(tz)
    horizon = parse_duration(config.rules.horizon)
    buffer = parse_duration(config.rules.buffer)
    range_start = now - buffer
    range_end = now + horizon + buffer

    all_busy: list[BusyInterval] = []
    for source in config.availability.calendars:
        intervals = fetch_busy_intervals(source, range_start, range_end)
        all_busy.extend(intervals)
    for source in config.availability.ics_urls:
        intervals = fetch_busy_intervals_ics(source, range_start, range_end)
        all_busy.extend(intervals)

    local_slots = compute_free_slots(all_busy, config)

    if not config.availability.zeitfenster_urls:
        return local_slots

    from zeitfenster.zeitfenster_client import fetch_free_slots

    slot_sets: list[dict[str, list[FreeSlot]]] = [local_slots]
    for source in config.availability.zeitfenster_urls:
        try:
            remote = fetch_free_slots(source, config.rules.slot_durations)
            slot_sets.append(remote)
        except Exception:
            logger.exception("federation_fetch_failed", url=source.url)
            return {d: [] for d in config.rules.slot_durations}

    return intersect_free_slots(slot_sets)
