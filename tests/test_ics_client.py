from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx2
import pytest

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


def _make_response(
    data: bytes,
    status_code: int = 200,
    url: str = "https://example.com/cal.ics",
) -> httpx2.Response:
    return httpx2.Response(
        status_code,
        content=data,
        request=httpx2.Request("GET", url),
    )


def _fetch(ics_data: bytes, range_start: datetime, range_end: datetime):
    source = IcsUrlSource(url="https://example.com/cal.ics")
    with patch("zeitfenster.ics_client.httpx2.get") as mock_get:
        mock_get.return_value = _make_response(ics_data)
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

    def test_allday_events_block_full_day(self):
        intervals = _fetch(
            ALLDAY_ICS,
            datetime(2026, 7, 1, tzinfo=TZ),
            datetime(2026, 7, 2, tzinfo=TZ),
        )
        assert len(intervals) == 1
        assert intervals[0].start == datetime(2026, 7, 1, tzinfo=TZ)
        assert intervals[0].end == datetime(2026, 7, 2, tzinfo=TZ)

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

    def test_uses_timeout_and_disables_automatic_redirects(self):
        source = IcsUrlSource(url="https://example.com/cal.ics")

        with patch("zeitfenster.ics_client.httpx2.get") as mock_get:
            mock_get.return_value = _make_response(NO_EVENTS_ICS)
            fetch_busy_intervals_ics(
                source,
                datetime(2026, 7, 1, tzinfo=TZ),
                datetime(2026, 7, 2, tzinfo=TZ),
            )

        mock_get.assert_called_once_with(
            httpx2.URL("https://example.com/cal.ics"),
            timeout=10.0,
            follow_redirects=False,
        )

    def test_http_error_raises(self):
        source = IcsUrlSource(url="https://example.com/cal.ics")

        with patch("zeitfenster.ics_client.httpx2.get") as mock_get:
            mock_get.return_value = _make_response(b"not found", status_code=404)
            with pytest.raises(httpx2.HTTPStatusError):
                fetch_busy_intervals_ics(
                    source,
                    datetime(2026, 7, 1, tzinfo=TZ),
                    datetime(2026, 7, 2, tzinfo=TZ),
                )

    def test_follows_same_host_redirect(self):
        source = IcsUrlSource(url="https://example.com/cal.ics")
        redirect = httpx2.Response(
            302,
            headers={"location": "https://example.com/other/cal.ics"},
            request=httpx2.Request("GET", "https://example.com/cal.ics"),
        )

        with patch("zeitfenster.ics_client.httpx2.get") as mock_get:
            mock_get.side_effect = [
                redirect,
                _make_response(NO_EVENTS_ICS, url="https://example.com/other/cal.ics"),
            ]
            intervals = fetch_busy_intervals_ics(
                source,
                datetime(2026, 7, 1, tzinfo=TZ),
                datetime(2026, 7, 2, tzinfo=TZ),
            )

        assert intervals == []
        assert mock_get.call_count == 2

    def test_rejects_cross_host_redirect(self):
        source = IcsUrlSource(url="https://example.com/cal.ics")
        redirect = httpx2.Response(
            302,
            headers={"location": "https://internal.evil.example/steal"},
            request=httpx2.Request("GET", "https://example.com/cal.ics"),
        )

        with patch("zeitfenster.ics_client.httpx2.get") as mock_get:
            mock_get.return_value = redirect
            with pytest.raises(ValueError, match="cross-host"):
                fetch_busy_intervals_ics(
                    source,
                    datetime(2026, 7, 1, tzinfo=TZ),
                    datetime(2026, 7, 2, tzinfo=TZ),
                )

        mock_get.assert_called_once()

    def test_rejects_non_https_redirect(self):
        source = IcsUrlSource(url="https://example.com/cal.ics")
        redirect = httpx2.Response(
            302,
            headers={"location": "http://example.com/cal.ics"},
            request=httpx2.Request("GET", "https://example.com/cal.ics"),
        )

        with patch("zeitfenster.ics_client.httpx2.get") as mock_get:
            mock_get.return_value = redirect
            with pytest.raises(ValueError, match="non-https"):
                fetch_busy_intervals_ics(
                    source,
                    datetime(2026, 7, 1, tzinfo=TZ),
                    datetime(2026, 7, 2, tzinfo=TZ),
                )

        mock_get.assert_called_once()

    def test_rejects_too_many_redirects(self):
        source = IcsUrlSource(url="https://example.com/cal.ics")
        redirect = httpx2.Response(
            302,
            headers={"location": "https://example.com/cal.ics"},
            request=httpx2.Request("GET", "https://example.com/cal.ics"),
        )

        with patch("zeitfenster.ics_client.httpx2.get") as mock_get:
            mock_get.return_value = redirect
            with pytest.raises(ValueError, match="Too many redirects"):
                fetch_busy_intervals_ics(
                    source,
                    datetime(2026, 7, 1, tzinfo=TZ),
                    datetime(2026, 7, 2, tzinfo=TZ),
                )

        assert mock_get.call_count == 5
