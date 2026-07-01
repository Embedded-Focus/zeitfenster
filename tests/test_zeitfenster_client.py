from __future__ import annotations

import json
import urllib.request
from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from zeitfenster.config import ZeitfensterSource
from zeitfenster.zeitfenster_client import fetch_free_slots

TZ = ZoneInfo("Europe/Vienna")


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _make_response(slots_dict: dict) -> _FakeResponse:
    return _FakeResponse(json.dumps({"slots": slots_dict}).encode())


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

        with patch(
            "zeitfenster.zeitfenster_client.urllib.request.urlopen"
        ) as mock_urlopen:
            mock_urlopen.return_value = _make_response(response_data)
            result = fetch_free_slots(source, ["30m", "60m"])

        assert len(result["30m"]) == 2
        assert len(result["60m"]) == 1
        assert result["30m"][0].duration == timedelta(minutes=30)
        assert result["60m"][0].duration == timedelta(minutes=60)
        mock_urlopen.assert_called_once_with(
            "https://example.com/api/free-slots", timeout=10
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

        with patch(
            "zeitfenster.zeitfenster_client.urllib.request.urlopen"
        ) as mock_urlopen:
            mock_urlopen.return_value = _make_response(response_data)
            result = fetch_free_slots(source, ["30m"])

        assert "30m" in result
        assert "60m" not in result

    def test_missing_duration_returns_empty_list(self):
        source = ZeitfensterSource(url="https://example.com")
        response_data = {"30m": []}

        with patch(
            "zeitfenster.zeitfenster_client.urllib.request.urlopen"
        ) as mock_urlopen:
            mock_urlopen.return_value = _make_response(response_data)
            result = fetch_free_slots(source, ["60m"])

        assert result["60m"] == []

    def test_strips_trailing_slash_from_url(self):
        source = ZeitfensterSource(url="https://example.com/")

        with patch(
            "zeitfenster.zeitfenster_client.urllib.request.urlopen"
        ) as mock_urlopen:
            mock_urlopen.return_value = _make_response({})
            fetch_free_slots(source, ["30m"])

        mock_urlopen.assert_called_once_with(
            "https://example.com/api/free-slots", timeout=10
        )

    def test_sends_bearer_token_when_configured(self, monkeypatch):
        source = ZeitfensterSource(
            url="https://example.com",
            token_env="EXAMPLE_ZEITFENSTER_TOKEN",
        )
        monkeypatch.setenv("EXAMPLE_ZEITFENSTER_TOKEN", "remote-secret")

        with patch(
            "zeitfenster.zeitfenster_client.urllib.request.urlopen"
        ) as mock_urlopen:
            mock_urlopen.return_value = _make_response({})
            fetch_free_slots(source, ["30m"])

        request = mock_urlopen.call_args.args[0]
        assert isinstance(request, urllib.request.Request)
        assert request.full_url == "https://example.com/api/free-slots"
        assert request.headers["Authorization"] == "Bearer remote-secret"
        assert mock_urlopen.call_args.kwargs == {"timeout": 10}

    def test_network_error_raises(self):
        source = ZeitfensterSource(url="https://unreachable.example.com")

        with patch(
            "zeitfenster.zeitfenster_client.urllib.request.urlopen"
        ) as mock_urlopen:
            mock_urlopen.side_effect = OSError("Connection refused")
            with pytest.raises(OSError, match="Connection refused"):
                fetch_free_slots(source, ["30m"])
