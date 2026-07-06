import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from zeitfenster.availability import FreeSlot
from zeitfenster.config import AppConfig
from zeitfenster.generator import generate_placeholder, generate_site

TZ = ZoneInfo("Europe/Vienna")

OUTPUT_DIR = Path(__file__).parent / "output"
ROOT_DIR = Path(__file__).parents[1]


def _make_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "branding": {
                "title": "Book a Meeting with Rainer",
                "logo": "/static/logo.svg",
                "colors": {
                    "background": "#101820",
                    "text": "#f5f7fa",
                    "muted_text": "#b9c0ca",
                    "primary": "#0d6efd",
                    "primary_hover": "#0b5ed7",
                    "primary_focus": "rgba(13, 110, 253, 0.25)",
                    "primary_inverse": "#ffffff",
                    "surface": "#182430",
                    "surface_border": "#2d3b48",
                    "surface_section": "#1d2a38",
                    "form_background": "#111b25",
                    "form_border": "#405060",
                    "form_active_background": "#172230",
                    "slot_colors": ["#ff0000", "#00aa00"],
                    "slot_backgrounds": ["#ffeeee", "#eeffee"],
                },
            },
            "email": {"owner": "test@example.com"},
            "rules": {
                "timezone": "Europe/Vienna",
                "slot_durations": ["30m", "60m", "90m"],
            },
        }
    )


def _make_fake_slots() -> dict[str, list[FreeSlot]]:
    base = datetime(2026, 7, 6, 0, 0, tzinfo=TZ)  # Monday

    slots: dict[str, list[FreeSlot]] = {"30m": [], "60m": [], "90m": []}

    for day_offset in range(5):  # Mon–Fri
        day = base + timedelta(days=day_offset)

        for hour in (9, 10, 11, 13, 14, 15, 16):
            start = day.replace(hour=hour, minute=0)
            slots["30m"].append(
                FreeSlot(
                    start=start,
                    end=start + timedelta(minutes=30),
                    duration=timedelta(minutes=30),
                )
            )
            if hour != 16:
                slots["30m"].append(
                    FreeSlot(
                        start=start + timedelta(minutes=30),
                        end=start + timedelta(minutes=60),
                        duration=timedelta(minutes=30),
                    )
                )

        for hour in (9, 10, 11, 13, 14, 15):
            start = day.replace(hour=hour, minute=0)
            slots["60m"].append(
                FreeSlot(
                    start=start,
                    end=start + timedelta(hours=1),
                    duration=timedelta(hours=1),
                )
            )

        for hour in (9, 10, 13, 14):
            start = day.replace(hour=hour, minute=0)
            slots["90m"].append(
                FreeSlot(
                    start=start,
                    end=start + timedelta(minutes=90),
                    duration=timedelta(minutes=90),
                )
            )

    return slots


class TestGenerateSite:
    def test_generates_index_and_thankyou(self):
        config = _make_config()
        slots = _make_fake_slots()
        with tempfile.TemporaryDirectory() as tmp:
            generate_site(slots, config, tmp)
            index = Path(tmp) / "index.html"
            thankyou = Path(tmp) / "thankyou.html"
            static = Path(tmp) / "static"
            assert index.exists()
            assert thankyou.exists()
            assert static.exists()
            assert (static / "pico.min.css").exists()
            assert (static / "style.css").exists()
            assert (static / "booking.js").exists()
            assert (static / "logo.svg").exists()
            assert (static / "logo.svg").read_text() == (
                ROOT_DIR / "logo.svg"
            ).read_text()

            html = index.read_text()
            assert "Book a Meeting with Rainer" in html
            assert (
                '<link rel="icon" href="/static/logo.svg" type="image/svg+xml">' in html
            )
            assert 'class="brand-heading"' in html
            assert 'class="brand-copy"' in html
            assert '<img src="/static/logo.svg"' in html
            assert "30m" in html
            assert "60m" in html
            assert "90m" in html
            assert "09:00" in html
            assert "Monday" in html
            assert 'src="static/booking.js"' in html
            assert "<script>" not in html
            assert "onclick=" not in html
            assert 'maxlength="100"' in html
            assert 'maxlength="254"' in html
            assert 'pattern="[^@\\s]+@[^@\\s]+\\.[^@\\s]+"' in html
            assert "--pico-background-color: #101820" in html
            assert "--pico-color: #f5f7fa" in html
            assert "--pico-primary-hover: #0b5ed7" in html
            assert "--pico-card-background-color: #182430" in html
            assert "--pico-form-element-border-color: #405060" in html
            assert "--duration-color: #ff0000" in html
            assert "--duration-color: #00aa00" in html
            assert "--duration-pastel: #ffeeee" in html
            assert "--duration-pastel: #eeffee" in html
            assert "Request this slot" in html
            assert "Send Request" in html
            thankyou_html = thankyou.read_text()
            assert "Your meeting request has been received." in thankyou_html
            assert "not confirmed" in thankyou_html

    def test_copies_custom_static_files(self):
        config = _make_config()
        slots = _make_fake_slots()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom_static = root / "custom-src"
            custom_static.mkdir()
            (custom_static / "logo.svg").write_text("<svg></svg>")
            nested = custom_static / "images"
            nested.mkdir()
            (nested / "badge.txt").write_text("badge")

            generate_site(slots, config, root / "site", custom_static)

            static = root / "site" / "static"
            assert (static / "custom" / "logo.svg").read_text() == "<svg></svg>"
            assert (static / "custom" / "images" / "badge.txt").read_text() == "badge"

    def test_uses_configured_logo_as_favicon(self):
        config = _make_config()
        config.branding.logo = "/static/custom/logo.svg"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom_static = root / "custom-src"
            custom_static.mkdir()
            (custom_static / "logo.svg").write_text("<svg></svg>")

            generate_site(_make_fake_slots(), config, root / "site", custom_static)

            html = (root / "site" / "index.html").read_text()
            assert (
                '<link rel="icon" href="/static/custom/logo.svg" type="image/svg+xml">'
            ) in html
            assert '<img src="/static/custom/logo.svg"' in html

    def test_favicon_falls_back_to_bundled_logo(self):
        config = _make_config()
        config.branding.logo = None
        with tempfile.TemporaryDirectory() as tmp:
            generate_site(_make_fake_slots(), config, tmp)

            html = (Path(tmp) / "index.html").read_text()
            assert (
                '<link rel="icon" href="static/logo.svg" type="image/svg+xml">' in html
            )
            assert "<img src=" not in html

    def test_missing_custom_static_directory_is_ignored(self):
        config = _make_config()
        slots = _make_fake_slots()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_site(slots, config, root / "site", root / "missing")

            assert (root / "site" / "static" / "booking.js").exists()
            assert not (root / "site" / "static" / "custom").exists()

    def test_custom_static_symlink_is_rejected(self):
        config = _make_config()
        slots = _make_fake_slots()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom_static = root / "custom-src"
            custom_static.mkdir()
            (custom_static / "target.txt").write_text("target")
            (custom_static / "link.txt").symlink_to(custom_static / "target.txt")

            with pytest.raises(ValueError, match="symlink"):
                generate_site(slots, config, root / "site", custom_static)

    def test_generates_placeholder(self):
        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            generate_placeholder(config, tmp)
            index = Path(tmp) / "index.html"
            assert index.exists()
            html = index.read_text()
            assert "Generating availability" in html
            assert "Book a Meeting with Rainer" in html
            assert (
                '<link rel="icon" href="/static/logo.svg" type="image/svg+xml">' in html
            )
            assert (Path(tmp) / "static" / "booking.js").exists()
            assert (Path(tmp) / "static" / "logo.svg").exists()

    def test_booking_script_handles_submit_errors(self):
        config = _make_config()
        slots = _make_fake_slots()
        with tempfile.TemporaryDirectory() as tmp:
            generate_site(slots, config, tmp)
            script = (Path(tmp) / "static" / "booking.js").read_text()
            assert 'document.addEventListener("submit"' in script
            assert "fetch(form.action" in script
            assert "setCustomValidity" in script
            assert "reportValidity" in script

    def test_empty_slots(self):
        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            generate_site({"30m": [], "60m": [], "90m": []}, config, tmp)
            html = (Path(tmp) / "index.html").read_text()
            assert "No available slots" in html

    def test_atomic_swap_replaces_existing(self):
        config = _make_config()
        slots = _make_fake_slots()
        with tempfile.TemporaryDirectory() as tmp:
            generate_placeholder(config, tmp)
            assert "Generating availability" in (Path(tmp) / "index.html").read_text()
            generate_site(slots, config, tmp)
            html = (Path(tmp) / "index.html").read_text()
            assert "Generating availability" not in html
            assert "09:00" in html


class TestVisualPreview:
    def test_generate_preview(self):
        """Generates a preview site in tests/output/ for visual inspection.

        After running this test, open tests/output/index.html in a browser.
        """
        config = _make_config()
        slots = _make_fake_slots()

        if OUTPUT_DIR.exists():
            shutil.rmtree(OUTPUT_DIR)

        generate_site(slots, config, OUTPUT_DIR)

        assert (OUTPUT_DIR / "index.html").exists()
        assert (OUTPUT_DIR / "thankyou.html").exists()
        assert (OUTPUT_DIR / "static" / "pico.min.css").exists()
        print(f"\n  Preview generated at: {OUTPUT_DIR / 'index.html'}")
        print("  Open in browser to see the booking page.\n")
