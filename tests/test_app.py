from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import zeitfenster.app as app_module
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
    def _valid_booking_data(self, **overrides):
        data = {
            "name": "Alice",
            "email": "alice@example.com",
            "slot_start": "2026-07-06T10:00:00+02:00",
            "slot_end": "2026-07-06T11:00:00+02:00",
            "duration": "60m",
            "website": "",
        }
        data.update(overrides)
        return data

    def _set_available_slot(self, client):
        client.app.state.current_slots = {
            "60m": [
                FreeSlot(
                    start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
                    end=datetime(2026, 7, 6, 11, 0, tzinfo=TZ),
                    duration=timedelta(hours=1),
                ),
            ]
        }

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_successful_booking(self, mock_send, client, test_env):
        self._set_available_slot(client)
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock):
            response = client.post(
                "/book",
                data=self._valid_booking_data(),
            )
        assert response.status_code == 200
        assert "Thank you" in response.text
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert call_kwargs[1]["customer_name"] == "Alice"
        assert call_kwargs[1]["customer_email"] == "alice@example.com"

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_booking_fields_are_normalized(self, mock_send, client):
        self._set_available_slot(client)
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock):
            response = client.post(
                "/book",
                data=self._valid_booking_data(
                    name="  Alice  ",
                    email="  alice@example.com  ",
                    slot_start="  2026-07-06T10:00:00+02:00  ",
                    slot_end="  2026-07-06T11:00:00+02:00  ",
                    duration="  60m  ",
                ),
            )
        assert response.status_code == 200
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

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_honeypot_does_not_validate_other_fields_or_regenerate(
        self, mock_send, client
    ):
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            response = client.post(
                "/book",
                data=self._valid_booking_data(
                    name="A" * 101,
                    email="not-an-email",
                    website="http://spam.example.com",
                ),
            )
        assert response.status_code == 200
        assert "Thank you" in response.text
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    @pytest.mark.parametrize(
        ("field", "value", "detail"),
        [
            ("name", "   ", "name is required"),
            ("name", "A" * 101, "name is too long"),
            ("name", "Alice\nBob", "name contains invalid characters"),
            ("email", "x", "email is too short"),
            ("email", "not-an-email", "Invalid email"),
            ("email", "alice bob@example.com", "Invalid email"),
            ("email", "a" * 247 + "@example.com", "email is too long"),
            ("slot_start", "2" * 65, "slot_start is too long"),
            ("slot_end", "2" * 65, "slot_end is too long"),
            ("duration", "x" * 17, "duration is too long"),
            ("website", "x" * 2049, "website is too long"),
        ],
    )
    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rejects_invalid_form_fields(self, mock_send, client, field, value, detail):
        self._set_available_slot(client)
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            response = client.post(
                "/book",
                data=self._valid_booking_data(**{field: value}),
            )
        assert response.status_code == 400
        assert response.json()["detail"] == detail
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rate_limit_blocks_repeated_valid_bookings(
        self, mock_send, client, monkeypatch
    ):
        self._set_available_slot(client)
        monkeypatch.setattr(app_module, "BOOKING_RATE_LIMIT_MAX", 2)
        monkeypatch.setattr(app_module, "BOOKING_RATE_LIMIT_WINDOW_SECONDS", 300)

        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            first = client.post("/book", data=self._valid_booking_data())
            second = client.post("/book", data=self._valid_booking_data())
            third = client.post("/book", data=self._valid_booking_data())

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert third.json()["detail"] == "Too many booking requests"
        assert mock_send.await_count == 2
        assert mock_regen.await_count <= 2

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_repeated_valid_bookings_coalesce_regeneration(self, mock_send, client):
        self._set_available_slot(client)

        async def slow_regenerate(_app):
            await asyncio.sleep(0.05)

        with patch("zeitfenster.app._regenerate", side_effect=slow_regenerate) as regen:
            first = client.post("/book", data=self._valid_booking_data())
            second = client.post("/book", data=self._valid_booking_data())

        assert first.status_code == 200
        assert second.status_code == 200
        assert mock_send.await_count == 2
        assert regen.call_count == 1

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rejects_slot_not_in_current_availability(self, mock_send, client):
        self._set_available_slot(client)
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            response = client.post(
                "/book",
                data={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "slot_start": "2026-07-06T12:00:00+02:00",
                    "slot_end": "2026-07-06T13:00:00+02:00",
                    "duration": "60m",
                    "website": "",
                },
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "Requested slot is not available"
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rejects_stale_slot_when_current_availability_is_empty(
        self, mock_send, client
    ):
        client.app.state.current_slots = {"60m": []}
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
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
        assert response.status_code == 400
        assert response.json()["detail"] == "Requested slot is not available"
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rejects_duration_not_in_config(self, mock_send, client):
        self._set_available_slot(client)
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            response = client.post(
                "/book",
                data={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "slot_start": "2026-07-06T10:00:00+02:00",
                    "slot_end": "2026-07-06T11:00:00+02:00",
                    "duration": "90m",
                    "website": "",
                },
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid duration"
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rejects_mismatched_duration(self, mock_send, client):
        client.app.state.current_slots = {
            "60m": [
                FreeSlot(
                    start=datetime(2026, 7, 6, 10, 0, tzinfo=TZ),
                    end=datetime(2026, 7, 6, 12, 0, tzinfo=TZ),
                    duration=timedelta(hours=2),
                ),
            ]
        }
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            response = client.post(
                "/book",
                data={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "slot_start": "2026-07-06T10:00:00+02:00",
                    "slot_end": "2026-07-06T12:00:00+02:00",
                    "duration": "60m",
                    "website": "",
                },
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "Requested slot duration does not match"
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rejects_slot_end_before_slot_start(self, mock_send, client):
        self._set_available_slot(client)
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            response = client.post(
                "/book",
                data={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "slot_start": "2026-07-06T11:00:00+02:00",
                    "slot_end": "2026-07-06T10:00:00+02:00",
                    "duration": "60m",
                    "website": "",
                },
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "slot_end must be after slot_start"
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rejects_malformed_slot_start(self, mock_send, client):
        self._set_available_slot(client)
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            response = client.post(
                "/book",
                data={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "slot_start": "not-a-date",
                    "slot_end": "2026-07-06T11:00:00+02:00",
                    "duration": "60m",
                    "website": "",
                },
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid slot_start"
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_rejects_naive_slot_start(self, mock_send, client):
        self._set_available_slot(client)
        with patch("zeitfenster.app._regenerate", new_callable=AsyncMock) as mock_regen:
            response = client.post(
                "/book",
                data={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "slot_start": "2026-07-06T10:00:00",
                    "slot_end": "2026-07-06T11:00:00+02:00",
                    "duration": "60m",
                    "website": "",
                },
            )
        assert response.status_code == 400
        assert response.json()["detail"] == "slot_start must include a timezone"
        mock_send.assert_not_called()
        mock_regen.assert_not_called()

    def test_missing_fields_returns_422(self, client):
        response = client.post(
            "/book",
            data={"name": "Alice"},
        )
        assert response.status_code == 422

    @patch("zeitfenster.app.send_booking_email", new_callable=AsyncMock)
    def test_email_failure_still_returns_thankyou(self, mock_send, client):
        self._set_available_slot(client)
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
