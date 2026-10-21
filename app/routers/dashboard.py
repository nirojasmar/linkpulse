from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import DailyClickCount, Link
from app.services.links import get_link_stats

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request, db: AsyncSession = Depends(get_db)):
    settings = get_settings()

    # Query 20 most recent links with total clicks
    query = (
        select(
            Link.code,
            Link.target_url,
            Link.created_at,
            func.coalesce(func.sum(DailyClickCount.count), 0).label("click_count"),
        )
        .outerjoin(DailyClickCount, Link.id == DailyClickCount.link_id)
        .where(Link.deleted_at.is_(None))
        .group_by(Link.id, Link.code, Link.target_url, Link.created_at)
        .order_by(desc(Link.created_at))
        .limit(20)
    )
    result = await db.execute(query)
    links = [
        {
            "code": row.code,
            "target_url": row.target_url,
            "created_at": row.created_at,
            "click_count": row.click_count,
        }
        for row in result.all()
    ]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "links": links,
            "pod_name": settings.pod_name,
            "app_version": settings.app_version,
            "git_sha": settings.git_sha,
        },
    )


@router.get("/dashboard/{code}", response_class=HTMLResponse)
async def dashboard_detail(code: str, request: Request, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    stats = await get_link_stats(db, code)
    if not stats:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    return templates.TemplateResponse(
        request=request,
        name="detail.html",
        context={
            "stats": stats,
            "pod_name": settings.pod_name,
            "app_version": settings.app_version,
            "git_sha": settings.git_sha,
        },
    )
