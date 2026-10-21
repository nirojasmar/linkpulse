from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.metrics import REDIRECTS_TOTAL
from app.services.cache import get_cached_link, set_cached_link
from app.services.events import publish_click_event
from app.services.links import get_link_by_code

router = APIRouter(tags=["redirect"])


@router.get("/{code}")
async def redirect_to_target(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Ignore reserved paths that shouldn't be short codes
    if code in (
        "favicon.ico",
        "robots.txt",
        "healthz",
        "readyz",
        "startupz",
        "metrics",
        "version",
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # 1. Look up in Redis cache
    target_url = await get_cached_link(code)

    if target_url:
        REDIRECTS_TOTAL.labels(result="hit").inc()
    else:
        # 2. Query PostgreSQL on cache miss
        link = await get_link_by_code(db, code, include_deleted=False)
        if not link:
            REDIRECTS_TOTAL.labels(result="not_found").inc()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

        target_url = link.target_url
        REDIRECTS_TOTAL.labels(result="miss").inc()
        # Populate cache
        await set_cached_link(code, target_url)

    # 3. Publish click event to Redis Stream (non-blocking / error-safe)
    referrer = request.headers.get("referer") or request.headers.get("referrer")
    user_agent = request.headers.get("user-agent")
    await publish_click_event(code=code, referrer=referrer, user_agent=user_agent)

    # 4. Return 302 redirect
    return RedirectResponse(
        url=target_url,
        status_code=status.HTTP_302_FOUND,
    )
