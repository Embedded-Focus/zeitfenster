from collections import deque

import pytest
from fastapi import HTTPException

from zeitfenster.rate_limit import enforce_booking_rate_limit


def test_enforce_booking_rate_limit_allows_until_limit():
    timestamps: deque[float] = deque()

    enforce_booking_rate_limit(timestamps, max_requests=2, window_seconds=300)
    enforce_booking_rate_limit(timestamps, max_requests=2, window_seconds=300)

    assert len(timestamps) == 2


def test_enforce_booking_rate_limit_rejects_over_limit():
    timestamps: deque[float] = deque()
    enforce_booking_rate_limit(timestamps, max_requests=1, window_seconds=300)

    with pytest.raises(HTTPException) as exc_info:
        enforce_booking_rate_limit(timestamps, max_requests=1, window_seconds=300)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "Too many booking requests"
