# Zeitfenster

Minimal, self-hosted appointment booking service. Reads existing calendars (CalDAV + ICS URLs) to compute availability, generates a static booking page, and emails `.ics` files to the owner on booking.

## Design Principles

- **Read-only calendar access** — the app never writes to any calendar. The owner manually accepts bookings by importing the `.ics` attachment.
- **Stateless** — no database, no sessions. Configuration via YAML + environment variables.
- **Security first** — the web-facing container (Caddy) holds zero secrets. CalDAV/SMTP credentials stay isolated in the internal Python backend.
- **No inline JavaScript** — no SPA framework, no analytics.

## Security Invariants

- `POST /book` must never trust submitted slot fields by themselves. Before generating an `.ics`, sending email, or scheduling regeneration, validate that `(duration, slot_start, slot_end)` exactly matches a currently advertised slot in `app.state.current_slots`.
- Invalid public input must fail before SMTP, calendar fetching, or filesystem writes are triggered.
- Keep `/api/free-slots` limited to computed free slots. Never expose raw busy intervals, calendar event metadata, CalDAV details, or secrets.

## Tech Stack

- Python 3.14+, FastAPI, Jinja2, Pico CSS
- `caldav` — CalDAV client (read-only)
- `icalendar` + `recurring-ical-events` — ICS parsing and recurring event expansion
- `aiosmtplib` — async email
- `pydantic` + `pyyaml` — configuration
- `structlog` — logging

## Architecture

Two-container setup: Caddy serves static HTML from a shared `/site` volume and proxies `POST /book` to the internal Python app. The Python app is not exposed to the internet.

Calendar sources:
- **CalDAV** (`availability.calendars`) — username/password auth, for self-hosted servers like Radicale
- **ICS URLs** (`availability.ics_urls`) — read-only `.ics` feeds, for Google Calendar ("secret address in iCal format")

Both source types produce `BusyInterval` lists that are merged, buffered, and subtracted from working hours to compute free slots.

### Federation

Multiple zeitfenster instances can be federated so customers only see slots when **all** members are free. Each instance exposes `GET /api/free-slots` (JSON). A federation instance fetches each member's free slots and intersects them — it never sees individual busy times.

- **Config**: `availability.zeitfenster_urls` lists member instance URLs
- **Fail-closed**: if any member instance is unreachable, the federation shows no slots (prevents double-bookings)
- **Slot alignment**: all instances must use the same `slot_durations` and compatible timezones for exact `(start, end)` matching
- **Multi-owner email**: `email.owner` accepts a list of addresses so all team members receive booking notifications
- **Pure federation** (no own calendars) works naturally — working-hour candidates are generated locally, then narrowed by intersection

## Key Modules

- `config.py` — Pydantic models, YAML loading, env var resolution for secrets
- `caldav_client.py` — CalDAV fetch → `BusyInterval` list
- `ics_client.py` — ICS URL fetch → `BusyInterval` list
- `zeitfenster_client.py` — fetches free slots from remote zeitfenster instances (federation)
- `availability.py` — merging, buffering, free slot computation, intersection, orchestrator (`fetch_and_compute`)
- `generator.py` — Jinja2 rendering, atomic file swap to `/site`
- `app.py` — FastAPI (POST `/book`, GET `/api/free-slots`, GET `/health`, lifespan scheduler)
- `ics.py` — builds `.ics` attachments for booking emails
- `email.py` — SMTP sending (supports multiple recipients)

## Verification

Use `uv` for all Python commands. A PostToolUse hook runs `uv run pre-commit run --all-files` automatically after every file edit, so formatting and lint violations are caught immediately. Before committing, verify manually:

```sh
uv run pre-commit run --all-files
uv run pytest
```

## Running Locally

```sh
# Demo environment (Caddy + app + Radicale + Mailpit)
make up        # browse localhost:8080 (booking) + localhost:8025 (emails)
make down
make logs
```

## Configuration

See `config.example.yaml` for all options. Secrets are referenced by environment variable name (`password_env`, `smtp_password_env`, etc.), never stored in the YAML directly.
