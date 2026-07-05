from datetime import datetime
from zoneinfo import ZoneInfo

from icalendar import Calendar

from zeitfenster.caldav_client import _extract_busy_intervals

TZ = ZoneInfo("Europe/Vienna")

ALLDAY_CALDAV_ICS = b"""\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260701
DTEND;VALUE=DATE:20260708
SUMMARY:Vacation
END:VEVENT
END:VCALENDAR
"""


class CalendarObject:
    def __init__(self, data: bytes):
        self.icalendar_instance = Calendar.from_ical(data)


class TestExtractBusyIntervals:
    def test_extracts_allday_event_as_busy_interval(self):
        intervals = _extract_busy_intervals(
            CalendarObject(ALLDAY_CALDAV_ICS),
            default_timezone=TZ,
        )

        assert len(intervals) == 1
        assert intervals[0].start == datetime(2026, 7, 1, tzinfo=TZ)
        assert intervals[0].end == datetime(2026, 7, 8, tzinfo=TZ)
