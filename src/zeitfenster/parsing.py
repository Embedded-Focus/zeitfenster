from __future__ import annotations

import re
from datetime import time, timedelta

_DURATION_RE = re.compile(r"^(\d+)([mhd])$")

_UNITS: dict[str, str] = {
    "m": "minutes",
    "h": "hours",
    "d": "days",
}


def parse_duration(s: str) -> timedelta:
    m = _DURATION_RE.match(s.strip())
    if not m:
        raise ValueError(f"Invalid duration {s!r}, expected e.g. '30m', '2h', '7d'")
    value, unit = int(m.group(1)), m.group(2)
    return timedelta(**{_UNITS[unit]: value})


def parse_time_range(s: str) -> tuple[time, time]:
    parts = s.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid time range {s!r}, expected e.g. '09:00-17:00'")
    start = time.fromisoformat(parts[0].strip())
    end = time.fromisoformat(parts[1].strip())
    if end <= start:
        raise ValueError(f"End time must be after start time in {s!r}")
    return start, end
