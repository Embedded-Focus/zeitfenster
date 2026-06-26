from __future__ import annotations

import uuid
from datetime import datetime

from icalendar import Calendar, Event, vCalAddress, vText


def build_booking_ics(
    owner_email: str,
    customer_name: str,
    customer_email: str,
    start: datetime,
    end: datetime,
    title: str = "Booking Request",
) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//Zeitfenster//Booking//EN")
    cal.add("version", "2.0")
    cal.add("method", "REQUEST")

    event = Event()
    event.add("uid", str(uuid.uuid4()))
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("summary", f"{title}: {customer_name}")
    event.add("description", f"Booking request from {customer_name} <{customer_email}>")

    organizer = vCalAddress(f"mailto:{owner_email}")
    organizer.params["cn"] = vText(owner_email)
    event.add("organizer", organizer)

    attendee = vCalAddress(f"mailto:{customer_email}")
    attendee.params["cn"] = vText(customer_name)
    attendee.params["partstat"] = vText("NEEDS-ACTION")
    attendee.params["rsvp"] = vText("TRUE")
    event.add("attendee", attendee)

    cal.add_component(event)
    return cal.to_ical()
