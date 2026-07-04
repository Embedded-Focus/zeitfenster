from unittest.mock import AsyncMock, patch

import pytest

from zeitfenster.config import Email
from zeitfenster.email import send_booking_email


@pytest.mark.asyncio
async def test_booking_email_explains_draft_ics_workflow(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    config = Email(owner="owner@example.com")

    with patch("zeitfenster.email.aiosmtplib.send", new_callable=AsyncMock) as send:
        await send_booking_email(
            config=config,
            customer_name="Alice",
            customer_email="alice@example.com",
            slot_summary="Monday, July 6 2026 10:00 - 11:00",
            ics_data=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
        )

    message = send.call_args.args[0]
    body = message.get_body(preferencelist=("plain",)).get_content()

    assert message["From"] == "Zeitfenster <sender@example.com>"
    assert "The attached .ics file is a draft event" in body
    assert "Add the attached .ics file to your calendar." in body
    assert "Edit the added event" in body
    assert "Save or send the updated event" in body
    assert "send the actual invitations to the attendees" in body
    assert "invite the customer from your calendar client" not in body

    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "booking.ics"


@pytest.mark.asyncio
async def test_booking_email_uses_configured_from_name(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    config = Email(owner="owner@example.com", from_name="Booking Desk")

    with patch("zeitfenster.email.aiosmtplib.send", new_callable=AsyncMock) as send:
        await send_booking_email(
            config=config,
            customer_name="Alice",
            customer_email="alice@example.com",
            slot_summary="Monday, July 6 2026 10:00 - 11:00",
            ics_data=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
        )

    message = send.call_args.args[0]
    assert message["From"] == "Booking Desk <sender@example.com>"
