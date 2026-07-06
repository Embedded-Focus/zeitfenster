import uuid
from datetime import date, datetime, tzinfo
from email.utils import parseaddr

from icalendar import Calendar, Event, Timezone, vCalAddress, vText


def _add_attendee(
    event: Event,
    *,
    email: str,
    name: str,
    role: str,
    partstat: str,
) -> None:
    attendee = vCalAddress(f"mailto:{email}")
    attendee.params["cn"] = vText(name)
    attendee.params["role"] = vText(role)
    attendee.params["partstat"] = vText(partstat)
    event.add("attendee", attendee, encode=False)


def normalize_mailbox(value: str) -> tuple[str, str | None]:
    parsed_name, parsed_email = parseaddr(value)
    email = parsed_email or value.strip()
    name = parsed_name or None
    return email, name


def _timezone_cache_key(value: tzinfo) -> str:
    return getattr(value, "key", None) or getattr(value, "zone", None) or str(value)


def _uses_utc_suffix(value: datetime) -> bool:
    if value.tzinfo is None:
        return False
    offset = value.utcoffset()
    return offset is not None and offset.total_seconds() == 0


def _add_event_timezones(cal: Calendar, start: datetime, end: datetime) -> None:
    first_date = date(min(start.year, end.year), 1, 1)
    last_date = date(max(start.year, end.year) + 1, 1, 1)
    seen: set[str] = set()

    for value in (start, end):
        if value.tzinfo is None or value.utcoffset() is None or _uses_utc_suffix(value):
            continue

        cache_key = _timezone_cache_key(value.tzinfo)
        if cache_key in seen:
            continue

        timezone = Timezone.from_tzinfo(
            value.tzinfo,
            first_date=first_date,
            last_date=last_date,
        )
        seen.add(cache_key)
        cal.add_component(timezone)


def build_booking_ics(
    owner_email: str,
    customer_name: str,
    customer_email: str,
    start: datetime,
    end: datetime,
    owner_name: str | None = None,
    summary_template: str = "{customer_name}",
    location: str | None = None,
    description_template: str = "",
) -> bytes:
    owner_email, parsed_owner_name = normalize_mailbox(owner_email)
    owner_display_name = owner_name or parsed_owner_name or owner_email

    cal = Calendar()
    cal.add("prodid", "-//Zeitfenster//Booking//EN")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    _add_event_timezones(cal, start, end)

    event = Event()
    event.add("uid", str(uuid.uuid4()))
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add(
        "summary",
        summary_template.format(
            customer_name=customer_name,
            customer_email=customer_email,
            owner_name=owner_name or "",
            owner_email=owner_email,
        ),
    )
    event.add(
        "description",
        description_template.format(
            customer_name=customer_name,
            customer_email=customer_email,
        ),
    )
    if location:
        event.add("location", location)

    organizer = vCalAddress(f"mailto:{owner_email}")
    organizer.params["cn"] = vText(owner_display_name)
    event.add("organizer", organizer)

    _add_attendee(
        event,
        email=owner_email,
        name=owner_display_name,
        role="CHAIR",
        partstat="ACCEPTED",
    )
    _add_attendee(
        event,
        email=customer_email,
        name=customer_name,
        role="REQ-PARTICIPANT",
        partstat="NEEDS-ACTION",
    )

    cal.add_component(event)
    return cal.to_ical()
