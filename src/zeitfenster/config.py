import os
from pathlib import Path
from string import Formatter
from typing import Any
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, field_validator, model_validator

DESCRIPTION_TEMPLATE_FIELDS = {"customer_name", "customer_email"}
SUMMARY_TEMPLATE_FIELDS = {
    "customer_name",
    "customer_email",
    "owner_name",
    "owner_email",
}


def _validate_template_fields(
    value: str,
    *,
    allowed_fields: set[str],
) -> str:
    for _, field_name, _, _ in Formatter().parse(value):
        if field_name is not None and field_name not in allowed_fields:
            allowed = ", ".join(sorted(allowed_fields))
            raise ValueError(
                f"Unknown template field {field_name!r}. Allowed fields: {allowed}"
            )
    return value


class BrandingColors(BaseModel):
    background: str = "#ffffff"
    text: str = "#373c44"
    muted_text: str = "#646b79"
    primary: str = "#2563eb"
    primary_hover: str = "#1d4ed8"
    primary_focus: str = "rgba(37, 99, 235, 0.25)"
    primary_inverse: str = "#ffffff"
    surface: str = "#ffffff"
    surface_border: str = "#e7eaef"
    surface_section: str = "#fbfbfc"
    form_background: str = "#fbfbfc"
    form_border: str = "#cfd5e2"
    form_active_background: str = "#ffffff"
    slot_colors: list[str] = ["#4a90d9", "#5ba870", "#d4833e"]
    slot_backgrounds: list[str] = ["#dbeafe", "#d1fae5", "#ffedd5"]

    @field_validator("slot_colors", "slot_backgrounds")
    @classmethod
    def _validate_color_list(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("color lists must contain at least one color")
        return value


class Branding(BaseModel):
    title: str = "Book a Meeting"
    logo: str | None = None
    colors: BrandingColors = BrandingColors()


class CalendarSource(BaseModel):
    url: str
    username: str
    password_env: str

    @property
    def password(self) -> str:
        value = os.environ.get(self.password_env)
        if value is None:
            raise ValueError(f"Environment variable {self.password_env!r} is not set")
        return value


class IcsUrlSource(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _validate_https_scheme(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("ics_urls entries must use https://")
        return value


class ZeitfensterSource(BaseModel):
    url: str
    token_env: str | None = None

    @property
    def token(self) -> str | None:
        if self.token_env is None:
            return None
        value = os.environ.get(self.token_env)
        if not value:
            raise ValueError(
                f"Environment variable {self.token_env!r} is not set or is empty"
            )
        return value


class Availability(BaseModel):
    calendars: list[CalendarSource] = []
    ics_urls: list[IcsUrlSource] = []
    zeitfenster_urls: list[ZeitfensterSource] = []


class Federation(BaseModel):
    free_slots_token_env: str | None = None

    @property
    def free_slots_token(self) -> str | None:
        if self.free_slots_token_env is None:
            return None
        value = os.environ.get(self.free_slots_token_env)
        if not value:
            raise ValueError(
                f"Environment variable {self.free_slots_token_env!r} "
                "is not set or is empty"
            )
        return value


class Captcha(BaseModel):
    enabled: bool = False
    provider: str = "cap"
    api_endpoint: str | None = None
    widget_script_url: str | None = None
    wasm_url: str | None = None
    secret_env: str | None = None

    @model_validator(mode="after")
    def _validate_enabled_config(self) -> "Captcha":
        if not self.enabled:
            return self
        if self.provider != "cap":
            raise ValueError("captcha.provider must be 'cap'")
        missing = [
            name
            for name, value in (
                ("api_endpoint", self.api_endpoint),
                ("widget_script_url", self.widget_script_url),
                ("wasm_url", self.wasm_url),
                ("secret_env", self.secret_env),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "captcha requires these fields when enabled: " + ", ".join(missing)
            )
        self._validate_http_url(self.api_endpoint, "captcha.api_endpoint")
        self._validate_http_url(self.widget_script_url, "captcha.widget_script_url")
        self._validate_http_url(self.wasm_url, "captcha.wasm_url")
        return self

    @staticmethod
    def _validate_http_url(value: str | None, field_name: str) -> None:
        if value is None:
            return
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{field_name} must be an http or https URL")

    @property
    def secret(self) -> str:
        if self.secret_env is None:
            raise ValueError("captcha.secret_env is not configured")
        value = os.environ.get(self.secret_env)
        if not value:
            raise ValueError(
                f"Environment variable {self.secret_env!r} is not set or is empty"
            )
        return value

    @property
    def siteverify_url(self) -> str:
        if self.api_endpoint is None:
            raise ValueError("captcha.api_endpoint is not configured")
        return f"{self.api_endpoint.rstrip('/')}/siteverify"


class Booking(BaseModel):
    location: str | None = None
    owner_name: str | None = None
    summary_template: str = "{customer_name}"
    description_template: str = ""

    @field_validator("summary_template")
    @classmethod
    def _validate_summary_template(cls, value: str) -> str:
        return _validate_template_fields(
            value,
            allowed_fields=SUMMARY_TEMPLATE_FIELDS,
        )

    @field_validator("description_template")
    @classmethod
    def _validate_description_template(cls, value: str) -> str:
        return _validate_template_fields(
            value,
            allowed_fields=DESCRIPTION_TEMPLATE_FIELDS,
        )


class WorkingHours(BaseModel):
    mon: list[str] = []
    tue: list[str] = []
    wed: list[str] = []
    thu: list[str] = []
    fri: list[str] = []
    sat: list[str] = []
    sun: list[str] = []


class Rules(BaseModel):
    timezone: str = "UTC"
    working_hours: WorkingHours = WorkingHours()
    slot_durations: list[str] = ["30m"]
    buffer: str = "15m"
    minimum_notice: str = "24h"
    horizon: str = "60d"
    refresh_interval: str = "15m"


class Email(BaseModel):
    owner: str | list[str]
    from_name: str = "Zeitfenster"
    smtp_host_env: str = "SMTP_HOST"
    smtp_port: int = 587
    smtp_user_env: str = "SMTP_USER"
    smtp_password_env: str = "SMTP_PASSWORD"
    smtp_start_tls: bool = True
    smtp_use_auth: bool = True
    smtp_use_tls: bool = False

    @model_validator(mode="after")
    def _validate_tls_options(self) -> "Email":
        if self.smtp_use_tls and self.smtp_start_tls:
            raise ValueError(
                "smtp_use_tls and smtp_start_tls are mutually exclusive; set "
                "smtp_start_tls: false when using smtp_use_tls (implicit TLS)"
            )
        if self.smtp_use_auth and not (self.smtp_start_tls or self.smtp_use_tls):
            raise ValueError(
                "smtp_use_auth requires smtp_start_tls or smtp_use_tls to be "
                "enabled; sending SMTP credentials over an unencrypted "
                "connection is not allowed"
            )
        return self

    @property
    def owner_list(self) -> list[str]:
        if isinstance(self.owner, list):
            return self.owner
        return [self.owner]

    @property
    def smtp_host(self) -> str:
        value = os.environ.get(self.smtp_host_env)
        if value is None:
            raise ValueError(f"Environment variable {self.smtp_host_env!r} is not set")
        return value

    @property
    def smtp_user(self) -> str:
        value = os.environ.get(self.smtp_user_env)
        if value is None:
            raise ValueError(f"Environment variable {self.smtp_user_env!r} is not set")
        return value

    @property
    def smtp_password(self) -> str:
        value = os.environ.get(self.smtp_password_env)
        if value is None:
            raise ValueError(
                f"Environment variable {self.smtp_password_env!r} is not set"
            )
        return value


class AppConfig(BaseModel):
    branding: Branding = Branding()
    availability: Availability = Availability()
    federation: Federation = Federation()
    captcha: Captcha = Captcha()
    booking: Booking = Booking()
    rules: Rules = Rules()
    email: Email

    @model_validator(mode="before")
    @classmethod
    def _resolve_env_passwords(cls, data: Any) -> Any:
        return data

    @classmethod
    def from_yaml(cls, path: str | Path) -> AppConfig:
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)
