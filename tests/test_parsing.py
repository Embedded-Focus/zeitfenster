from datetime import time, timedelta

import pytest

from zeitfenster.parsing import parse_duration, parse_time_range


class TestParseDuration:
    def test_minutes(self):
        assert parse_duration("30m") == timedelta(minutes=30)

    def test_hours(self):
        assert parse_duration("2h") == timedelta(hours=2)

    def test_days(self):
        assert parse_duration("60d") == timedelta(days=60)

    def test_strips_whitespace(self):
        assert parse_duration("  15m  ") == timedelta(minutes=15)

    def test_invalid_unit(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("10s")

    def test_no_number(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("m")

    def test_empty_string(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("")


class TestParseTimeRange:
    def test_standard_range(self):
        start, end = parse_time_range("09:00-17:00")
        assert start == time(9, 0)
        assert end == time(17, 0)

    def test_with_whitespace(self):
        start, end = parse_time_range("  09:00 - 17:00  ")
        assert start == time(9, 0)
        assert end == time(17, 0)

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError, match="End time must be after start"):
            parse_time_range("17:00-09:00")

    def test_equal_times_raises(self):
        with pytest.raises(ValueError, match="End time must be after start"):
            parse_time_range("09:00-09:00")

    def test_missing_separator(self):
        with pytest.raises(ValueError, match="Invalid time range"):
            parse_time_range("09:00")
