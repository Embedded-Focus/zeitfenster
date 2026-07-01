from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx2
import pytest

from zeitfenster.config import ZeitfensterSource
from zeitfenster.zeitfenster_client import fetch_free_slots

TZ = ZoneInfo("Europe/Vienna")


def _make_response(
    slots_dict: dict,
    status_code: int = 200,
    url: str = "https://example.com/api/free-slots",
) -> httpx2.Response:
    return httpx2.Response(
        status_code,
        content=json.dumps({"slots": slots_dict}).encode(),
        request=httpx2.Request("GET", url),
    )


class TestFetchFreeSlots:
    def test_parses_json_response(self):
        source = ZeitfensterSource(url="https://example.com")
        response_data = {
            "30m": [
                {
                    "start": "2026-07-01T09:00:00+02:00",
                    "end": "2026-07-01T09:30:00+02:00",
                },
                {
                    "start": "2026-07-01T09:30:00+02:00",
                    "end": "2026-07-01T10:00:00+02:00",
                },
            ],
            "60m": [
                {
                    "start": "2026-07-01T09:00:00+02:00",
                    "end": "2026-07-01T10:00:00+02:00",
                },
            ],
        }

        with patch("zeitfenster.zeitfenster_client.httpx2.get") as mock_get:
            mock_get.return_value = _make_response(response_data)
            result = fetch_free_slots(source, ["30m", "60m"])

        assert len(result["30m"]) == 2
        assert len(result["60m"]) == 1
        assert result["30m"][0].duration == timedelta(minutes=30)
        assert result["60m"][0].duration == timedelta(minutes=60)
        mock_get.assert_called_once_with(
            "https://example.com/api/free-slots",
            headers={},
            timeout=10.0,
            follow_redirects=False,
        )

    def test_filters_to_requested_durations(self):
        source = ZeitfensterSource(url="https://example.com")
        response_data = {
            "30m": [
                {
                    "start": "2026-07-01T09:00:00+02:00",
                    "end": "2026-07-01T09:30:00+02:00",
                },
            ],
            "60m": [
                {
                    "start": "2026-07-01T09:00:00+02:00",
                    "end": "2026-07-01T10:00:00+02:00",
                },
            ],
        }

        with patch("zeitfenster.zeitfenster_client.httpx2.get") as mock_get:
            mock_get.return_value = _make_response(response_data)
            result = fetch_free_slots(source, ["30m"])

        assert "30m" in result
        assert "60m" not in result

    def test_missing_duration_returns_empty_list(self):
        source = ZeitfensterSource(url="https://example.com")
        response_data = {"30m": []}

        with patch("zeitfenster.zeitfenster_client.httpx2.get") as mock_get:
            mock_get.return_value = _make_response(response_data)
            result = fetch_free_slots(source, ["60m"])

        assert result["60m"] == []

    def test_strips_trailing_slash_from_url(self):
        source = ZeitfensterSource(url="https://example.com/")

        with patch("zeitfenster.zeitfenster_client.httpx2.get") as mock_get:
            mock_get.return_value = _make_response({})
            fetch_free_slots(source, ["30m"])

        mock_get.assert_called_once_with(
            "https://example.com/api/free-slots",
            headers={},
            timeout=10.0,
            follow_redirects=False,
        )

    def test_sends_bearer_token_when_configured(self, monkeypatch):
        source = ZeitfensterSource(
            url="https://example.com",
            token_env="EXAMPLE_ZEITFENSTER_TOKEN",
        )
        monkeypatch.setenv("EXAMPLE_ZEITFENSTER_TOKEN", "remote-secret")

        with patch("zeitfenster.zeitfenster_client.httpx2.get") as mock_get:
            mock_get.return_value = _make_response({})
            fetch_free_slots(source, ["30m"])

        mock_get.assert_called_once_with(
            "https://example.com/api/free-slots",
            headers={"Authorization": "Bearer remote-secret"},
            timeout=10.0,
            follow_redirects=False,
        )

    def test_network_error_raises(self):
        source = ZeitfensterSource(url="https://unreachable.example.com")

        with patch("zeitfenster.zeitfenster_client.httpx2.get") as mock_get:
            mock_get.side_effect = httpx2.ConnectError("Connection refused")
            with pytest.raises(httpx2.ConnectError, match="Connection refused"):
                fetch_free_slots(source, ["30m"])

    def test_http_error_raises(self):
        source = ZeitfensterSource(url="https://example.com")

        with patch("zeitfenster.zeitfenster_client.httpx2.get") as mock_get:
            mock_get.return_value = _make_response({}, status_code=401)
            with pytest.raises(httpx2.HTTPStatusError):
                fetch_free_slots(source, ["30m"])
