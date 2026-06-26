# Zeitfenster

Minimal, self-hosted appointment booking service. Reads existing CalDAV calendars to compute availability and presents free slots on a web page. Customers pick a slot and submit their contact details — you receive an email with an `.ics` file to import and send a calendar invitation.

The application never writes to any calendar. You stay in control of every booking.

## How It Works

1. A background task periodically reads your CalDAV calendars (read-only).
2. Free slots are computed based on your working hours, buffer, and other rules.
3. A static HTML page is generated and served by Caddy.
4. When a customer books a slot, a small FastAPI endpoint sends you an email with an `.ics` attachment.
5. You import the `.ics` — your calendar client sends the invitation to the customer.

## Architecture

```
Internet → [Traefik] → Caddy (static files + reverse proxy)
                            ↓ POST /book
                        Python App (FastAPI)
                            ↓ read-only
                        CalDAV Calendars
```

Two containers in production:
- **Caddy** — serves static files, proxies `/book` to the app. No credentials, no Python.
- **Python App** — reads CalDAV, computes slots, generates HTML, sends booking emails. Internal-only, not exposed to the internet.

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
├── app.py              FastAPI app (POST /book, health check, scheduler)
├── availability.py     Free slot computation (merge, buffer, working hours)
├── caldav_client.py    CalDAV read wrapper
├── config.py           Pydantic config (YAML + env vars)
├── email.py            SMTP email with .ics attachment
├── generator.py        Static site generator (Jinja2 → HTML)
├── ics.py              .ics file builder (VEVENT with ATTENDEE)
├── parsing.py          Duration and time range parsing
├── templates/          Jinja2 templates (base, index, thankyou, placeholder)
└── static/             Pico CSS + custom styles

tests/                  Unit and integration tests
demo/                   Demo environment (Radicale config, sample calendars, .env)
Dockerfile              Multi-stage build
Caddyfile               Caddy reverse proxy config
compose.yaml            Demo environment (Caddy + app + Radicale + Mailpit)
compose.prod.yaml       Production override (Traefik labels, no demo services)
pod.yaml                Podman kube reference (production)
config.example.yaml     Example configuration
```

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
