import asyncio
import hmac
import os
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from zeitfenster.availability import FreeSlot, fetch_and_compute
from zeitfenster.booking_service import (
    RawBookingForm,
    handle_booking_request,
)
from zeitfenster.config import AppConfig
from zeitfenster.generator import generate_placeholder, generate_site
from zeitfenster.parsing import parse_duration

logger = structlog.get_logger()

CONFIG_PATH = Path(
    os.environ.get("ZEITFENSTER_CONFIG_PATH", "/etc/zeitfenster/config.yaml")
)
SITE_DIR = Path(os.environ.get("ZEITFENSTER_SITE_DIR", "/site"))
CUSTOM_STATIC_DIR = os.environ.get("ZEITFENSTER_CUSTOM_STATIC_DIR")
BOOKING_RATE_LIMIT_MAX = int(os.environ.get("ZEITFENSTER_BOOKING_RATE_LIMIT_MAX", "5"))
BOOKING_RATE_LIMIT_WINDOW_SECONDS = int(
    os.environ.get("ZEITFENSTER_BOOKING_RATE_LIMIT_WINDOW_SECONDS", "300")
)
STARTUP_REGEN_MAX_ATTEMPTS = int(
    os.environ.get("ZEITFENSTER_STARTUP_REGEN_MAX_ATTEMPTS", "10")
)
STARTUP_REGEN_INITIAL_DELAY_SECONDS = float(
    os.environ.get("ZEITFENSTER_STARTUP_REGEN_INITIAL_DELAY_SECONDS", "1")
)


async def _regenerate(app_instance: FastAPI) -> bool:
    try:
        config: AppConfig = app_instance.state.config
        site_dir: Path = app_instance.state.site_dir
        custom_static_dir: Path | None = app_instance.state.custom_static_dir
        slots = fetch_and_compute(config)
        app_instance.state.current_slots = slots
        generate_site(slots, config, site_dir, custom_static_dir)
        return True
    except Exception:
        logger.exception("regeneration_failed")
        return False


def _refresh_interval_seconds(config: AppConfig) -> float:
    seconds = parse_duration(config.rules.refresh_interval).total_seconds()
    if seconds <= 0:
        raise ValueError("rules.refresh_interval must be greater than 0")
    return seconds


async def _periodic_regeneration(app_instance: FastAPI) -> None:
    while True:
        await asyncio.sleep(app_instance.state.refresh_interval_seconds)
        await _regenerate(app_instance)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    config_path = getattr(app.state, "config_path", CONFIG_PATH)
    site_dir = getattr(app.state, "site_dir", SITE_DIR)
    custom_static_dir = getattr(
        app.state,
        "custom_static_dir",
        Path(CUSTOM_STATIC_DIR) if CUSTOM_STATIC_DIR else None,
    )

    config = AppConfig.from_yaml(config_path)
    app.state.config = config
    app.state.site_dir = site_dir
    app.state.custom_static_dir = custom_static_dir
    app.state.refresh_interval_seconds = _refresh_interval_seconds(config)
    logger.info(
        "refresh_interval_configured",
        interval=config.rules.refresh_interval,
        interval_seconds=app.state.refresh_interval_seconds,
    )
    free_slots_auth_enabled = config.federation.free_slots_token is not None
    logger.info(
        "free_slots_auth_configured",
        enabled=free_slots_auth_enabled,
    )
    if not (config.email.smtp_start_tls or config.email.smtp_use_tls):
        logger.warning(
            "smtp_encryption_disabled",
            message=(
                "SMTP transport encryption is disabled; booking emails "
                "(customer name, email, and slot time) will be sent in "
                "plaintext. This is only allowed when SMTP authentication "
                "is disabled."
            ),
        )

    app.state.current_slots = {}
    app.state.booking_rate_limit_timestamps = deque()
    app.state.regeneration_task = None

    generate_placeholder(config, site_dir, custom_static_dir)

    for attempt in range(STARTUP_REGEN_MAX_ATTEMPTS):
        if await _regenerate(app):
            break
        delay = STARTUP_REGEN_INITIAL_DELAY_SECONDS * (2**attempt)
        if attempt + 1 >= STARTUP_REGEN_MAX_ATTEMPTS:
            continue
        logger.info("startup_regen_retry", attempt=attempt + 1, delay=delay)
        await asyncio.sleep(delay)
    else:
        logger.warning("startup_regen_retries_exhausted")

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
    return "<html><body><h1>Thank you!</h1><p>Your meeting request has been received.</p><p>The meeting is not confirmed until you receive a calendar invitation.</p></body></html>"


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


@app.post("/book", response_class=HTMLResponse)
async def book(
    request: Request,
    name: str = Form(),
    email: str = Form(),
    description: str = Form(default=""),
    slot_start: str = Form(),
    slot_end: str = Form(),
    duration: str = Form(),
    website: str = Form(default=""),
    cap_token: str = Form(default="", alias="cap-token"),
) -> HTMLResponse:
    config: AppConfig = request.app.state.config
    site_dir: Path = request.app.state.site_dir
    current_slots: dict[str, list[FreeSlot]] = getattr(
        request.app.state,
        "current_slots",
        {},
    )
    booking_rate_limit_timestamps: deque[float] = getattr(
        request.app.state,
        "booking_rate_limit_timestamps",
        deque(),
    )
    request.app.state.booking_rate_limit_timestamps = booking_rate_limit_timestamps

    result = await handle_booking_request(
        config=config,
        current_slots=current_slots,
        booking_rate_limit_timestamps=booking_rate_limit_timestamps,
        booking_rate_limit_max=BOOKING_RATE_LIMIT_MAX,
        booking_rate_limit_window_seconds=BOOKING_RATE_LIMIT_WINDOW_SECONDS,
        form=RawBookingForm(
            name=name,
            email=email,
            description=description,
            slot_start=slot_start,
            slot_end=slot_end,
            duration=duration,
            website=website,
            cap_token=cap_token,
        ),
    )

    if result.honeypot_triggered:
        return HTMLResponse(_read_thankyou(site_dir))

    if result.accepted:
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


def _validate_free_slots_authorization(request: Request, config: AppConfig) -> None:
    expected_token = config.federation.free_slots_token
    if expected_token is None:
        return

    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not hmac.compare_digest(token, expected_token)
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/api/free-slots")
async def free_slots(request: Request) -> dict:
    config: AppConfig = request.app.state.config
    _validate_free_slots_authorization(request, config)
    current: dict[str, list[FreeSlot]] = getattr(request.app.state, "current_slots", {})
    return {"slots": _serialize_slots(current)}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
