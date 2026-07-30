from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr

from fastapi import HTTPException

from zeitfenster.availability import FreeSlot
from zeitfenster.parsing import parse_duration

MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 254
MAX_DESCRIPTION_LENGTH = 1000
MAX_DATETIME_LENGTH = 64
MAX_DURATION_LENGTH = 16
MAX_HONEYPOT_LENGTH = 2048


@dataclass(frozen=True)
class BookingFormFields:
    name: str
    email: str
    description: str
    slot_start: str
    slot_end: str
    duration: str
    website: str


def validate_bounded_field(
    value: str,
    field_name: str,
    max_length: int,
) -> str:
    normalized = value.strip()
    if len(normalized) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} is too long",
        )
    return normalized


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _validate_customer_name(value: str) -> str:
    name = validate_bounded_field(value, "name", MAX_NAME_LENGTH)
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if _has_control_characters(name):
        raise HTTPException(
            status_code=400,
            detail="name contains invalid characters",
        )
    return name


def _validate_customer_email(value: str) -> str:
    email = validate_bounded_field(value, "email", MAX_EMAIL_LENGTH)
    if len(email) < 3:
        raise HTTPException(status_code=400, detail="email is too short")
    if _has_control_characters(email) or any(char.isspace() for char in email):
        raise HTTPException(status_code=400, detail="Invalid email")

    display_name, parsed_email = parseaddr(email)
    if display_name or parsed_email != email or email.count("@") != 1:
        raise HTTPException(status_code=400, detail="Invalid email")

    local_part, domain = email.rsplit("@", 1)
    if (
        not local_part
        or not domain
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
        or ".." in domain
    ):
        raise HTTPException(status_code=400, detail="Invalid email")

    return email


def _validate_customer_description(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(normalized) > MAX_DESCRIPTION_LENGTH:
        raise HTTPException(status_code=400, detail="description is too long")

    for char in normalized:
        if char in {"\n", "\t"}:
            continue
        if ord(char) < 32 or ord(char) == 127:
            raise HTTPException(
                status_code=400,
                detail="description contains invalid characters",
            )

    return normalized


def validate_booking_form_fields(
    *,
    message_enabled: bool,
    name: str,
    email: str,
    description: str,
    slot_start: str,
    slot_end: str,
    duration: str,
    website: str,
) -> BookingFormFields:
    validated_website = validate_bounded_field(
        website,
        "website",
        MAX_HONEYPOT_LENGTH,
    )
    if validated_website:
        return BookingFormFields(
            name="",
            email="",
            description="",
            slot_start="",
            slot_end="",
            duration="",
            website=validated_website,
        )

    return BookingFormFields(
        name=_validate_customer_name(name),
        email=_validate_customer_email(email),
        description=(
            _validate_customer_description(description) if message_enabled else ""
        ),
        slot_start=validate_bounded_field(
            slot_start,
            "slot_start",
            MAX_DATETIME_LENGTH,
        ),
        slot_end=validate_bounded_field(slot_end, "slot_end", MAX_DATETIME_LENGTH),
        duration=validate_bounded_field(duration, "duration", MAX_DURATION_LENGTH),
        website=validated_website,
    )


def parse_booking_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must include a timezone",
        )
    return parsed


def validate_requested_slot(
    *,
    current_slots: dict[str, list[FreeSlot]],
    configured_durations: list[str],
    duration: str,
    start: datetime,
    end: datetime,
) -> FreeSlot:
    if end <= start:
        raise HTTPException(status_code=400, detail="slot_end must be after slot_start")

    if duration not in configured_durations:
        raise HTTPException(status_code=400, detail="Invalid duration")

    if end - start != parse_duration(duration):
        raise HTTPException(
            status_code=400,
            detail="Requested slot duration does not match",
        )

    matching_slots = current_slots.get(duration, [])
    for slot in matching_slots:
        if slot.start == start and slot.end == end:
            return slot

    raise HTTPException(status_code=400, detail="Requested slot is not available")
