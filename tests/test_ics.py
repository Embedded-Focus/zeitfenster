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
        assert cal["method"] == "PUBLISH"

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

    def test_organizer_owner_attendee_and_customer_attendee(self):
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

        attendees = event["attendee"]
        assert len(attendees) == 2

        owner_attendee = next(
            attendee for attendee in attendees if "owner@example.com" in str(attendee)
        )
        assert owner_attendee.params["CN"] == "owner@example.com"
        assert owner_attendee.params["ROLE"] == "CHAIR"
        assert owner_attendee.params["PARTSTAT"] == "ACCEPTED"

        customer_attendee = next(
            attendee for attendee in attendees if "alice@example.com" in str(attendee)
        )
        assert customer_attendee.params["CN"] == "Alice"
        assert customer_attendee.params["ROLE"] == "REQ-PARTICIPANT"
        assert customer_attendee.params["PARTSTAT"] == "NEEDS-ACTION"

    def test_description_is_empty_by_default(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]

        assert str(event["description"]) == ""

    def test_configured_description_and_location(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
            location="https://meet.example.com/room",
            description_template=(
                "Request from {customer_name} at {customer_email}.\n"
                "Meeting link already configured."
            ),
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]

        assert event["location"] == "https://meet.example.com/room"
        assert "Request from Alice at alice@example.com." in str(event["description"])
        assert "Meeting link already configured." in str(event["description"])

    def test_summary_includes_customer_and_owner_names(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            owner_name="Jane Doe",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
            summary_template="{customer_name} and {owner_name}",
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["summary"]) == "Alice and Jane Doe"

    def test_owner_attendee_uses_configured_owner_name(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            owner_name="Jane Doe",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        owner_attendee = next(
            attendee
            for attendee in event["attendee"]
            if "owner@example.com" in str(attendee)
        )
        assert owner_attendee.params["CN"] == "Jane Doe"

    def test_organizer_uses_configured_owner_name(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            owner_name="Jane Doe",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]

        assert event["organizer"].params["CN"] == "Jane Doe"

    def test_rfc_style_owner_mailbox_is_normalized(self):
        data = build_booking_ics(
            owner_email="Jane Doe <jane.doe@example.com>",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]

        organizer = event["organizer"]
        assert str(organizer) == "mailto:jane.doe@example.com"
        assert organizer.params["CN"] == "Jane Doe"

        owner_attendee = next(
            attendee
            for attendee in event["attendee"]
            if "jane.doe@example.com" in str(attendee)
        )
        assert str(owner_attendee) == "mailto:jane.doe@example.com"
        assert owner_attendee.params["CN"] == "Jane Doe"
        assert "Jane Doe <jane.doe@example.com>" not in data.decode()

    def test_summary_defaults_to_customer_name(self):
        data = build_booking_ics(
            owner_email="owner@example.com",
            customer_name="Alice",
            customer_email="alice@example.com",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        )
        cal = Calendar.from_ical(data)
        event = [c for c in cal.walk() if c.name == "VEVENT"][0]
        assert str(event["summary"]) == "Alice"

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
