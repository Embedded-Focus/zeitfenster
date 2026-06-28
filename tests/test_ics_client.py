from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from zeitfenster.config import IcsUrlSource
from zeitfenster.ics_client import fetch_busy_intervals_ics

TZ = ZoneInfo("Europe/Vienna")

SIMPLE_ICS = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART:20260701T100000Z
DTEND:20260701T110000Z
SUMMARY:Meeting
END:VEVENT
BEGIN:VEVENT
DTSTART:20260701T140000Z
DTEND:20260701T150000Z
SUMMARY:Lunch
END:VEVENT
END:VCALENDAR
"""

RECURRING_ICS = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART:20260701T090000Z
DTEND:20260701T093000Z
SUMMARY:Daily standup
RRULE:FREQ=DAILY;COUNT=5
END:VEVENT
END:VCALENDAR
"""

ALLDAY_ICS = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260701
DTEND;VALUE=DATE:20260702
SUMMARY:Holiday
END:VEVENT
END:VCALENDAR
"""

NO_EVENTS_ICS = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
END:VCALENDAR
"""


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _fetch(ics_data: bytes, range_start: datetime, range_end: datetime):
    source = IcsUrlSource(url="https://example.com/cal.ics")
    with patch("zeitfenster.ics_client.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _FakeResponse(ics_data)
        return fetch_busy_intervals_ics(source, range_start, range_end)


class TestFetchBusyIntervalsIcs:
    def test_simple_events(self):
        intervals = _fetch(
            SIMPLE_ICS,
            datetime(2026, 7, 1, tzinfo=TZ),
            datetime(2026, 7, 2, tzinfo=TZ),
        )
        assert len(intervals) == 2
        summaries_by_hour = {iv.start.hour: iv for iv in intervals}
        assert 10 in summaries_by_hour
        assert 14 in summaries_by_hour

    def test_recurring_events_expanded(self):
        intervals = _fetch(
            RECURRING_ICS,
            datetime(2026, 7, 1, tzinfo=TZ),
            datetime(2026, 7, 8, tzinfo=TZ),
        )
        assert len(intervals) == 5

    def test_allday_events_skipped(self):
        intervals = _fetch(
            ALLDAY_ICS,
            datetime(2026, 7, 1, tzinfo=TZ),
            datetime(2026, 7, 2, tzinfo=TZ),
        )
        assert len(intervals) == 0

    def test_no_events(self):
        intervals = _fetch(
            NO_EVENTS_ICS,
            datetime(2026, 7, 1, tzinfo=TZ),
            datetime(2026, 7, 2, tzinfo=TZ),
        )
        assert len(intervals) == 0

    def test_range_filters_events(self):
        utc = ZoneInfo("UTC")
        intervals = _fetch(
            SIMPLE_ICS,
            datetime(2026, 7, 1, 13, 0, tzinfo=utc),
            datetime(2026, 7, 1, 16, 0, tzinfo=utc),
        )
        assert len(intervals) == 1
        assert intervals[0].start.hour == 14
