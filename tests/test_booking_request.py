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


def _valid_form_data(**overrides):
    data = {
        "message_enabled": False,
        "name": "Alice",
        "email": "alice@example.com",
        "description": "",
        "slot_start": "2026-07-06T10:00:00+02:00",
        "slot_end": "2026-07-06T11:00:00+02:00",
        "duration": "60m",
        "website": "",
    }
    data.update(overrides)
    return data


def _assert_http_error(exc_info, *, status_code: int, detail: str):
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == detail


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


@pytest.mark.parametrize(
    ("field", "value", "detail"),
    [
        ("name", "   ", "name is required"),
        ("name", "A" * 101, "name is too long"),
        ("name", "Alice\nBob", "name contains invalid characters"),
        ("email", "x", "email is too short"),
        ("email", "not-an-email", "Invalid email"),
        ("email", "foo@bar", "Invalid email"),
        ("email", "alice bob@example.com", "Invalid email"),
        ("email", "a" * 247 + "@example.com", "email is too long"),
        ("slot_start", "2" * 65, "slot_start is too long"),
        ("slot_end", "2" * 65, "slot_end is too long"),
        ("duration", "x" * 17, "duration is too long"),
        ("website", "x" * 2049, "website is too long"),
    ],
)
def test_validate_booking_form_fields_rejects_invalid_fields(field, value, detail):
    with pytest.raises(HTTPException) as exc_info:
        validate_booking_form_fields(**_valid_form_data(**{field: value}))

    _assert_http_error(exc_info, status_code=400, detail=detail)


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
            **_valid_form_data(message_enabled=True, description=description)
        )

    _assert_http_error(exc_info, status_code=400, detail=detail)


@pytest.mark.parametrize(
    ("value", "field_name", "detail"),
    [
        ("not-a-date", "slot_start", "Invalid slot_start"),
        ("not-a-date", "slot_end", "Invalid slot_end"),
        ("2026-07-06T10:00:00", "slot_start", "slot_start must include a timezone"),
        ("2026-07-06T11:00:00", "slot_end", "slot_end must include a timezone"),
    ],
)
def test_parse_booking_datetime_rejects_invalid_values(value, field_name, detail):
    with pytest.raises(HTTPException) as exc_info:
        parse_booking_datetime(value, field_name)

    _assert_http_error(exc_info, status_code=400, detail=detail)


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


@pytest.mark.parametrize(
    ("current_slots", "configured_durations", "duration", "start", "end", "detail"),
    [
        (
            {"60m": []},
            ["60m"],
            "60m",
            datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
            "Requested slot is not available",
        ),
        (
            {"60m": []},
            ["60m"],
            "90m",
            datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
            "Invalid duration",
        ),
        (
            {
                "60m": [
                    FreeSlot(
                        start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
                        end=datetime(2026, 7, 6, 12, 0, tzinfo=TZ),
                        duration=timedelta(hours=2),
                    ),
                ]
            },
            ["60m"],
            "60m",
            datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            datetime(2026, 7, 6, 12, 0, tzinfo=TZ),
            "Requested slot duration does not match",
        ),
        (
            {"60m": []},
            ["60m"],
            "60m",
            datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
            datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
            "slot_end must be after slot_start",
        ),
    ],
)
def test_validate_requested_slot_rejects_invalid_requests(
    current_slots,
    configured_durations,
    duration,
    start,
    end,
    detail,
):
    with pytest.raises(HTTPException) as exc_info:
        validate_requested_slot(
            current_slots=current_slots,
            configured_durations=configured_durations,
            duration=duration,
            start=start,
            end=end,
        )

    _assert_http_error(exc_info, status_code=400, detail=detail)
