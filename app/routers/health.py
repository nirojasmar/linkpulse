import asyncio

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import check_db_health
from app.metrics import metrics_response
from app.routers.chaos import chaos_state
from app.schemas import VersionResponse
from app.services.cache import check_redis_health

router = APIRouter(tags=["health"])

# Global flag set to True when startup tasks complete
_started = False


def mark_startup_completed():
    global _started
    _started = True


@router.get("/healthz")
async def healthz():
    """Liveness probe. Does not check external dependencies."""
    if chaos_state.hang_healthz:
        # Simulate hung process: sleep indefinitely (probe will time out)
        await asyncio.sleep(3600)
    return {"status": "alive"}


@router.get("/readyz")
async def readyz():
    """Readiness probe. Checks PostgreSQL and Redis with 1s timeout."""
    if chaos_state.unready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unready", "reason": "chaos_injected"},
        )

    db_ok, db_err = await check_db_health(timeout=1.0)
    redis_ok, redis_err = await check_redis_health(timeout=1.0)

    details = {
        "database": "ok" if db_ok else f"failed: {db_err}",
        "redis": "ok" if redis_ok else f"failed: {redis_err}",
    }

    if not db_ok or not redis_ok:
        details["status"] = "unready"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=details,
        )

    details["status"] = "ready"
    return details


@router.get("/startupz")
async def startupz():
    """Startup probe. Returns 200 once app initialization is complete."""
    if not _started:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "starting"},
        )
    return {"status": "started"}


@router.get("/version", response_model=VersionResponse)
async def version():
    """Returns application version, git SHA and pod name."""
    settings = get_settings()
    return VersionResponse(
        version=settings.app_version,
        git_sha=settings.git_sha,
        pod=settings.pod_name,
    )


@router.get("/metrics")
async def metrics():
    """Prometheus metrics scrape endpoint."""
    return metrics_response()
