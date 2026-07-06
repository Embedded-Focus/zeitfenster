import uuid
from datetime import datetime
from email.utils import parseaddr

from icalendar import Calendar, Event, vCalAddress, vText


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
