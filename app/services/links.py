import datetime
import secrets
import string
import time
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.metrics import DB_QUERY_DURATION_SECONDS
from app.models import Click, DailyClickCount, Link
from app.schemas import DailyClickStat, LinkStatsResponse, ReferrerStat
from app.services.cache import delete_cached_link

BASE62_CHARS = string.digits + string.ascii_letters


def generate_code(length: int = 7) -> str:
    """Generates a random base62 string of given length."""
    return "".join(secrets.choice(BASE62_CHARS) for _ in range(length))


async def create_link(
    db: AsyncSession,
    target_url: str,
    custom_code: Optional[str] = None,
) -> Link:
    """Creates a new short link, generating a base62 code if none provided."""
    if custom_code:
        # Check conflict
        t0 = time.perf_counter()
        query = select(Link).where(Link.code == custom_code)
        result = await db.execute(query)
        DB_QUERY_DURATION_SECONDS.labels(query_type="select").observe(time.perf_counter() - t0)
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Code '{custom_code}' already exists")
        code = custom_code
    else:
        # Generate 7-char code and check collision
        max_attempts = 10
        code = None
        for _ in range(max_attempts):
            candidate = generate_code(7)
            t0 = time.perf_counter()
            query = select(Link).where(Link.code == candidate)
            result = await db.execute(query)
            DB_QUERY_DURATION_SECONDS.labels(query_type="select").observe(time.perf_counter() - t0)
            if not result.scalar_one_or_none():
                code = candidate
                break
        if code is None:
            raise RuntimeError("Failed to generate unique short code after multiple attempts")

    link = Link(
        code=code,
        target_url=target_url,
    )
    db.add(link)
    t0 = time.perf_counter()
    await db.commit()
    await db.refresh(link)
    DB_QUERY_DURATION_SECONDS.labels(query_type="insert").observe(time.perf_counter() - t0)
    return link


async def get_link_by_code(
    db: AsyncSession,
    code: str,
    include_deleted: bool = False,
) -> Optional[Link]:
    """Finds link by code."""
    t0 = time.perf_counter()
    query = select(Link).where(Link.code == code)
    if not include_deleted:
        query = query.where(Link.deleted_at.is_(None))
    result = await db.execute(query)
    DB_QUERY_DURATION_SECONDS.labels(query_type="select").observe(time.perf_counter() - t0)
    return result.scalar_one_or_none()


async def soft_delete_link(db: AsyncSession, code: str) -> bool:
    """Soft-deletes link and evicts from Redis cache.
    Returns True if found and deleted, False if not found.
    """
    link = await get_link_by_code(db, code, include_deleted=False)
    if not link:
        return False

    link.deleted_at = datetime.datetime.now(datetime.timezone.utc)
    t0 = time.perf_counter()
    await db.commit()
    DB_QUERY_DURATION_SECONDS.labels(query_type="update").observe(time.perf_counter() - t0)

    # Evict from Redis
    await delete_cached_link(code)
    return True


async def list_links(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Link], int]:
    """Returns paginated active links and total count."""
    t0 = time.perf_counter()
    count_query = select(func.count(Link.id)).where(Link.deleted_at.is_(None))
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = (
        select(Link)
        .where(Link.deleted_at.is_(None))
        .order_by(desc(Link.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    items = list(result.scalars().all())
    DB_QUERY_DURATION_SECONDS.labels(query_type="select").observe(time.perf_counter() - t0)
    return items, total


async def get_link_stats(db: AsyncSession, code: str) -> Optional[LinkStatsResponse]:
    """Calculates statistics for a given link."""
    link = await get_link_by_code(db, code, include_deleted=False)
    if not link:
        return None

    t0 = time.perf_counter()

    # Total clicks
    total_query = select(func.count(Click.id)).where(Click.link_id == link.id)
    total_result = await db.execute(total_query)
    total_clicks = total_result.scalar_one() or 0

    # Clicks last 7 days
    today = datetime.datetime.now(datetime.timezone.utc).date()
    seven_days_ago = today - datetime.timedelta(days=6)

    daily_query = select(DailyClickCount.day, DailyClickCount.count).where(
        DailyClickCount.link_id == link.id,
        DailyClickCount.day >= seven_days_ago,
        DailyClickCount.day <= today,
    )
    daily_res = await db.execute(daily_query)
    daily_map = {row.day: row.count for row in daily_res.all()}

    # Ensure all 7 days have an entry
    clicks_last_7_days = []
    for i in range(7):
        d = seven_days_ago + datetime.timedelta(days=i)
        clicks_last_7_days.append(DailyClickStat(day=d.isoformat(), count=daily_map.get(d, 0)))

    # Top referrers (top 10)
    ref_query = (
        select(Click.referrer, func.count(Click.id).label("ref_count"))
        .where(Click.link_id == link.id)
        .group_by(Click.referrer)
        .order_by(desc("ref_count"))
        .limit(10)
    )
    ref_res = await db.execute(ref_query)
    top_referrers = []
    for row in ref_res.all():
        ref_name = row.referrer.strip() if row.referrer and row.referrer.strip() else "direct"
        top_referrers.append(ReferrerStat(referrer=ref_name, count=row.ref_count))

    DB_QUERY_DURATION_SECONDS.labels(query_type="select").observe(time.perf_counter() - t0)

    return LinkStatsResponse(
        code=link.code,
        target_url=link.target_url,
        total_clicks=total_clicks,
        clicks_last_7_days=clicks_last_7_days,
        top_referrers=top_referrers,
    )
