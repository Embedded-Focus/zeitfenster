from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from zeitfenster.app import app
from zeitfenster.availability import FreeSlot
from zeitfenster.config import AppConfig
from zeitfenster.generator import generate_site

TZ = ZoneInfo("Europe/Vienna")

CONFIG_YAML = """\
branding:
  title: "Test Booking"

availability:
  calendars: []

rules:
  timezone: Europe/Vienna
  working_hours:
    mon: ["09:00-17:00"]
  slot_durations: [60m]
  buffer: 0m
  minimum_notice: 0m
  horizon: 7d

email:
  owner: owner@example.com
  smtp_host_env: TEST_SMTP_HOST
  smtp_port: 587
  smtp_user_env: TEST_SMTP_USER
  smtp_password_env: TEST_SMTP_PASSWORD
"""


@pytest.fixture()
def test_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)
    site_dir = tmp_path / "site"
    site_dir.mkdir()

    monkeypatch.setenv("TEST_SMTP_HOST", "localhost")
    monkeypatch.setenv("TEST_SMTP_USER", "testuser")
    monkeypatch.setenv("TEST_SMTP_PASSWORD", "testpass")

    config = AppConfig.from_yaml(config_path)
    slots = {
        "60m": [
            FreeSlot(
                start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
                end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
                duration=timedelta(hours=1),
            ),
        ]
    }
    generate_site(slots, config, site_dir)

    app.state.config_path = config_path
    app.state.site_dir = site_dir

    return {"config_path": config_path, "site_dir": site_dir, "config": config}


@pytest.fixture()
def client(test_env):
    with (
        patch("zeitfenster.app.fetch_and_compute", return_value={"60m": []}),
        patch("zeitfenster.app.generate_placeholder"),
        patch("zeitfenster.app.generate_site"),
        TestClient(app) as c,
    ):
        yield c


class TestFreeSlotsEndpoint:
    def test_returns_slots_json(self, client):
        client.app.state.current_slots = {
            "60m": [
                FreeSlot(
                    start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
                    end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
                    duration=timedelta(hours=1),
                ),
            ]
        }
        response = client.get("/api/free-slots")
        assert response.status_code == 200
        data = response.json()
        assert "slots" in data
        assert len(data["slots"]["60m"]) == 1
        assert "start" in data["slots"]["60m"][0]
        assert "end" in data["slots"]["60m"][0]

    def test_returns_empty_when_no_slots(self, client):
        client.app.state.current_slots = {}
        response = client.get("/api/free-slots")
        assert response.status_code == 200
        assert response.json() == {"slots": {}}


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestBookEndpoint:
    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_successful_booking(self, mock_send, client, test_env):
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock):
            response = client.post(
                "/book",
                data={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "slot_start": "2026-07-06T10:00:00+02:00",
                    "slot_end": "2026-07-06T11:00:00+02:00",
                    "duration": "60m",
                    "website": "",
                },
            )
        assert response.status_code == 200
        assert "Thank you" in response.text
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert call_kwargs[1]["customer_name"] == "Alice"
        assert call_kwargs[1]["customer_email"] == "alice@example.com"

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_honeypot_blocks_spam(self, mock_send, client):
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock):
            response = client.post(
                "/book",
                data={
                    "name": "Spammer",
                    "email": "spam@example.com",
                    "slot_start": "2026-07-06T10:00:00+02:00",
                    "slot_end": "2026-07-06T11:00:00+02:00",
                    "duration": "60m",
                    "website": "http://spam.example.com",
                },
            )
        assert response.status_code == 200
        assert "Thank you" in response.text
        mock_send.assert_not_called()

    def test_missing_fields_returns_422(self, client):
        response = client.post(
            "/book",
            data={"name": "Alice"},
        )
        assert response.status_code == 422

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_email_failure_still_returns_thankyou(self, mock_send, client):
        mock_send.side_effect = ConnectionError("SMTP down")
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock):
            response = client.post(
                "/book",
                data={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "slot_start": "2026-07-06T10:00:00+02:00",
                    "slot_end": "2026-07-06T11:00:00+02:00",
                    "duration": "60m",
                    "website": "",
                },
            )
        assert response.status_code == 200
        assert "Thank you" in response.text
