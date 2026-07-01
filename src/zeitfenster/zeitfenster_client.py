import json
from datetime import datetime

import httpx2
import structlog

from zeitfenster.availability import FreeSlot
from zeitfenster.config import ZeitfensterSource

logger = structlog.get_logger()
ZEITFENSTER_FETCH_TIMEOUT_SECONDS = 10.0


def fetch_free_slots(
    source: ZeitfensterSource,
    slot_durations: list[str],
) -> dict[str, list[FreeSlot]]:
    url = f"{source.url.rstrip('/')}/api/free-slots"
    logger.info("fetching_zeitfenster", url=url)

    token = source.token
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    response = httpx2.get(
        url,
        headers=headers,
        timeout=ZEITFENSTER_FETCH_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    response.raise_for_status()
    data = json.loads(response.content)

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
