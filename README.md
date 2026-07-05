# Zeitfenster

Minimal, self-hosted appointment request service. Reads existing calendars (CalDAV, ICS feeds) to compute availability and presents free slots on a web page. Customers pick a slot and submit their contact details — you receive an email with an `.ics` draft event to import, edit, and use for the calendar invitation.

The application never writes to any calendar. You stay in control of every meeting request.

## How It Works

1. A background task periodically reads your calendars — CalDAV, ICS feeds, or both (read-only). The default refresh interval is 15 minutes and can be changed with `rules.refresh_interval`.
2. Free slots are computed based on your working hours, buffer, and other rules.
3. A static HTML page is generated and served by Caddy.
4. When a customer requests a slot, a small FastAPI endpoint sends you an email with an `.ics` attachment.
5. You import the `.ics` draft, add final meeting details or meeting links, and send the actual invitation from your calendar client.

The attached `.ics` files are drafts for the owner. Importing them into the owner's calendar does not send invitations by itself; customer invitations are sent separately from your calendar client after you have reviewed and edited the event.

All-day calendar events are treated as busy for the full local day. Multi-day all-day events, such as vacations, block every working-hour slot they cover.

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

- **Read-only calendars:** the app reads CalDAV and ICS sources, but never writes to calendars. Meeting requests are sent as draft `.ics` email attachments for manual import.
- **Secret isolation:** Caddy serves static files and proxies selected requests, but does not receive CalDAV or SMTP credentials. Those stay in the internal Python app container.
- **No database or sessions:** state is derived from configuration, calendar reads, generated static files, and in-memory availability.
- **Bounded booking input:** booking form fields are normalized and size-limited before use. Names reject control characters, and customer email addresses are checked for a valid basic shape with a dotted domain. The generated form mirrors key limits with native browser validation.
- **Booking slot validation:** `POST /book` does not trust submitted hidden form fields by themselves. The backend parses timezone-aware datetimes, requires `slot_end > slot_start`, checks that the posted duration is configured and matches the submitted range, and requires `(duration, slot_start, slot_end)` to exactly match a currently advertised slot in memory.
- **Request abuse controls:** accepted meeting requests pass through an in-memory global rate limit before email delivery. Request-triggered availability regeneration is coalesced so repeated posts cannot create unlimited concurrent calendar refresh tasks. Caddy also caps `/book` request bodies.
- **Browser hardening:** booking-page JavaScript is served as a static asset, with no inline event handlers. Caddy sends a Content Security Policy, `X-Content-Type-Options: nosniff`, and `Referrer-Policy`.
- **User-facing validation errors:** booking form submissions are intercepted by the static JavaScript. Backend validation failures are mapped back to native browser validation messages instead of exposing raw JSON error responses to normal users.
- **Fail-before-side-effects:** invalid, forged, stale, malformed, or timezone-naive meeting requests are rejected before `.ics` generation, SMTP delivery, or availability regeneration.
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
├── ics.py                  .ics file builder (owner-side draft VEVENT)
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
      token_env: BOB_ZEITFENSTER_TOKEN

federation:
  free_slots_token_env: MY_FREE_SLOTS_TOKEN

email:
  owner:
    - alice@example.com
    - bob@example.com
```

Requirements:
- All member instances and the federation must use the same `slot_durations` and compatible timezones.
- If any member instance is unreachable, the federation shows **no slots** (fail-closed to prevent double-bookings).
- A pure federation instance (no own calendars) works naturally — working-hour candidates are generated locally, then narrowed by intersection.
- Federation authentication is optional on both sides. If `federation.free_slots_token_env` is set, this instance requires `Authorization: Bearer ...` for `GET /api/free-slots`. If a `zeitfenster_urls` member has `token_env`, the federation client sends that token to the member. If no inbound token is configured, `/api/free-slots` is public and computed free slots are scrapeable.
- If a federation token environment variable is configured but missing or empty, startup/fetching fails instead of silently falling back to unauthenticated access.
- On startup, the app logs whether `/api/free-slots` authentication is enabled.

## Configuration

Copy `config.example.yaml` and adjust to your setup. Secrets (CalDAV passwords, SMTP credentials, federation tokens) are referenced by environment variable name, not stored in the config file.

See `config.example.yaml` for all available options including working hours, slot durations, buffer, minimum notice, horizon, refresh interval, branding, and owner-side booking event text/location.

The public page title is configured separately from generated calendar event text. Use `branding.title` for the booking page heading, and `booking.owner_name` plus `booking.summary_template` for the `.ics` event subject.

Owner notification emails use `email.from_name` as the display name for the SMTP sender, defaulting to `Zeitfenster <SMTP_USER>`.

On startup, Zeitfenster generates a placeholder page and retries availability generation if calendar sources are not ready yet. Startup regeneration retries use exponential backoff and can be tuned with `ZEITFENSTER_STARTUP_REGEN_MAX_ATTEMPTS` and `ZEITFENSTER_STARTUP_REGEN_INITIAL_DELAY_SECONDS`.

## Images

The Makefile includes Podman targets for building and pushing an OCI image:

```sh
make build
make push
```

The default image is `registry.example.com/zeitfenster/zeitfenster:1.0.0`. Override `IMAGE` or `TAG` when needed:

```sh
make build TAG=1.0.1
make push IMAGE=registry.example.com/zeitfenster/zeitfenster TAG=1.0.1
```

## Development

```sh
uv sync                       # install dependencies
uv run pytest                 # run tests
uv run pre-commit run --all-files  # lint + format + type check
```

## License

[MIT](LICENSE)
