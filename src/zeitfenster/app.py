from __future__ import annotations

import asyncio
import os
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path
from time import monotonic

import structlog
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from zeitfenster.availability import FreeSlot, fetch_and_compute
from zeitfenster.config import AppConfig
from zeitfenster.email import send_booking_email
from zeitfenster.generator import generate_placeholder, generate_site
from zeitfenster.ics import build_booking_ics
from zeitfenster.parsing import parse_duration

logger = structlog.get_logger()

CONFIG_PATH = Path(
    os.environ.get("ZEITFENSTER_CONFIG_PATH", "/etc/zeitfenster/config.yaml")
)
SITE_DIR = Path(os.environ.get("ZEITFENSTER_SITE_DIR", "/site"))
REGEN_INTERVAL_SECONDS = 900
BOOKING_RATE_LIMIT_MAX = int(os.environ.get("ZEITFENSTER_BOOKING_RATE_LIMIT_MAX", "5"))
BOOKING_RATE_LIMIT_WINDOW_SECONDS = int(
    os.environ.get("ZEITFENSTER_BOOKING_RATE_LIMIT_WINDOW_SECONDS", "300")
)
MAX_NAME_LENGTH = 100
MAX_EMAIL_LENGTH = 254
MAX_DATETIME_LENGTH = 64
MAX_DURATION_LENGTH = 16
MAX_HONEYPOT_LENGTH = 2048


async def _regenerate(app_instance: FastAPI) -> None:
    try:
        config: AppConfig = app_instance.state.config
        site_dir: Path = app_instance.state.site_dir
        slots = fetch_and_compute(config)
        app_instance.state.current_slots = slots
        generate_site(slots, config, site_dir)
    except Exception:
        logger.exception("regeneration_failed")


async def _periodic_regeneration(app_instance: FastAPI) -> None:
    while True:
        await asyncio.sleep(REGEN_INTERVAL_SECONDS)
        await _regenerate(app_instance)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    config_path = getattr(app.state, "config_path", CONFIG_PATH)
    site_dir = getattr(app.state, "site_dir", SITE_DIR)

    config = AppConfig.from_yaml(config_path)
    app.state.config = config
    app.state.site_dir = site_dir

    app.state.current_slots = {}
    app.state.booking_rate_limit_timestamps = deque()
    app.state.regeneration_task = None

    generate_placeholder(config, site_dir)

    for attempt in range(5):
        await _regenerate(app)
        if (site_dir / "thankyou.html").exists():
            break
        delay = 2**attempt
        logger.info("startup_regen_retry", attempt=attempt + 1, delay=delay)
        await asyncio.sleep(delay)

    task = asyncio.create_task(_periodic_regeneration(app))
    try:
        yield
    finally:
        task.cancel()
        scheduled: asyncio.Task[None] | None = getattr(
            app.state, "regeneration_task", None
        )
        if scheduled is not None and not scheduled.done():
            scheduled.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if scheduled is not None:
            try:
                await scheduled
            except asyncio.CancelledError:
                pass


app = FastAPI(lifespan=lifespan)


def _read_thankyou(site_dir: Path) -> str:
    thankyou_path = site_dir / "thankyou.html"
    if thankyou_path.exists():
        return thankyou_path.read_text()
    return "<html><body><h1>Thank you!</h1><p>Your booking request has been received.</p></body></html>"


async def _run_scheduled_regeneration(app_instance: FastAPI) -> None:
    try:
        await _regenerate(app_instance)
    finally:
        app_instance.state.regeneration_task = None


def _schedule_regeneration(app_instance: FastAPI) -> None:
    existing: asyncio.Task[None] | None = getattr(
        app_instance.state, "regeneration_task", None
    )
    if existing is not None and not existing.done():
        return
    app_instance.state.regeneration_task = asyncio.create_task(
        _run_scheduled_regeneration(app_instance)
    )


def _enforce_booking_rate_limit(app_instance: FastAPI) -> None:
    timestamps: deque[float] = getattr(
        app_instance.state, "booking_rate_limit_timestamps", deque()
    )
    app_instance.state.booking_rate_limit_timestamps = timestamps

    now = monotonic()
    window_start = now - BOOKING_RATE_LIMIT_WINDOW_SECONDS
    while timestamps and timestamps[0] <= window_start:
        timestamps.popleft()

    if len(timestamps) >= BOOKING_RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many booking requests")

    timestamps.append(now)


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _validate_bounded_field(
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


def _validate_customer_name(value: str) -> str:
    name = _validate_bounded_field(value, "name", MAX_NAME_LENGTH)
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if _has_control_characters(name):
        raise HTTPException(
            status_code=400,
            detail="name contains invalid characters",
        )
    return name


def _validate_customer_email(value: str) -> str:
    email = _validate_bounded_field(value, "email", MAX_EMAIL_LENGTH)
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
        or domain.startswith(".")
        or domain.endswith(".")
        or ".." in domain
    ):
        raise HTTPException(status_code=400, detail="Invalid email")

    return email


def _validate_booking_form_fields(
    *,
    name: str,
    email: str,
    slot_start: str,
    slot_end: str,
    duration: str,
    website: str,
) -> tuple[str, str, str, str, str, str]:
    validated_website = _validate_bounded_field(website, "website", MAX_HONEYPOT_LENGTH)
    if validated_website:
        return ("", "", "", "", "", validated_website)

    return (
        _validate_customer_name(name),
        _validate_customer_email(email),
        _validate_bounded_field(slot_start, "slot_start", MAX_DATETIME_LENGTH),
        _validate_bounded_field(slot_end, "slot_end", MAX_DATETIME_LENGTH),
        _validate_bounded_field(duration, "duration", MAX_DURATION_LENGTH),
        validated_website,
    )


def _parse_booking_datetime(value: str, field_name: str) -> datetime:
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


def _validate_requested_slot(
    *,
    request: Request,
    config: AppConfig,
    duration: str,
    start: datetime,
    end: datetime,
) -> None:
    if end <= start:
        raise HTTPException(status_code=400, detail="slot_end must be after slot_start")

    if duration not in config.rules.slot_durations:
        raise HTTPException(status_code=400, detail="Invalid duration")

    if end - start != parse_duration(duration):
        raise HTTPException(
            status_code=400,
            detail="Requested slot duration does not match",
        )

    current_slots: dict[str, list[FreeSlot]] = getattr(
        request.app.state, "current_slots", {}
    )
    matching_slots = current_slots.get(duration, [])
    if not any(slot.start == start and slot.end == end for slot in matching_slots):
        raise HTTPException(status_code=400, detail="Requested slot is not available")


@app.post("/book", response_class=HTMLResponse)
async def book(
    request: Request,
    name: str = Form(),
    email: str = Form(),
    slot_start: str = Form(),
    slot_end: str = Form(),
    duration: str = Form(),
    website: str = Form(default=""),
) -> HTMLResponse:
    config: AppConfig = request.app.state.config
    site_dir: Path = request.app.state.site_dir
    name, email, slot_start, slot_end, duration, website = (
        _validate_booking_form_fields(
            name=name,
            email=email,
            slot_start=slot_start,
            slot_end=slot_end,
            duration=duration,
            website=website,
        )
    )

    if website:
        logger.info("honeypot_triggered")
        return HTMLResponse(_read_thankyou(site_dir))

    start = _parse_booking_datetime(slot_start, "slot_start")
    end = _parse_booking_datetime(slot_end, "slot_end")
    _validate_requested_slot(
        request=request,
        config=config,
        duration=duration,
        start=start,
        end=end,
    )
    _enforce_booking_rate_limit(request.app)

    slot_summary = f"{start.strftime('%A, %B %-d %Y %H:%M')} – {end.strftime('%H:%M')}"

    ics_data = build_booking_ics(
        owner_email=config.email.owner_list[0],
        customer_name=name,
        customer_email=email,
        start=start,
        end=end,
        title=config.branding.title,
    )

    try:
        await send_booking_email(
            config=config.email,
            customer_name=name,
            customer_email=email,
            slot_summary=slot_summary,
            ics_data=ics_data,
        )
    except Exception:
        logger.exception("email_send_failed", customer=email, slot=slot_summary)

    _schedule_regeneration(request.app)

    return HTMLResponse(_read_thankyou(site_dir))


def _serialize_slots(
    slots: dict[str, list[FreeSlot]],
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for duration, slot_list in slots.items():
        result[duration] = [
            {"start": s.start.isoformat(), "end": s.end.isoformat()} for s in slot_list
        ]
    return result


@app.get("/api/free-slots")
async def free_slots(request: Request) -> dict:
    current: dict[str, list[FreeSlot]] = getattr(request.app.state, "current_slots", {})
    return {"slots": _serialize_slots(current)}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
