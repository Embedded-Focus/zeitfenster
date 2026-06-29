from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from zeitfenster.availability import (
    FreeSlot,
    apply_buffer,
    compute_free_slots,
    intersect_free_slots,
    merge_intervals,
)
from zeitfenster.caldav_client import BusyInterval
from zeitfenster.config import AppConfig

TZ = ZoneInfo("Europe/Vienna")


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


def _make_config(
    slot_durations: list[str] | None = None,
    buffer: str = "0m",
    minimum_notice: str = "0m",
    horizon: str = "7d",
    working_hours: dict | None = None,
) -> AppConfig:
    wh = (
        working_hours
        if working_hours is not None
        else {"mon": ["09:00-17:00"], "tue": ["09:00-17:00"]}
    )
    return AppConfig.model_validate(
        {
            "email": {"owner": "test@example.com"},
            "rules": {
                "timezone": "Europe/Vienna",
                "working_hours": wh,
                "slot_durations": slot_durations or ["60m"],
                "buffer": buffer,
                "minimum_notice": minimum_notice,
                "horizon": horizon,
            },
        }
    )


class TestMergeIntervals:
    def test_empty(self):
        assert merge_intervals([]) == []

    def test_single(self):
        iv = BusyInterval(start=_dt(2026, 7, 1, 9), end=_dt(2026, 7, 1, 10))
        assert merge_intervals([iv]) == [iv]

    def test_non_overlapping(self):
        a = BusyInterval(start=_dt(2026, 7, 1, 9), end=_dt(2026, 7, 1, 10))
        b = BusyInterval(start=_dt(2026, 7, 1, 11), end=_dt(2026, 7, 1, 12))
        assert merge_intervals([b, a]) == [a, b]

    def test_overlapping(self):
        a = BusyInterval(start=_dt(2026, 7, 1, 9), end=_dt(2026, 7, 1, 11))
        b = BusyInterval(start=_dt(2026, 7, 1, 10), end=_dt(2026, 7, 1, 12))
        result = merge_intervals([a, b])
        assert len(result) == 1
        assert result[0].start == _dt(2026, 7, 1, 9)
        assert result[0].end == _dt(2026, 7, 1, 12)

    def test_adjacent(self):
        a = BusyInterval(start=_dt(2026, 7, 1, 9), end=_dt(2026, 7, 1, 10))
        b = BusyInterval(start=_dt(2026, 7, 1, 10), end=_dt(2026, 7, 1, 11))
        result = merge_intervals([a, b])
        assert len(result) == 1
        assert result[0].start == _dt(2026, 7, 1, 9)
        assert result[0].end == _dt(2026, 7, 1, 11)

    def test_contained(self):
        outer = BusyInterval(start=_dt(2026, 7, 1, 9), end=_dt(2026, 7, 1, 14))
        inner = BusyInterval(start=_dt(2026, 7, 1, 10), end=_dt(2026, 7, 1, 12))
        result = merge_intervals([outer, inner])
        assert len(result) == 1
        assert result[0] == outer

    def test_multiple_merges(self):
        intervals = [
            BusyInterval(start=_dt(2026, 7, 1, 9), end=_dt(2026, 7, 1, 10)),
            BusyInterval(start=_dt(2026, 7, 1, 10), end=_dt(2026, 7, 1, 11)),
            BusyInterval(start=_dt(2026, 7, 1, 13), end=_dt(2026, 7, 1, 14)),
            BusyInterval(start=_dt(2026, 7, 1, 14), end=_dt(2026, 7, 1, 15)),
        ]
        result = merge_intervals(intervals)
        assert len(result) == 2
        assert result[0].start == _dt(2026, 7, 1, 9)
        assert result[0].end == _dt(2026, 7, 1, 11)
        assert result[1].start == _dt(2026, 7, 1, 13)
        assert result[1].end == _dt(2026, 7, 1, 15)


class TestApplyBuffer:
    def test_no_buffer(self):
        iv = BusyInterval(start=_dt(2026, 7, 1, 10), end=_dt(2026, 7, 1, 11))
        result = apply_buffer([iv], timedelta(0))
        assert result == [iv]

    def test_buffer_applied(self):
        iv = BusyInterval(start=_dt(2026, 7, 1, 10), end=_dt(2026, 7, 1, 11))
        result = apply_buffer([iv], timedelta(minutes=15))
        assert len(result) == 1
        assert result[0].start == _dt(2026, 7, 1, 9, 45)
        assert result[0].end == _dt(2026, 7, 1, 11, 15)


class TestComputeFreeSlots:
    def test_no_busy_intervals_returns_all_working_slots(self):
        # Monday 2026-06-29, working hours 09:00-17:00, 60m slots
        fake_now = _dt(2026, 6, 28, 12, 0)  # Sunday
        config = _make_config(
            slot_durations=["60m"],
            minimum_notice="0m",
            horizon="2d",
            working_hours={"mon": ["09:00-17:00"]},
        )
        with patch("zeitfenster.availability.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = compute_free_slots([], config)

        assert "60m" in result
        slots = result["60m"]
        assert len(slots) == 8
        assert slots[0].start == _dt(2026, 6, 29, 9, 0)
        assert slots[-1].start == _dt(2026, 6, 29, 16, 0)

    def test_busy_interval_removes_overlapping_slots(self):
        fake_now = _dt(2026, 6, 28, 12, 0)
        config = _make_config(
            slot_durations=["60m"],
            minimum_notice="0m",
            horizon="2d",
            working_hours={"mon": ["09:00-17:00"]},
        )
        busy = [
            BusyInterval(start=_dt(2026, 6, 29, 10, 0), end=_dt(2026, 6, 29, 11, 0))
        ]
        with patch("zeitfenster.availability.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = compute_free_slots(busy, config)

        slots = result["60m"]
        slot_starts = [s.start.hour for s in slots]
        assert 10 not in slot_starts
        assert 9 in slot_starts
        assert 11 in slot_starts

    def test_buffer_removes_adjacent_slots(self):
        fake_now = _dt(2026, 6, 28, 12, 0)
        config = _make_config(
            slot_durations=["30m"],
            buffer="30m",
            minimum_notice="0m",
            horizon="2d",
            working_hours={"mon": ["09:00-12:00"]},
        )
        # Busy 10:00-10:30, with 30m buffer → blocks 09:30-11:00
        busy = [
            BusyInterval(start=_dt(2026, 6, 29, 10, 0), end=_dt(2026, 6, 29, 10, 30))
        ]
        with patch("zeitfenster.availability.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = compute_free_slots(busy, config)

        slots = result["30m"]
        slot_times = [(s.start.hour, s.start.minute) for s in slots]
        assert (9, 0) in slot_times
        assert (9, 30) not in slot_times  # blocked by buffer before
        assert (10, 0) not in slot_times  # the busy slot itself
        assert (10, 30) not in slot_times  # blocked by buffer after
        assert (11, 0) in slot_times
        assert (11, 30) in slot_times

    def test_minimum_notice_filters_near_slots(self):
        # Now is Monday 09:00, minimum_notice 2h → earliest slot at 11:00
        fake_now = _dt(2026, 6, 29, 9, 0)
        config = _make_config(
            slot_durations=["60m"],
            minimum_notice="2h",
            horizon="1d",
            working_hours={"mon": ["09:00-17:00"]},
        )
        with patch("zeitfenster.availability.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = compute_free_slots([], config)

        slots = result["60m"]
        assert all(s.start >= _dt(2026, 6, 29, 11, 0) for s in slots)
        assert slots[0].start == _dt(2026, 6, 29, 11, 0)

    def test_multiple_durations(self):
        fake_now = _dt(2026, 6, 28, 12, 0)
        config = _make_config(
            slot_durations=["30m", "60m"],
            minimum_notice="0m",
            horizon="2d",
            working_hours={"mon": ["09:00-11:00"]},
        )
        with patch("zeitfenster.availability.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = compute_free_slots([], config)

        assert len(result["30m"]) == 4  # 09:00, 09:30, 10:00, 10:30
        assert len(result["60m"]) == 2  # 09:00, 10:00

    def test_multiple_working_ranges_per_day(self):
        fake_now = _dt(2026, 6, 28, 12, 0)
        config = _make_config(
            slot_durations=["60m"],
            minimum_notice="0m",
            horizon="2d",
            working_hours={"mon": ["09:00-12:00", "13:00-15:00"]},
        )
        with patch("zeitfenster.availability.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = compute_free_slots([], config)

        slots = result["60m"]
        assert len(slots) == 5  # 09, 10, 11 + 13, 14
        slot_hours = [s.start.hour for s in slots]
        assert 12 not in slot_hours

    def test_no_working_hours_returns_empty(self):
        fake_now = _dt(2026, 6, 28, 12, 0)
        config = _make_config(
            slot_durations=["60m"],
            minimum_notice="0m",
            horizon="2d",
            working_hours={},
        )
        with patch("zeitfenster.availability.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = compute_free_slots([], config)

        assert result["60m"] == []


def _slot(hour: int, minute: int, duration_minutes: int) -> FreeSlot:
    start = _dt(2026, 7, 1, hour, minute)
    return FreeSlot(
        start=start,
        end=start + timedelta(minutes=duration_minutes),
        duration=timedelta(minutes=duration_minutes),
    )


class TestIntersectFreeSlots:
    def test_empty_input(self):
        assert intersect_free_slots([]) == {}

    def test_single_set_unchanged(self):
        slots = {"60m": [_slot(9, 0, 60), _slot(10, 0, 60)]}
        result = intersect_free_slots([slots])
        assert result["60m"] == slots["60m"]

    def test_identical_sets(self):
        slots_a = {"60m": [_slot(9, 0, 60), _slot(10, 0, 60)]}
        slots_b = {"60m": [_slot(9, 0, 60), _slot(10, 0, 60)]}
        result = intersect_free_slots([slots_a, slots_b])
        assert len(result["60m"]) == 2

    def test_disjoint_sets(self):
        slots_a = {"60m": [_slot(9, 0, 60)]}
        slots_b = {"60m": [_slot(14, 0, 60)]}
        result = intersect_free_slots([slots_a, slots_b])
        assert result["60m"] == []

    def test_partial_overlap(self):
        slots_a = {"60m": [_slot(9, 0, 60), _slot(10, 0, 60), _slot(11, 0, 60)]}
        slots_b = {"60m": [_slot(10, 0, 60), _slot(11, 0, 60), _slot(14, 0, 60)]}
        result = intersect_free_slots([slots_a, slots_b])
        assert len(result["60m"]) == 2
        assert result["60m"][0].start.hour == 10
        assert result["60m"][1].start.hour == 11

    def test_preserves_order_from_first_set(self):
        slots_a = {"60m": [_slot(11, 0, 60), _slot(9, 0, 60)]}
        slots_b = {"60m": [_slot(9, 0, 60), _slot(11, 0, 60)]}
        result = intersect_free_slots([slots_a, slots_b])
        assert result["60m"][0].start.hour == 11
        assert result["60m"][1].start.hour == 9

    def test_multiple_durations(self):
        slots_a = {
            "30m": [_slot(9, 0, 30), _slot(9, 30, 30)],
            "60m": [_slot(9, 0, 60)],
        }
        slots_b = {
            "30m": [_slot(9, 0, 30)],
            "60m": [_slot(9, 0, 60)],
        }
        result = intersect_free_slots([slots_a, slots_b])
        assert len(result["30m"]) == 1
        assert len(result["60m"]) == 1

    def test_duration_missing_in_one_set_yields_empty(self):
        slots_a = {"30m": [_slot(9, 0, 30)], "60m": [_slot(9, 0, 60)]}
        slots_b = {"30m": [_slot(9, 0, 30)]}
        result = intersect_free_slots([slots_a, slots_b])
        assert len(result["30m"]) == 1
        assert result["60m"] == []

    def test_three_sets(self):
        slots_a = {"60m": [_slot(9, 0, 60), _slot(10, 0, 60), _slot(11, 0, 60)]}
        slots_b = {"60m": [_slot(9, 0, 60), _slot(10, 0, 60)]}
        slots_c = {"60m": [_slot(10, 0, 60), _slot(11, 0, 60)]}
        result = intersect_free_slots([slots_a, slots_b, slots_c])
        assert len(result["60m"]) == 1
        assert result["60m"][0].start.hour == 10
