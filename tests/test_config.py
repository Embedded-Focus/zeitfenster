import os
import tempfile
from pathlib import Path

import pytest

from zeitfenster.config import AppConfig


MINIMAL_YAML = """\
email:
  owner: test@example.com
"""

MULTI_OWNER_YAML = """\
email:
  owner:
    - alice@example.com
    - bob@example.com
"""

FEDERATION_YAML = """\
availability:
  zeitfenster_urls:
    - url: https://alice.example.com
    - url: https://bob.example.com
      token_env: BOB_ZEITFENSTER_TOKEN

federation:
  free_slots_token_env: INBOUND_ZEITFENSTER_TOKEN

email:
  owner: test@example.com
"""

FULL_YAML = """\
branding:
  title: "Test Booking"
  logo: "/static/logo.png"
  colors:
    primary: "#ff0000"
    background: "#000000"

availability:
  calendars:
    - url: https://caldav.example.com/cal1/
      username: reader1
      password_env: CAL1_PASSWORD
    - url: https://caldav.example.com/cal2/
      username: reader2
      password_env: CAL2_PASSWORD
  ics_urls:
    - url: https://calendar.google.com/calendar/ical/test/basic.ics

booking:
  location: https://meet.example.com/room
  owner_name: "Jane Doe"
  summary_template: "{customer_name} and {owner_name}"
  description_template: |
    Booking request from {customer_name} <{customer_email}>.
    Meeting link is already configured.

rules:
  timezone: Europe/Vienna
  working_hours:
    mon: ["09:00-12:00", "13:00-17:00"]
    tue: ["09:00-17:00"]
    fri: ["09:00-16:00"]
  slot_durations: [30m, 60m, 90m]
  buffer: 15m
  minimum_notice: 24h
  horizon: 60d
  refresh_interval: 10m

email:
  owner: owner@example.com
  from_name: "Booking Bot"
  smtp_host_env: TEST_SMTP_HOST
  smtp_port: 465
  smtp_user_env: TEST_SMTP_USER
  smtp_password_env: TEST_SMTP_PASSWORD
"""


def _write_yaml(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


class TestMinimalConfig:
    def test_loads_with_defaults(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.email.owner == "test@example.com"
            assert cfg.branding.title == "Book a Meeting"
            assert cfg.branding.colors.primary == "#2563eb"
            assert cfg.rules.timezone == "UTC"
            assert cfg.rules.slot_durations == ["30m"]
            assert cfg.rules.refresh_interval == "15m"
            assert cfg.availability.calendars == []
            assert cfg.booking.location is None
            assert cfg.booking.owner_name is None
            assert cfg.booking.summary_template == "{customer_name}"
            assert cfg.booking.description_template == ""
        finally:
            path.unlink()


class TestFullConfig:
    def test_loads_all_fields(self):
        path = _write_yaml(FULL_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.branding.title == "Test Booking"
            assert cfg.branding.logo == "/static/logo.png"
            assert cfg.branding.colors.primary == "#ff0000"
            assert len(cfg.availability.calendars) == 2
            assert (
                cfg.availability.calendars[0].url == "https://caldav.example.com/cal1/"
            )
            assert cfg.availability.calendars[0].username == "reader1"
            assert len(cfg.availability.ics_urls) == 1
            assert (
                cfg.availability.ics_urls[0].url
                == "https://calendar.google.com/calendar/ical/test/basic.ics"
            )
            assert cfg.rules.timezone == "Europe/Vienna"
            assert cfg.rules.working_hours.mon == ["09:00-12:00", "13:00-17:00"]
            assert cfg.rules.working_hours.sat == []
            assert cfg.rules.slot_durations == ["30m", "60m", "90m"]
            assert cfg.rules.buffer == "15m"
            assert cfg.rules.horizon == "60d"
            assert cfg.rules.refresh_interval == "10m"
            assert cfg.booking.location == "https://meet.example.com/room"
            assert cfg.booking.owner_name == "Jane Doe"
            assert cfg.booking.summary_template == "{customer_name} and {owner_name}"
            assert "Meeting link is already configured." in (
                cfg.booking.description_template
            )
            assert cfg.email.owner == "owner@example.com"
            assert cfg.email.from_name == "Booking Bot"
            assert cfg.email.smtp_port == 465
        finally:
            path.unlink()

    def test_rejects_unknown_booking_template_fields(self):
        path = _write_yaml(
            """\
booking:
  summary_template: "{customer_name} and {calendar_name}"
email:
  owner: owner@example.com
"""
        )
        try:
            with pytest.raises(ValueError, match="calendar_name"):
                AppConfig.from_yaml(path)
        finally:
            path.unlink()


class TestEnvVarResolution:
    def test_calendar_password_from_env(self, monkeypatch):
        path = _write_yaml(FULL_YAML)
        monkeypatch.setenv("CAL1_PASSWORD", "secret123")
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.availability.calendars[0].password == "secret123"
        finally:
            path.unlink()

    def test_calendar_password_missing_raises(self):
        path = _write_yaml(FULL_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            os.environ.pop("CAL1_PASSWORD", None)
            with pytest.raises(ValueError, match="CAL1_PASSWORD"):
                _ = cfg.availability.calendars[0].password
        finally:
            path.unlink()

    def test_smtp_credentials_from_env(self, monkeypatch):
        path = _write_yaml(FULL_YAML)
        monkeypatch.setenv("TEST_SMTP_HOST", "mail.example.com")
        monkeypatch.setenv("TEST_SMTP_USER", "user")
        monkeypatch.setenv("TEST_SMTP_PASSWORD", "pass")
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.email.smtp_host == "mail.example.com"
            assert cfg.email.smtp_user == "user"
            assert cfg.email.smtp_password == "pass"
        finally:
            path.unlink()

    def test_smtp_host_missing_raises(self):
        path = _write_yaml(FULL_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            os.environ.pop("TEST_SMTP_HOST", None)
            with pytest.raises(ValueError, match="TEST_SMTP_HOST"):
                _ = cfg.email.smtp_host
        finally:
            path.unlink()


class TestOwnerList:
    def test_single_string_owner(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.email.owner == "test@example.com"
            assert cfg.email.from_name == "Zeitfenster"
            assert cfg.email.owner_list == ["test@example.com"]
        finally:
            path.unlink()

    def test_list_owner(self):
        path = _write_yaml(MULTI_OWNER_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.email.owner == ["alice@example.com", "bob@example.com"]
            assert cfg.email.owner_list == ["alice@example.com", "bob@example.com"]
        finally:
            path.unlink()


class TestZeitfensterSource:
    def test_parses_zeitfenster_urls(self):
        path = _write_yaml(FEDERATION_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            assert len(cfg.availability.zeitfenster_urls) == 2
            assert (
                cfg.availability.zeitfenster_urls[0].url == "https://alice.example.com"
            )
            assert cfg.availability.zeitfenster_urls[1].url == "https://bob.example.com"
            assert cfg.availability.zeitfenster_urls[0].token_env is None
            assert (
                cfg.availability.zeitfenster_urls[1].token_env
                == "BOB_ZEITFENSTER_TOKEN"
            )
            assert cfg.federation.free_slots_token_env == "INBOUND_ZEITFENSTER_TOKEN"
        finally:
            path.unlink()

    def test_default_empty(self):
        path = _write_yaml(MINIMAL_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.availability.zeitfenster_urls == []
            assert cfg.federation.free_slots_token_env is None
        finally:
            path.unlink()

    def test_zeitfenster_token_from_env(self, monkeypatch):
        path = _write_yaml(FEDERATION_YAML)
        monkeypatch.setenv("BOB_ZEITFENSTER_TOKEN", "remote-secret")
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.availability.zeitfenster_urls[0].token is None
            assert cfg.availability.zeitfenster_urls[1].token == "remote-secret"
        finally:
            path.unlink()

    def test_zeitfenster_token_missing_raises(self):
        path = _write_yaml(FEDERATION_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            os.environ.pop("BOB_ZEITFENSTER_TOKEN", None)
            with pytest.raises(ValueError, match="BOB_ZEITFENSTER_TOKEN"):
                _ = cfg.availability.zeitfenster_urls[1].token
        finally:
            path.unlink()

    def test_free_slots_token_from_env(self, monkeypatch):
        path = _write_yaml(FEDERATION_YAML)
        monkeypatch.setenv("INBOUND_ZEITFENSTER_TOKEN", "inbound-secret")
        try:
            cfg = AppConfig.from_yaml(path)
            assert cfg.federation.free_slots_token == "inbound-secret"
        finally:
            path.unlink()

    def test_free_slots_token_missing_raises(self):
        path = _write_yaml(FEDERATION_YAML)
        try:
            cfg = AppConfig.from_yaml(path)
            os.environ.pop("INBOUND_ZEITFENSTER_TOKEN", None)
            with pytest.raises(ValueError, match="INBOUND_ZEITFENSTER_TOKEN"):
                _ = cfg.federation.free_slots_token
        finally:
            path.unlink()
