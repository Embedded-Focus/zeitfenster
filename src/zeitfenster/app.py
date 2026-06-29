from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import structlog
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from zeitfenster.availability import FreeSlot, fetch_and_compute
from zeitfenster.config import AppConfig
from zeitfenster.email import send_booking_email
from zeitfenster.generator import generate_placeholder, generate_site
from zeitfenster.ics import build_booking_ics

logger = structlog.get_logger()

CONFIG_PATH = Path(
    os.environ.get("ZEITFENSTER_CONFIG_PATH", "/etc/zeitfenster/config.yaml")
)
SITE_DIR = Path(os.environ.get("ZEITFENSTER_SITE_DIR", "/site"))
REGEN_INTERVAL_SECONDS = 900


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
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)


def _read_thankyou(site_dir: Path) -> str:
    thankyou_path = site_dir / "thankyou.html"
    if thankyou_path.exists():
        return thankyou_path.read_text()
    return "<html><body><h1>Thank you!</h1><p>Your booking request has been received.</p></body></html>"


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

    if website:
        logger.info("honeypot_triggered", name=name)
        return HTMLResponse(_read_thankyou(site_dir))

    start = datetime.fromisoformat(slot_start)
    end = datetime.fromisoformat(slot_end)

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

    asyncio.create_task(_regenerate(request.app))

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
