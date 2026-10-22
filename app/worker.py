import asyncio
import datetime
import logging
import signal
import time
from typing import Any

import redis.asyncio as redis
from prometheus_client import start_http_server
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import get_sessionmaker
from app.logging import setup_logging
from app.metrics import (
    WORKER_BATCH_DURATION_SECONDS,
    WORKER_EVENTS_PROCESSED_TOTAL,
    WORKER_STREAM_PENDING,
)
from app.models import Click, DailyClickCount, Link

STREAM_NAME = "clicks"
GROUP_NAME = "linkpulse-workers"
BATCH_SIZE = 100
BLOCK_TIME_MS = 2000
AUTOCLAIM_IDLE_TIME_MS = 5000

logger = logging.getLogger("linkpulse")
_running = True


def handle_sigterm(signum, frame):
    global _running
    logger.info("Received termination signal, completing current batch and shutting down...")
    _running = False


async def init_consumer_group(r: redis.Redis) -> None:
    try:
        await r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
        logger.info(f"Created Redis stream '{STREAM_NAME}' and consumer group '{GROUP_NAME}'")
    except redis.ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            logger.info(f"Consumer group '{GROUP_NAME}' already exists")
        else:
            raise


async def process_batch(events: list[tuple[str, dict[str, Any]]], r: redis.Redis) -> int:
    """Processes a batch of events: inserts clicks and upserts counts in a single transaction."""
    if not events:
        return 0

    t0 = time.perf_counter()
    sessionmaker = get_sessionmaker()

    # Parse entries
    parsed_events = []
    codes_to_lookup = set()
    event_ids = []

    for entry_id, fields in events:
        event_ids.append(entry_id)
        code = fields.get("code")
        if not code:
            continue
        codes_to_lookup.add(code)

        # Parse timestamp
        raw_ts = fields.get("ts")
        clicked_at = None
        if raw_ts:
            try:
                clicked_at = datetime.datetime.fromisoformat(raw_ts)
            except Exception:
                pass
        if not clicked_at:
            clicked_at = datetime.datetime.now(datetime.timezone.utc)

        parsed_events.append(
            {
                "event_id": entry_id,
                "code": code,
                "clicked_at": clicked_at,
                "referrer": fields.get("referrer") or None,
                "user_agent": fields.get("user_agent") or None,
            }
        )

    if not parsed_events:
        await r.xack(STREAM_NAME, GROUP_NAME, *event_ids)
        return 0

    async with sessionmaker() as session:
        async with session.begin():
            # Lookup links for codes
            stmt = select(Link.id, Link.code).where(Link.code.in_(codes_to_lookup))
            result = await session.execute(stmt)
            link_map = {row.code: row.id for row in result.all()}

            valid_clicks = []

            for ev in parsed_events:
                link_id = link_map.get(ev["code"])
                if not link_id:
                    # Link might have been deleted or invalid code; skip insert but still ack
                    continue

                valid_clicks.append(
                    {
                        "link_id": link_id,
                        "event_id": ev["event_id"],
                        "clicked_at": ev["clicked_at"],
                        "referrer": ev["referrer"],
                        "user_agent": ev["user_agent"],
                    }
                )

            if valid_clicks:
                # Insert clicks, deduping on event_id and returning only inserted rows
                click_stmt = (
                    insert(Click)
                    .values(valid_clicks)
                    .on_conflict_do_nothing(index_elements=["event_id"])
                    .returning(Click.link_id, Click.clicked_at)
                )
                res = await session.execute(click_stmt)
                inserted_rows = res.all()

                # Build daily_aggregates ONLY for actually inserted click events (dedup protection)
                daily_aggregates: dict[tuple[int, datetime.date], int] = {}
                for row in inserted_rows:
                    day = row.clicked_at.date()
                    key = (row.link_id, day)
                    daily_aggregates[key] = daily_aggregates.get(key, 0) + 1

                # Upsert daily click counts
                for (link_id, day), count in daily_aggregates.items():
                    daily_stmt = (
                        insert(DailyClickCount)
                        .values(link_id=link_id, day=day, count=count)
                        .on_conflict_do_update(
                            index_elements=["link_id", "day"],
                            set_={"count": DailyClickCount.count + count},
                        )
                    )
                    await session.execute(daily_stmt)

    # Acknowledge messages in Redis after successful DB commit
    await r.xack(STREAM_NAME, GROUP_NAME, *event_ids)

    duration = time.perf_counter() - t0
    WORKER_BATCH_DURATION_SECONDS.observe(duration)
    count = len(parsed_events)
    WORKER_EVENTS_PROCESSED_TOTAL.inc(count)
    logger.info(
        f"Processed batch of {count} events in {duration * 1000:.2f}ms",
        extra={"duration_ms": duration * 1000, "count": count},
    )
    return count


async def update_pending_metrics(r: redis.Redis) -> None:
    try:
        pending_info = await r.xpending(STREAM_NAME, GROUP_NAME)
        total_pending = pending_info.get("pending", 0) if isinstance(pending_info, dict) else 0
        WORKER_STREAM_PENDING.set(total_pending)
    except Exception as exc:
        logger.debug(f"Could not update pending gauge: {exc}")


async def run_worker() -> None:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, pod_name=settings.pod_name)
    logger.info(
        f"Starting Linkpulse Worker (version={settings.app_version}, pod={settings.pod_name})",
        extra={"config": settings.redacted_dict()},
    )

    # Start Prometheus HTTP metrics server on port 9100 (H2)
    metrics_port = 9100
    try:
        start_http_server(metrics_port)
        logger.info(f"Worker Prometheus metrics server started on port {metrics_port}")
    except Exception as exc:
        logger.warning(f"Could not start metrics server on port {metrics_port}: {exc}")

    consumer_name = f"worker-{settings.pod_name}"
    r = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=3.0,
        socket_timeout=5.0,
    )

    # Ensure stream and group exist
    while _running:
        try:
            await init_consumer_group(r)
            break
        except Exception as exc:
            target = settings.redis_target
            logger.error(
                f"Redis connection failed at {target} during init: {exc}. Retrying in 2s...",
                extra={"target": target, "error": str(exc)},
            )
            await asyncio.sleep(2)

    logger.info(f"Worker listening on group '{GROUP_NAME}', consumer '{consumer_name}'")

    # Claim any pending unacked entries on startup
    start_autoclaim_id = "0-0"
    last_pending_check = 0.0

    while _running:
        try:
            now = time.time()
            if now - last_pending_check > 5.0:
                await update_pending_metrics(r)
                # Attempt autoclaim of unacked entries idle for > 5s
                try:
                    res = await r.xautoclaim(
                        STREAM_NAME,
                        GROUP_NAME,
                        consumer_name,
                        min_idle_time=AUTOCLAIM_IDLE_TIME_MS,
                        start_id=start_autoclaim_id,
                        count=BATCH_SIZE,
                    )
                    next_id, claimed_events, _ = res
                    start_autoclaim_id = next_id if next_id != "0-0" else "0-0"
                    if claimed_events:
                        logger.info(f"Autoclaimed {len(claimed_events)} pending events")
                        await process_batch(claimed_events, r)
                except Exception as exc:
                    logger.warning(f"Error during xautoclaim: {exc}")
                last_pending_check = now

            # Read new events
            entries = await r.xreadgroup(
                groupname=GROUP_NAME,
                consumername=consumer_name,
                streams={STREAM_NAME: ">"},
                count=BATCH_SIZE,
                block=BLOCK_TIME_MS,
            )

            if entries:
                for stream_name, stream_entries in entries:
                    if stream_entries:
                        await process_batch(stream_entries, r)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            target = settings.redis_target
            logger.error(
                f"Error in worker loop contacting {target} or DB {settings.db_target}: {exc}",
                extra={"target": target, "error": str(exc)},
            )
            await asyncio.sleep(2)

    logger.info("Worker shutdown complete.")
    await r.aclose()


def main():
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
