import datetime
import logging
from typing import Optional

from app.config import get_settings
from app.metrics import (
    CLICK_EVENTS_PUBLISH_ERRORS_TOTAL,
    CLICK_EVENTS_PUBLISHED_TOTAL,
)
from app.services.cache import get_redis_client

logger = logging.getLogger("linkpulse")
STREAM_NAME = "clicks"


async def publish_click_event(
    code: str,
    referrer: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """Publishes a click event to the Redis Stream `clicks`.
    Returns True if successful, False otherwise.
    Never raises an exception so redirect is never broken by Redis stream errors.
    """
    settings = get_settings()
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fields = {
        "code": code,
        "ts": ts,
        "referrer": referrer or "",
        "user_agent": user_agent or "",
    }

    try:
        r = get_redis_client()
        await r.xadd(STREAM_NAME, fields)
        CLICK_EVENTS_PUBLISHED_TOTAL.inc()
        return True
    except Exception as exc:
        CLICK_EVENTS_PUBLISH_ERRORS_TOTAL.inc()
        target = settings.redis_target
        logger.error(
            f"Failed to publish click event to stream '{STREAM_NAME}' at {target}: {exc}",
            extra={"target": target, "error": str(exc)},
        )
        return False
