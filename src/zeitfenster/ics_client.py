from datetime import date, datetime, time, tzinfo

import httpx2
import recurring_ical_events
import structlog
from icalendar import Calendar

from zeitfenster.caldav_client import BusyInterval
from zeitfenster.config import IcsUrlSource

logger = structlog.get_logger()
ICS_FETCH_TIMEOUT_SECONDS = 10.0
MAX_ICS_REDIRECTS = 5


def _reject_non_https(url: httpx2.URL, context: str) -> None:
    if url.scheme != "https":
        raise ValueError(f"Refusing to fetch non-https ICS URL ({context}): {url}")


def _fetch_ics_response(url: str) -> httpx2.Response:
    current = httpx2.URL(url)
    _reject_non_https(current, "source")
    original_host = current.host

    for _ in range(MAX_ICS_REDIRECTS):
        response = httpx2.get(
            current, timeout=ICS_FETCH_TIMEOUT_SECONDS, follow_redirects=False
        )
        if not response.has_redirect_location:
            return response

        target = response.url.join(response.headers["location"])
        _reject_non_https(target, "redirect")
        if target.host != original_host:
            raise ValueError(
                f"Refusing to follow cross-host ICS redirect from "
                f"{original_host!r} to {target.host!r}"
            )
        current = target

    raise ValueError(f"Too many redirects fetching ICS URL: {url!r}")


def _coerce_calendar_datetime(
    value: date | datetime,
    default_timezone: tzinfo | None = None,
) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=default_timezone)
    return None


def fetch_busy_intervals_ics(
    source: IcsUrlSource,
    range_start: datetime,
    range_end: datetime,
) -> list[BusyInterval]:
    logger.info(
        "fetching_ics",
        url=source.url,
        range_start=range_start.isoformat(),
        range_end=range_end.isoformat(),
    )
    response = _fetch_ics_response(source.url)
    response.raise_for_status()
    data = response.content

    cal = Calendar.from_ical(data)
    events = recurring_ical_events.of(cal).between(range_start, range_end)

    intervals: list[BusyInterval] = []
    for component in events:
        if component.name != "VEVENT":
            continue
        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        if dtstart is None or dtend is None:
            continue
        start = _coerce_calendar_datetime(dtstart.dt, range_start.tzinfo)
        end = _coerce_calendar_datetime(dtend.dt, range_start.tzinfo)
        if start is not None and end is not None:
            intervals.append(BusyInterval(start=start, end=end))

    logger.info("fetched_ics", url=source.url, count=len(intervals))
    return intervals
