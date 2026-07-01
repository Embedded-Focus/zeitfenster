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


class IcsUrlSource(BaseModel):
    url: str


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
    owner: str | list[str]
    smtp_host_env: str = "SMTP_HOST"
    smtp_port: int = 587
    smtp_user_env: str = "SMTP_USER"
    smtp_password_env: str = "SMTP_PASSWORD"
    smtp_start_tls: bool = True

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
