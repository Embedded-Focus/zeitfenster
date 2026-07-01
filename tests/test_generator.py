from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from zeitfenster.availability import FreeSlot
from zeitfenster.config import AppConfig
from zeitfenster.generator import generate_placeholder, generate_site

TZ = ZoneInfo("Europe/Vienna")

OUTPUT_DIR = Path(__file__).parent / "output"


def _make_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "branding": {
                "title": "Book a Meeting with Rainer",
                "colors": {"primary": "#0d6efd", "background": "#ffffff"},
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

            html = index.read_text()
            assert "Book a Meeting with Rainer" in html
            assert "30m" in html
            assert "60m" in html
            assert "90m" in html
            assert "09:00" in html
            assert "Monday" in html
            assert 'src="static/booking.js"' in html
            assert "<script>" not in html
            assert "onclick=" not in html

    def test_generates_placeholder(self):
        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            generate_placeholder(config, tmp)
            index = Path(tmp) / "index.html"
            assert index.exists()
            html = index.read_text()
            assert "Generating availability" in html
            assert "Book a Meeting with Rainer" in html
            assert (Path(tmp) / "static" / "booking.js").exists()

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
