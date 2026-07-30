from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from zeitfenster.availability import FreeSlot
from zeitfenster.booking_request import (
    parse_booking_datetime,
    validate_booking_form_fields,
    validate_requested_slot,
)

TZ = ZoneInfo("Europe/Vienna")


def test_validate_booking_form_fields_normalizes_enabled_message():
    fields = validate_booking_form_fields(
        message_enabled=True,
        name="  Alice  ",
        email="  alice@example.com  ",
        description="  Project kickoff\r\nBring notes\tplease  ",
        slot_start="  2026-07-06T10:00:00+02:00  ",
        slot_end="  2026-07-06T11:00:00+02:00  ",
        duration="  60m  ",
        website="",
    )

    assert fields.name == "Alice"
    assert fields.email == "alice@example.com"
    assert fields.description == "Project kickoff\nBring notes\tplease"
    assert fields.slot_start == "2026-07-06T10:00:00+02:00"
    assert fields.slot_end == "2026-07-06T11:00:00+02:00"
    assert fields.duration == "60m"
    assert fields.website == ""


def test_validate_booking_form_fields_ignores_message_when_disabled():
    fields = validate_booking_form_fields(
        message_enabled=False,
        name="Alice",
        email="alice@example.com",
        description="Direct post message",
        slot_start="2026-07-06T10:00:00+02:00",
        slot_end="2026-07-06T11:00:00+02:00",
        duration="60m",
        website="",
    )

    assert fields.description == ""


def test_validate_booking_form_fields_honeypot_short_circuits_other_fields():
    fields = validate_booking_form_fields(
        message_enabled=True,
        name="",
        email="not-an-email",
        description="x" * 1001,
        slot_start="not-a-date",
        slot_end="not-a-date",
        duration="x" * 17,
        website="https://spam.example.com",
    )

    assert fields.website == "https://spam.example.com"
    assert fields.name == ""
    assert fields.email == ""
    assert fields.description == ""


@pytest.mark.parametrize(
    ("description", "detail"),
    [
        ("x" * 1001, "description is too long"),
        ("Project kickoff\x00", "description contains invalid characters"),
    ],
)
def test_validate_booking_form_fields_rejects_invalid_message(description, detail):
    with pytest.raises(HTTPException) as exc_info:
        validate_booking_form_fields(
            message_enabled=True,
            name="Alice",
            email="alice@example.com",
            description=description,
            slot_start="2026-07-06T10:00:00+02:00",
            slot_end="2026-07-06T11:00:00+02:00",
            duration="60m",
            website="",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == detail


def test_parse_booking_datetime_requires_timezone():
    with pytest.raises(HTTPException) as exc_info:
        parse_booking_datetime("2026-07-06T10:00:00", "slot_start")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "slot_start must include a timezone"


def test_validate_requested_slot_returns_matching_slot():
    slot = FreeSlot(
        start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
        end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        duration=timedelta(hours=1),
    )

    assert (
        validate_requested_slot(
            current_slots={"60m": [slot]},
            configured_durations=["60m"],
            duration="60m",
            start=slot.start,
            end=slot.end,
        )
        == slot
    )


def test_validate_requested_slot_rejects_unavailable_slot():
    with pytest.raises(HTTPException) as exc_info:
        validate_requested_slot(
            current_slots={"60m": []},
            configured_durations=["60m"],
            duration="60m",
            start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Requested slot is not available"
