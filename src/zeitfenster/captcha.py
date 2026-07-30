import asyncio
import json

import httpx2
import structlog
from fastapi import HTTPException

from zeitfenster.booking_request import validate_bounded_field
from zeitfenster.config import AppConfig

logger = structlog.get_logger()

MAX_CAP_TOKEN_LENGTH = 4096
CAPTCHA_VERIFY_TIMEOUT_SECONDS = 5.0


async def verify_captcha_token(config: AppConfig, token: str) -> None:
    if not config.captcha.enabled:
        return

    token = validate_bounded_field(token, "cap-token", MAX_CAP_TOKEN_LENGTH)
    if not token:
        raise HTTPException(status_code=400, detail="CAPTCHA token is required")

    try:
        response = await asyncio.to_thread(
            httpx2.post,
            config.captcha.siteverify_url,
            json={"secret": config.captcha.secret, "response": token},
            timeout=CAPTCHA_VERIFY_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        response.raise_for_status()
        data = json.loads(response.content)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("captcha_verification_unavailable")
        raise HTTPException(
            status_code=503,
            detail="CAPTCHA verification is unavailable",
        ) from exc

    if data.get("success") is not True:
        raise HTTPException(status_code=400, detail="CAPTCHA verification failed")
