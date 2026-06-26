from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import caldav  # type: ignore[import-untyped]
import structlog
from icalendar import cal as ical_cal

from zeitfenster.config import CalendarSource

logger = structlog.get_logger()


@dataclass(frozen=True, order=True)
class BusyInterval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be after start ({self.start})")


def _extract_busy_intervals(
    event: caldav.CalendarObjectResource,
) -> list[BusyInterval]:
    intervals: list[BusyInterval] = []
    ical = event.icalendar_instance
    if not isinstance(ical, ical_cal.Calendar):
        return intervals
    for component in ical.walk():
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
    return intervals


def fetch_busy_intervals(
    source: CalendarSource,
    range_start: datetime,
    range_end: datetime,
) -> list[BusyInterval]:
    logger.info(
        "fetching_events",
        url=source.url,
        username=source.username,
        range_start=range_start.isoformat(),
        range_end=range_end.isoformat(),
    )
    client = caldav.DAVClient(
        url=source.url,
        username=source.username,
        password=source.password,
    )
    calendar = client.calendar(url=source.url)
    events = calendar.search(
        start=range_start,
        end=range_end,
        event=True,
        expand=True,
    )
    intervals: list[BusyInterval] = []
    for event in events:
        intervals.extend(_extract_busy_intervals(event))
    logger.info("fetched_events", url=source.url, count=len(intervals))
    return intervals
