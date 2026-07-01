from email.message import EmailMessage

import aiosmtplib
import structlog

from zeitfenster.config import Email as EmailConfig

logger = structlog.get_logger()


async def send_booking_email(
    config: EmailConfig,
    customer_name: str,
    customer_email: str,
    slot_summary: str,
    ics_data: bytes,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"Booking Request: {customer_name} – {slot_summary}"
    msg["From"] = config.smtp_user
    msg["To"] = ", ".join(config.owner_list)

    msg.set_content(
        f"New booking request:\n\n"
        f"Name: {customer_name}\n"
        f"Email: {customer_email}\n"
        f"Slot: {slot_summary}\n\n"
        f"Import the attached .ics file to send a calendar invitation."
    )

    msg.add_attachment(
        ics_data,
        maintype="text",
        subtype="calendar",
        filename="booking.ics",
    )

    logger.info(
        "sending_booking_email",
        to=config.owner_list,
        customer=customer_email,
        slot=slot_summary,
    )

    await aiosmtplib.send(
        msg,
        hostname=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_user if config.smtp_start_tls else None,
        password=config.smtp_password if config.smtp_start_tls else None,
        start_tls=config.smtp_start_tls,
    )

    logger.info("booking_email_sent", to=config.owner_list)
