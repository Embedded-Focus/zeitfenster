from __future__ import annotations

import json
import urllib.request
from datetime import datetime

import structlog

from zeitfenster.availability import FreeSlot
from zeitfenster.config import ZeitfensterSource

logger = structlog.get_logger()


def fetch_free_slots(
    source: ZeitfensterSource,
    slot_durations: list[str],
) -> dict[str, list[FreeSlot]]:
    url = f"{source.url.rstrip('/')}/api/free-slots"
    logger.info("fetching_zeitfenster", url=url)

    token = source.token
    request: str | urllib.request.Request
    if token is None:
        request = url
    else:
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )

    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        data = json.loads(response.read())

    remote_slots: dict = data.get("slots", {})

    result: dict[str, list[FreeSlot]] = {}
    for duration_str in slot_durations:
        raw_list = remote_slots.get(duration_str, [])
        parsed: list[FreeSlot] = []
        for entry in raw_list:
            start = datetime.fromisoformat(entry["start"])
            end = datetime.fromisoformat(entry["end"])
            parsed.append(FreeSlot(start=start, end=end, duration=end - start))
        result[duration_str] = parsed

    logger.info(
        "fetched_zeitfenster",
        url=url,
        durations={d: len(s) for d, s in result.items()},
    )
    return result
