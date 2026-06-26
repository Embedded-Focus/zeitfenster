from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, model_validator


class BrandingColors(BaseModel):
    primary: str = "#2563eb"
    background: str = "#ffffff"


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


class Availability(BaseModel):
    calendars: list[CalendarSource] = []


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


class Email(BaseModel):
    owner: str
    smtp_host_env: str = "SMTP_HOST"
    smtp_port: int = 587
    smtp_user_env: str = "SMTP_USER"
    smtp_password_env: str = "SMTP_PASSWORD"
    smtp_start_tls: bool = True

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
