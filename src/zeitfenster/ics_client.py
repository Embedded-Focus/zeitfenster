from __future__ import annotations

import urllib.request
from datetime import datetime

import recurring_ical_events
import structlog
from icalendar import Calendar

from zeitfenster.caldav_client import BusyInterval
from zeitfenster.config import IcsUrlSource

logger = structlog.get_logger()


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
    with urllib.request.urlopen(source.url) as response:  # noqa: S310
        data = response.read()

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
        start = dtstart.dt
        end = dtend.dt
        if isinstance(start, datetime) and isinstance(end, datetime):
            intervals.append(BusyInterval(start=start, end=end))

    logger.info("fetched_ics", url=source.url, count=len(intervals))
    return intervals
