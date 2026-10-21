import asyncio
import logging
from typing import Optional

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger("linkpulse")

_redis_client: Optional[redis.Redis] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_redis_client() -> redis.Redis:
    global _redis_client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_client is None or (_client_loop is not None and _client_loop is not current_loop):
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
        _client_loop = current_loop
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client, _client_loop
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        _client_loop = None


async def get_cached_link(code: str) -> Optional[str]:
    """Retrieves target URL for a code from Redis cache.
    Returns None on cache miss or Redis error (fallback gracefully).
    """
    settings = get_settings()
    try:
        r = get_redis_client()
        return await r.get(f"link:{code}")
    except Exception as exc:
        target = settings.redis_target
        logger.warning(
            f"Redis cache lookup failed for code={code} at {target}: {exc}",
            extra={"target": target, "error": str(exc)},
        )
        return None


async def set_cached_link(code: str, target_url: str, ttl_seconds: Optional[int] = None) -> None:
    """Stores target URL in Redis cache with TTL."""
    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
    try:
        r = get_redis_client()
        await r.set(f"link:{code}", target_url, ex=ttl)
    except Exception as exc:
        target = settings.redis_target
        logger.warning(
            f"Redis cache set failed for code={code} at {target}: {exc}",
            extra={"target": target, "error": str(exc)},
        )


async def delete_cached_link(code: str) -> None:
    """Evicts link from Redis cache."""
    settings = get_settings()
    try:
        r = get_redis_client()
        await r.delete(f"link:{code}")
    except Exception as exc:
        target = settings.redis_target
        logger.warning(
            f"Redis cache eviction failed for code={code} at {target}: {exc}",
            extra={"target": target, "error": str(exc)},
        )


async def check_redis_health(timeout: float = 1.0) -> tuple[bool, Optional[str]]:
    """Checks Redis connectivity with timeout.
    Returns (True, None) if healthy, or (False, error_message) if unhealthy.
    """
    settings = get_settings()
    try:
        r = get_redis_client()
        async with asyncio.timeout(timeout):
            await r.ping()
        return True, None
    except Exception as exc:
        target = settings.redis_target
        err_msg = f"Failed to connect to Redis at {target}: {exc}"
        logger.error(err_msg, extra={"target": target, "error": str(exc)})
        return False, str(exc)
