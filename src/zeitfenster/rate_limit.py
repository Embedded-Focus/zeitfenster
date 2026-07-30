from collections import deque
from time import monotonic

from fastapi import HTTPException


def enforce_booking_rate_limit(
    timestamps: deque[float],
    *,
    max_requests: int,
    window_seconds: int,
) -> None:
    now = monotonic()
    window_start = now - window_seconds
    while timestamps and timestamps[0] <= window_start:
        timestamps.popleft()

    if len(timestamps) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many booking requests")

    timestamps.append(now)
