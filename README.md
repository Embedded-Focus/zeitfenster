# Zeitfenster

Minimal, self-hosted appointment booking service. Reads existing calendars (CalDAV, ICS feeds) to compute availability and presents free slots on a web page. Customers pick a slot and submit their contact details — you receive an email with an `.ics` file to import and send a calendar invitation.

The application never writes to any calendar. You stay in control of every booking.

## How It Works

1. A background task periodically reads your calendars — CalDAV, ICS feeds, or both (read-only).
2. Free slots are computed based on your working hours, buffer, and other rules.
3. A static HTML page is generated and served by Caddy.
4. When a customer books a slot, a small FastAPI endpoint sends you an email with an `.ics` attachment.
5. You import the `.ics` — your calendar client sends the invitation to the customer.

## Architecture

```
Internet → [Traefik] → Caddy (static files + reverse proxy)
                            ↓ POST /book, GET /api/free-slots
                        Python App (FastAPI)
                            ↓ read-only
                        CalDAV / ICS Calendars
```

Two containers in production:
- **Caddy** — serves static files, proxies `/book` and `/api/*` to the app. No credentials, no Python.
- **Python App** — reads calendars, computes slots, generates HTML, sends booking emails. Internal-only, not exposed to the internet.

## Security

Zeitfenster is designed around a small public surface and a secret-free frontend container.

- **Read-only calendars:** the app reads CalDAV and ICS sources, but never writes to calendars. Booking requests are sent as `.ics` email attachments for manual import.
- **Secret isolation:** Caddy serves static files and proxies selected requests, but does not receive CalDAV or SMTP credentials. Those stay in the internal Python app container.
- **No database or sessions:** state is derived from configuration, calendar reads, generated static files, and in-memory availability.
- **Bounded booking input:** booking form fields are normalized and size-limited before use. Names reject control characters, and customer email addresses are checked for a valid basic shape.
- **Booking slot validation:** `POST /book` does not trust submitted hidden form fields by themselves. The backend parses timezone-aware datetimes, requires `slot_end > slot_start`, checks that the posted duration is configured and matches the submitted range, and requires `(duration, slot_start, slot_end)` to exactly match a currently advertised slot in memory.
- **Fail-before-side-effects:** invalid, forged, stale, malformed, or timezone-naive booking requests are rejected before `.ics` generation, SMTP delivery, or availability regeneration.
- **Federation privacy boundary:** `/api/free-slots` exposes computed free slots only. Federation members do not receive raw busy intervals or calendar event details.

## Quick Start (Demo)

```sh
make up
```

This starts a full demo environment with:
- Booking page at `http://localhost:8080`
- Mailpit (email viewer) at `http://localhost:8025`
- Radicale (CalDAV server) with sample recurring events

## Project Layout

```
src/zeitfenster/
├── app.py                  FastAPI app (POST /book, GET /api/free-slots, scheduler)
├── availability.py         Free slot computation, intersection, orchestrator
├── caldav_client.py        CalDAV read wrapper
├── ics_client.py           ICS URL feed reader
├── zeitfenster_client.py   Federation client (fetches remote free slots)
├── config.py               Pydantic config (YAML + env vars)
├── email.py                SMTP email with .ics attachment (multi-recipient)
├── generator.py            Static site generator (Jinja2 → HTML)
├── ics.py                  .ics file builder (VEVENT with ATTENDEE)
├── parsing.py              Duration and time range parsing
├── templates/              Jinja2 templates (base, index, thankyou, placeholder)
└── static/                 Pico CSS + custom styles

tests/                  Unit and integration tests
demo/                   Demo environment (Radicale config, sample calendars, .env)
Dockerfile              Multi-stage build
Caddyfile               Caddy reverse proxy config
compose.yaml            Demo environment (Caddy + app + Radicale + Mailpit)
compose.prod.yaml       Production override (Traefik labels, no demo services)
pod.yaml                Podman kube reference (production)
config.example.yaml     Example configuration
```

## Federation

Multiple zeitfenster instances can be federated so customers only see slots when **all** team members are free. Each instance exposes its computed free slots via `GET /api/free-slots`. A federation instance fetches those and intersects them — it never learns individual busy times.

```yaml
availability:
  zeitfenster_urls:
    - url: https://alice.example.com
    - url: https://bob.example.com

email:
  owner:
    - alice@example.com
    - bob@example.com
```

Requirements:
- All member instances and the federation must use the same `slot_durations` and compatible timezones.
- If any member instance is unreachable, the federation shows **no slots** (fail-closed to prevent double-bookings).
- A pure federation instance (no own calendars) works naturally — working-hour candidates are generated locally, then narrowed by intersection.

## Configuration

Copy `config.example.yaml` and adjust to your setup. Secrets (CalDAV passwords, SMTP credentials) are referenced by environment variable name, not stored in the config file.

See `config.example.yaml` for all available options including working hours, slot durations, buffer, minimum notice, horizon, and branding.

## Development

```sh
uv sync                       # install dependencies
uv run pytest                 # run tests
uv run pre-commit run --all-files  # lint + format + type check
```

## License

[MIT](LICENSE)
