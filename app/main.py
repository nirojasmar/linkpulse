import asyncio
import contextlib
import random
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import check_db_health, get_engine
from app.logging import get_logger, setup_logging
from app.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL
from app.routers.chaos import chaos_state
from app.routers.chaos import router as chaos_router
from app.routers.dashboard import router as dashboard_router
from app.routers.health import mark_startup_completed
from app.routers.health import router as health_router
from app.routers.links import router as links_router
from app.routers.redirect import router as redirect_router
from app.services.cache import check_redis_health, close_redis_client

logger = get_logger("linkpulse")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(log_level=settings.log_level, pod_name=settings.pod_name)

    logger.info(
        f"Starting Linkpulse API (version={settings.app_version}, pod={settings.pod_name})",
        extra={"config": settings.redacted_dict()},
    )

    # Artificial startup delay if configured
    if settings.startup_delay_seconds > 0:
        logger.info(
            f"Applying artificial startup delay of {settings.startup_delay_seconds} seconds"
        )
        await asyncio.sleep(settings.startup_delay_seconds)

    # Startup dependency check
    db_ok, db_err = await check_db_health(timeout=3.0)
    redis_ok, redis_err = await check_redis_health(timeout=3.0)

    if settings.fail_if_dependency_down_at_startup:
        if not db_ok:
            logger.fatal(
                f"Startup failed: PostgreSQL at {settings.db_target} unreachable: {db_err}"
            )
            raise SystemExit(1)
        if not redis_ok:
            logger.fatal(
                f"Startup failed: Redis at {settings.redis_target} unreachable: {redis_err}"
            )
            raise SystemExit(1)
    else:
        if not db_ok:
            logger.warning(f"PostgreSQL at {settings.db_target} not ready at startup: {db_err}")
        if not redis_ok:
            logger.warning(f"Redis at {settings.redis_target} not ready at startup: {redis_err}")

    mark_startup_completed()
    logger.info("Linkpulse API startup complete and ready to serve traffic.")

    yield

    logger.info("Shutting down Linkpulse API...")
    await close_redis_client()
    engine = get_engine()
    await engine.dispose()
    logger.info("Linkpulse API shutdown finished.")


app = FastAPI(
    title="Linkpulse",
    description="URL shortener with click analytics - Target for Kubernetes troubleshooting",
    version=get_settings().app_version,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_lifecycle_middleware(request: Request, call_next):
    # Extract or generate request ID
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    t0 = time.perf_counter()
    path = request.url.path
    method = request.method

    # Apply chaos fault injection (latency & error rate) if path is not chaos admin
    if not path.startswith("/admin/chaos"):
        if chaos_state.latency_ms > 0:
            await asyncio.sleep(chaos_state.latency_ms / 1000.0)

        if chaos_state.error_percent > 0:
            if random.randint(1, 100) <= chaos_state.error_percent:
                duration_ms = (time.perf_counter() - t0) * 1000
                logger.error(
                    f"{method} {path} - 500 (Chaos Injected Error)",
                    extra={
                        "request_id": request_id,
                        "path": path,
                        "status": 500,
                        "duration_ms": duration_ms,
                    },
                )
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"detail": "Chaos injected internal server error"},
                    headers={"x-request-id": request_id},
                )

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as exc:
        status_code = 500
        duration_ms = (time.perf_counter() - t0) * 1000
        logger.error(
            f"{method} {path} - 500 Exception: {exc}",
            extra={
                "request_id": request_id,
                "path": path,
                "status": 500,
                "duration_ms": duration_ms,
                "error": str(exc),
            },
        )
        raise

    duration_s = time.perf_counter() - t0
    duration_ms = duration_s * 1000

    # Record Prometheus metrics (avoid explosion by using clean path for known endpoints)
    metric_path = path
    if path.startswith("/api/v1/links/"):
        if path.endswith("/stats"):
            metric_path = "/api/v1/links/{code}/stats"
        else:
            metric_path = "/api/v1/links/{code}"
    elif path.startswith("/dashboard/") and path != "/dashboard/":
        metric_path = "/dashboard/{code}"
    elif len(path) > 1 and not path.startswith(("/api", "/admin", "/docs", "/openapi")):
        metric_path = "/{code}"

    HTTP_REQUESTS_TOTAL.labels(method=method, path=metric_path, status=str(status_code)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=metric_path).observe(duration_s)

    # JSON access log to stdout
    logger.info(
        f"{method} {path} - {status_code}",
        extra={
            "request_id": request_id,
            "path": path,
            "status": status_code,
            "duration_ms": duration_ms,
        },
    )

    response.headers["x-request-id"] = request_id
    return response


# Register routers in priority order
app.include_router(health_router)
app.include_router(chaos_router)
app.include_router(links_router)
app.include_router(dashboard_router)
app.include_router(redirect_router)  # Mounted last so /{code} doesn't shadow other routes
