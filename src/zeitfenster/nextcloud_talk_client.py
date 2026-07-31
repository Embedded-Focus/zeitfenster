import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx2
import structlog

from zeitfenster.config import NextcloudTalk

logger = structlog.get_logger()

NEXTCLOUD_TALK_TIMEOUT_SECONDS = 10.0
NEXTCLOUD_TALK_PUBLIC_ROOM_TYPE = 3
NEXTCLOUD_TALK_MAX_ROOM_NAME_LENGTH = 255
NEXTCLOUD_TALK_MAX_ROOM_DESCRIPTION_LENGTH = 2000


class NextcloudTalkError(Exception):
    pass


@dataclass(frozen=True)
class NextcloudTalkBookingContext:
    customer_name: str
    customer_email: str
    customer_description: str
    owner_name: str
    owner_email: str
    slot_start: datetime
    slot_end: datetime


def _template_values(context: NextcloudTalkBookingContext) -> dict[str, str]:
    return {
        "customer_name": context.customer_name,
        "customer_email": context.customer_email,
        "customer_description": context.customer_description,
        "owner_name": context.owner_name,
        "owner_email": context.owner_email,
        "slot_start": context.slot_start.isoformat(),
        "slot_end": context.slot_end.isoformat(),
    }


def _api_url(config: NextcloudTalk, path: str) -> str:
    if config.base_url is None:
        raise NextcloudTalkError("Nextcloud Talk base URL is not configured")
    return (
        f"{config.base_url.rstrip('/')}/ocs/v2.php/apps/spreed/api/v4{path}?format=json"
    )


def _call_talk_api(
    *,
    method: str,
    url: str,
    config: NextcloudTalk,
    data: dict[str, Any],
) -> dict[str, Any]:
    response = httpx2.request(
        method,
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "OCS-APIRequest": "true",
        },
        auth=(config.username, config.app_password),
        timeout=NEXTCLOUD_TALK_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    response.raise_for_status()
    return json.loads(response.content)


def _extract_token(data: dict[str, Any]) -> str:
    token = data.get("ocs", {}).get("data", {}).get("token")
    if not isinstance(token, str) or not token:
        raise NextcloudTalkError("Nextcloud Talk response did not include a token")
    return token


async def create_talk_room(
    *,
    config: NextcloudTalk,
    context: NextcloudTalkBookingContext,
) -> str:
    values = _template_values(context)
    room_name = config.room_name_template.format(**values).strip()
    if not room_name:
        raise NextcloudTalkError("Nextcloud Talk room name is empty")
    if len(room_name) > NEXTCLOUD_TALK_MAX_ROOM_NAME_LENGTH:
        raise NextcloudTalkError("Nextcloud Talk room name is too long")

    payload: dict[str, Any] = {
        "roomType": NEXTCLOUD_TALK_PUBLIC_ROOM_TYPE,
        "roomName": room_name,
    }
    room_password = config.room_password
    if room_password is not None:
        payload["password"] = room_password

    try:
        data = await asyncio.to_thread(
            _call_talk_api,
            method="POST",
            url=_api_url(config, "/room"),
            config=config,
            data=payload,
        )
        token = _extract_token(data)

        if config.room_description_template:
            description = config.room_description_template.format(**values).strip()
            if len(description) > NEXTCLOUD_TALK_MAX_ROOM_DESCRIPTION_LENGTH:
                raise NextcloudTalkError("Nextcloud Talk room description is too long")
            if description:
                await asyncio.to_thread(
                    _call_talk_api,
                    method="PUT",
                    url=_api_url(config, f"/room/{token}/description"),
                    config=config,
                    data={"description": description},
                )
    except NextcloudTalkError:
        raise
    except Exception as exc:
        raise NextcloudTalkError("Nextcloud Talk room creation failed") from exc

    if config.base_url is None:
        raise NextcloudTalkError("Nextcloud Talk base URL is not configured")

    meeting_url = f"{config.base_url.rstrip('/')}/call/{token}"
    logger.info("nextcloud_talk_room_created")
    return meeting_url
