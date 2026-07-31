from collections import deque
from dataclasses import dataclass

import structlog
from fastapi import HTTPException

from zeitfenster.availability import FreeSlot
from zeitfenster.booking_request import (
    parse_booking_datetime,
    validate_booking_form_fields,
    validate_requested_slot,
)
from zeitfenster.captcha import verify_captcha_token
from zeitfenster.config import AppConfig
from zeitfenster.email import send_booking_email
from zeitfenster.ics import build_booking_ics, normalize_mailbox
from zeitfenster.nextcloud_talk_client import (
    NextcloudTalkBookingContext,
    NextcloudTalkError,
    create_talk_room,
)
from zeitfenster.rate_limit import enforce_booking_rate_limit

logger = structlog.get_logger()


@dataclass(frozen=True)
class RawBookingForm:
    name: str
    email: str
    description: str
    slot_start: str
    slot_end: str
    duration: str
    website: str
    cap_token: str


@dataclass(frozen=True)
class BookingRequestResult:
    honeypot_triggered: bool = False
    accepted: bool = False


async def handle_booking_request(
    *,
    config: AppConfig,
    current_slots: dict[str, list[FreeSlot]],
    booking_rate_limit_timestamps: deque[float],
    booking_rate_limit_max: int,
    booking_rate_limit_window_seconds: int,
    form: RawBookingForm,
) -> BookingRequestResult:
    form_fields = validate_booking_form_fields(
        message_enabled=config.booking.message_enabled,
        name=form.name,
        email=form.email,
        description=form.description,
        slot_start=form.slot_start,
        slot_end=form.slot_end,
        duration=form.duration,
        website=form.website,
    )

    if form_fields.website:
        logger.info("honeypot_triggered")
        return BookingRequestResult(honeypot_triggered=True)

    await verify_captcha_token(config, form.cap_token)

    start = parse_booking_datetime(form_fields.slot_start, "slot_start")
    end = parse_booking_datetime(form_fields.slot_end, "slot_end")
    requested_slot = validate_requested_slot(
        current_slots=current_slots,
        configured_durations=config.rules.slot_durations,
        duration=form_fields.duration,
        start=start,
        end=end,
    )
    enforce_booking_rate_limit(
        booking_rate_limit_timestamps,
        max_requests=booking_rate_limit_max,
        window_seconds=booking_rate_limit_window_seconds,
    )

    slot_summary = f"{start.strftime('%A, %B %-d %Y %H:%M')} – {end.strftime('%H:%M')}"

    owner_email, parsed_owner_name = normalize_mailbox(config.email.owner_list[0])
    owner_name = config.booking.owner_name or parsed_owner_name
    owner_display_name = owner_name or owner_email
    meeting_url = None

    if config.nextcloud_talk.enabled:
        try:
            meeting_url = await create_talk_room(
                config=config.nextcloud_talk,
                context=NextcloudTalkBookingContext(
                    customer_name=form_fields.name,
                    customer_email=form_fields.email,
                    customer_description=form_fields.description,
                    owner_name=owner_display_name,
                    owner_email=owner_email,
                    slot_start=requested_slot.start,
                    slot_end=requested_slot.end,
                ),
            )
        except NextcloudTalkError as exc:
            logger.warning("nextcloud_talk_room_creation_failed", error=str(exc))
            if config.nextcloud_talk.required:
                raise HTTPException(
                    status_code=503,
                    detail="Nextcloud Talk room creation is unavailable",
                ) from exc

    ics_data = build_booking_ics(
        owner_email=owner_email,
        owner_name=owner_name,
        customer_name=form_fields.name,
        customer_email=form_fields.email,
        customer_description=form_fields.description,
        start=requested_slot.start,
        end=requested_slot.end,
        summary_template=config.booking.summary_template,
        location=config.booking.location,
        description_template=config.booking.description_template,
        meeting_url=meeting_url,
    )

    try:
        await send_booking_email(
            config=config.email,
            customer_name=form_fields.name,
            customer_email=form_fields.email,
            customer_description=form_fields.description,
            slot_summary=slot_summary,
            ics_data=ics_data,
            meeting_url=meeting_url,
        )
    except Exception:
        logger.exception(
            "email_send_failed",
            customer=form_fields.email,
            slot=slot_summary,
        )

    return BookingRequestResult(accepted=True)
