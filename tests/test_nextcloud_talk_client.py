from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx2
import pytest

from zeitfenster.config import NextcloudTalk
from zeitfenster.nextcloud_talk_client import (
    NEXTCLOUD_TALK_TIMEOUT_SECONDS,
    NextcloudTalkBookingContext,
    NextcloudTalkError,
    create_talk_room,
)

TZ = ZoneInfo("Europe/Vienna")


def _config(**overrides) -> NextcloudTalk:
    data = {
        "enabled": True,
        "base_url": "https://cloud.example.com",
        "username_env": "NEXTCLOUD_TALK_USER",
        "app_password_env": "NEXTCLOUD_TALK_APP_PASSWORD",
        "room_name_template": "Meeting with {customer_name}",
    }
    data.update(overrides)
    return NextcloudTalk.model_validate(data)


def _context(**overrides) -> NextcloudTalkBookingContext:
    data = {
        "customer_name": "Alice",
        "customer_email": "alice@example.com",
        "customer_description": "Discuss launch plan.",
        "owner_name": "Jane Doe",
        "owner_email": "jane@example.com",
        "slot_start": datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
        "slot_end": datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
    }
    data.update(overrides)
    return NextcloudTalkBookingContext(**data)


def _talk_response(token: str = "abc123") -> httpx2.Response:
    return httpx2.Response(
        201,
        content=(f'{{"ocs": {{"data": {{"token": "{token}"}}}}}}').encode(),
        request=httpx2.Request(
            "POST",
            "https://cloud.example.com/ocs/v2.php/apps/spreed/api/v4/room",
        ),
    )


@pytest.mark.asyncio
async def test_create_talk_room_sends_expected_request(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_TALK_USER", "talk-bot")
    monkeypatch.setenv("NEXTCLOUD_TALK_APP_PASSWORD", "app-password")

    with patch("zeitfenster.nextcloud_talk_client.httpx2.request") as request:
        request.return_value = _talk_response()

        meeting_url = await create_talk_room(config=_config(), context=_context())

    assert meeting_url == "https://cloud.example.com/call/abc123"
    request.assert_called_once_with(
        "POST",
        "https://cloud.example.com/ocs/v2.php/apps/spreed/api/v4/room?format=json",
        data={"roomType": 3, "roomName": "Meeting with Alice"},
        headers={
            "Accept": "application/json",
            "OCS-APIRequest": "true",
        },
        auth=("talk-bot", "app-password"),
        timeout=NEXTCLOUD_TALK_TIMEOUT_SECONDS,
        follow_redirects=False,
    )


@pytest.mark.asyncio
async def test_create_talk_room_sends_optional_password(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_TALK_USER", "talk-bot")
    monkeypatch.setenv("NEXTCLOUD_TALK_APP_PASSWORD", "app-password")
    monkeypatch.setenv("NEXTCLOUD_TALK_ROOM_PASSWORD", "room-secret")

    with patch("zeitfenster.nextcloud_talk_client.httpx2.request") as request:
        request.return_value = _talk_response()

        await create_talk_room(
            config=_config(room_password_env="NEXTCLOUD_TALK_ROOM_PASSWORD"),
            context=_context(),
        )

    assert request.call_args.kwargs["data"]["password"] == "room-secret"


@pytest.mark.asyncio
async def test_create_talk_room_sets_optional_description(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_TALK_USER", "talk-bot")
    monkeypatch.setenv("NEXTCLOUD_TALK_APP_PASSWORD", "app-password")

    with patch("zeitfenster.nextcloud_talk_client.httpx2.request") as request:
        request.side_effect = [
            _talk_response("room-token"),
            httpx2.Response(
                200,
                content=b'{"ocs": {"data": []}}',
                request=httpx2.Request(
                    "PUT",
                    "https://cloud.example.com/ocs/v2.php/apps/spreed/api/v4/"
                    "room/room-token/description",
                ),
            ),
        ]

        meeting_url = await create_talk_room(
            config=_config(
                room_description_template=(
                    "Message from {customer_name}:\n{customer_description}"
                )
            ),
            context=_context(),
        )

    assert meeting_url == "https://cloud.example.com/call/room-token"
    assert request.call_args_list[1].kwargs["data"] == {
        "description": "Message from Alice:\nDiscuss launch plan."
    }


@pytest.mark.asyncio
async def test_create_talk_room_rejects_malformed_token_response(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_TALK_USER", "talk-bot")
    monkeypatch.setenv("NEXTCLOUD_TALK_APP_PASSWORD", "app-password")

    with patch("zeitfenster.nextcloud_talk_client.httpx2.request") as request:
        request.return_value = httpx2.Response(
            201,
            content=b'{"ocs": {"data": {}}}',
            request=httpx2.Request(
                "POST",
                "https://cloud.example.com/ocs/v2.php/apps/spreed/api/v4/room",
            ),
        )

        with pytest.raises(NextcloudTalkError, match="token"):
            await create_talk_room(config=_config(), context=_context())


@pytest.mark.asyncio
async def test_create_talk_room_rejects_overlong_room_name(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_TALK_USER", "talk-bot")
    monkeypatch.setenv("NEXTCLOUD_TALK_APP_PASSWORD", "app-password")

    with pytest.raises(NextcloudTalkError, match="room name"):
        await create_talk_room(
            config=_config(room_name_template="{customer_name}"),
            context=_context(customer_name="A" * 256),
        )


@pytest.mark.asyncio
async def test_create_talk_room_wraps_http_errors(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_TALK_USER", "talk-bot")
    monkeypatch.setenv("NEXTCLOUD_TALK_APP_PASSWORD", "app-password")

    with patch("zeitfenster.nextcloud_talk_client.httpx2.request") as request:
        request.side_effect = httpx2.ConnectError("offline")

        with pytest.raises(NextcloudTalkError, match="room creation failed"):
            await create_talk_room(config=_config(), context=_context())
