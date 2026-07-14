from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar

from zeitfenster.caldav_client import (
    _extract_busy_intervals,
    _validate_caldav_redirect,
    fetch_busy_intervals,
)
from zeitfenster.config import CalendarSource

TZ = ZoneInfo("Europe/Vienna")


class FakeResponse:
    def __init__(self, url, is_redirect=False, location=None):
        self.url = url
        self.is_redirect = is_redirect
        self.headers = {"location": location} if location else {}


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


class TestValidateCaldavRedirect:
    def test_ignores_non_redirect(self):
        response = FakeResponse(url="https://caldav.example.com/cal/")
        _validate_caldav_redirect("caldav.example.com", "https", response)

    def test_allows_same_host_same_scheme(self):
        response = FakeResponse(
            url="https://caldav.example.com/cal/",
            is_redirect=True,
            location="https://caldav.example.com/other/",
        )
        _validate_caldav_redirect("caldav.example.com", "https", response)

    def test_allows_relative_redirect_location(self):
        response = FakeResponse(
            url="https://caldav.example.com/cal/",
            is_redirect=True,
            location="/other/",
        )
        _validate_caldav_redirect("caldav.example.com", "https", response)

    def test_rejects_cross_host_redirect(self):
        response = FakeResponse(
            url="https://caldav.example.com/cal/",
            is_redirect=True,
            location="https://internal.evil.example/steal",
        )
        with pytest.raises(ValueError, match="Refusing to follow"):
            _validate_caldav_redirect("caldav.example.com", "https", response)

    def test_rejects_scheme_downgrade(self):
        response = FakeResponse(
            url="https://caldav.example.com/cal/",
            is_redirect=True,
            location="http://caldav.example.com/cal/",
        )
        with pytest.raises(ValueError, match="Refusing to follow"):
            _validate_caldav_redirect("caldav.example.com", "https", response)

    def test_allows_same_host_over_http(self):
        # Mirrors self-hosted CalDAV over plain HTTP on an internal network
        # (e.g. this project's own demo config).
        response = FakeResponse(
            url="http://radicale/reader/work/",
            is_redirect=True,
            location="http://radicale/reader/work/other/",
        )
        _validate_caldav_redirect("radicale", "http", response)


class TestFetchBusyIntervalsRedirectHook:
    def test_registers_redirect_hook_on_session(self, monkeypatch):
        monkeypatch.setenv("TEST_CALDAV_PASSWORD", "secret")
        source = CalendarSource(
            url="https://caldav.example.com/cal/",
            username="reader",
            password_env="TEST_CALDAV_PASSWORD",
        )

        fake_session = SimpleNamespace(hooks={"response": []})
        fake_calendar = MagicMock()
        fake_calendar.search.return_value = []
        fake_client = MagicMock()
        fake_client.session = fake_session
        fake_client.calendar.return_value = fake_calendar

        with patch(
            "zeitfenster.caldav_client.caldav.DAVClient", return_value=fake_client
        ):
            fetch_busy_intervals(
                source,
                datetime(2026, 7, 1, tzinfo=TZ),
                datetime(2026, 7, 2, tzinfo=TZ),
            )

        assert len(fake_session.hooks["response"]) == 1
        hook = fake_session.hooks["response"][0]

        bad_response = FakeResponse(
            url="https://caldav.example.com/cal/",
            is_redirect=True,
            location="https://internal.evil.example/steal",
        )
        with pytest.raises(ValueError, match="Refusing to follow"):
            hook(bad_response)
