from __future__ import annotations

import shutil
import tempfile
from collections import OrderedDict
from datetime import timedelta
from pathlib import Path

import structlog
from jinja2 import Environment, PackageLoader

from zeitfenster.availability import FreeSlot
from zeitfenster.config import AppConfig

logger = structlog.get_logger()

_STATIC_DIR = Path(__file__).parent / "static"


def _build_template_env() -> Environment:
    return Environment(
        loader=PackageLoader("zeitfenster", "templates"),
        autoescape=True,
    )


def _format_duration(td: timedelta) -> str:
    total_minutes = int(td.total_seconds() // 60)
    if total_minutes >= 60 and total_minutes % 60 == 0:
        hours = total_minutes // 60
        return f"{hours}h"
    return f"{total_minutes}m"


def _prepare_slots_for_template(
    slots_by_duration: dict[str, list[FreeSlot]],
) -> dict[str, OrderedDict[str, list[dict]]]:
    result: dict[str, OrderedDict[str, list[dict]]] = {}

    for duration_label, slots in slots_by_duration.items():
        days: OrderedDict[str, list[dict]] = OrderedDict()
        for slot in slots:
            day_label = slot.start.strftime("%A, %B %-d, %Y")
            if day_label not in days:
                days[day_label] = []
            days[day_label].append(
                {
                    "start_time": slot.start.strftime("%H:%M"),
                    "end_time": slot.end.strftime("%H:%M"),
                    "start_iso": slot.start.isoformat(),
                    "end_iso": slot.end.isoformat(),
                }
            )
        result[duration_label] = days

    return result


def generate_site(
    slots_by_duration: dict[str, list[FreeSlot]],
    config: AppConfig,
    output_dir: str | Path,
) -> None:
    output_dir = Path(output_dir)
    env = _build_template_env()

    template_data = _prepare_slots_for_template(slots_by_duration)
    context = {
        "branding": config.branding,
        "slots_by_duration": template_data,
    }

    tmp_dir = Path(tempfile.mkdtemp(prefix="zeitfenster_"))
    try:
        index_template = env.get_template("index.html.j2")
        (tmp_dir / "index.html").write_text(index_template.render(**context))

        thankyou_template = env.get_template("thankyou.html.j2")
        (tmp_dir / "thankyou.html").write_text(
            thankyou_template.render(branding=config.branding)
        )

        static_dest = tmp_dir / "static"
        shutil.copytree(_STATIC_DIR, static_dest)

        _atomic_swap(tmp_dir, output_dir)
        logger.info("site_generated", output_dir=str(output_dir))
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def generate_placeholder(config: AppConfig, output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    env = _build_template_env()

    tmp_dir = Path(tempfile.mkdtemp(prefix="zeitfenster_"))
    try:
        template = env.get_template("placeholder.html.j2")
        (tmp_dir / "index.html").write_text(template.render(branding=config.branding))

        static_dest = tmp_dir / "static"
        shutil.copytree(_STATIC_DIR, static_dest)

        _atomic_swap(tmp_dir, output_dir)
        logger.info("placeholder_generated", output_dir=str(output_dir))
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _atomic_swap(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)

    for item in dest.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    for item in src.iterdir():
        shutil.move(str(item), str(dest / item.name))

    shutil.rmtree(src, ignore_errors=True)
