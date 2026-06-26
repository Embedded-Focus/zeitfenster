from datetime import datetime
from zoneinfo import ZoneInfo

from icalendar import Calendar

from zeitfenster.ics import build_booking_ics

TZ = ZoneInfo("Europe/Vienna")


class TestBuildBookingIcs:
    def test_produces_valid_icalendar(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        )
        cal = Calendar.from_ical(data)
        assert cal["prodid"] == "-//Zeitfenster//Booking//EN"
        assert cal["version"] == "2.0"
        assert cal["method"] == "REQUEST"

    def test_event_times(self):
        start = datetime(2026, 7, 6, 10, 0, tzinfo=TZ)
        end = datetime(2026, 7, 6, 11, 0, tzinfo=TZ)
        data = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=start,
            end=end,
        )
        cal = Calendar.from_ical(data)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1
        event = events[0]
        assert event["dtstart"].dt == start
        assert event["dtend"].dt == end

    def test_organizer_and_attendee(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]

        organizer = event["organizer"]
        assert "owner@example.com" in str(organizer)

        attendee = event["attendee"]
        assert "alice@example.com" in str(attendee)
        assert attendee.params["cn"] == "Alice"
        assert attendee.params["partstat"] == "NEEDS-ACTION"

    def test_summary_includes_customer_name(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
            title="Book a Meeting",
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert "Alice" in str(event["summary"])
        assert "Book a Meeting" in str(event["summary"])

    def test_uid_is_unique(self):
        start = datetime(2026, 7, 6, 10, 0, tzinfo=TZ)
        end = datetime(2026, 7, 6, 11, 0, tzinfo=TZ)
        data1 = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=start,
            end=end,
        )
        data2 = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=start,
            end=end,
        )
        cal1 = Calendar.from_ical(data1)
        cal2 = Calendar.from_ical(data2)
        ev1 = [c for c in cal1.walk() if c.name == "VEVENT"][0]
        ev2 = [c for c in cal2.walk() if c.name == "VEVENT"][0]
        assert str(ev1["uid"]) != str(ev2["uid"])
