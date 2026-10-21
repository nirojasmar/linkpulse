from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.routers.chaos import require_api_key
from app.schemas import (
    LinkCreate,
    LinkListResponse,
    LinkResponse,
    LinkStatsResponse,
)
from app.services.links import (
    create_link,
    get_link_by_code,
    get_link_stats,
    list_links,
    soft_delete_link,
)

router = APIRouter(prefix="/api/v1/links", tags=["links"])


def build_short_url(code: str) -> str:
    settings = get_settings()
    base = settings.base_url.rstrip("/")
    return f"{base}/{code}"


@router.post("", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
async def create_new_link(
    payload: LinkCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Creates a new short link. Requires API key."""
    try:
        link = await create_link(
            db=db,
            target_url=payload.url,
            custom_code=payload.custom_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return LinkResponse(
        code=link.code,
        short_url=build_short_url(link.code),
        url=link.target_url,
        created_at=link.created_at,
    )


@router.get("", response_model=LinkListResponse)
async def get_links(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Lists links with pagination."""
    items, total = await list_links(db, offset=offset, limit=limit)
    response_items = [
        LinkResponse(
            code=item.code,
            short_url=build_short_url(item.code),
            url=item.target_url,
            created_at=item.created_at,
        )
        for item in items
    ]
    return LinkListResponse(
        items=response_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{code}", response_model=LinkResponse)
async def get_link(code: str, db: AsyncSession = Depends(get_db)):
    """Retrieves link details."""
    link = await get_link_by_code(db, code, include_deleted=False)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    return LinkResponse(
        code=link.code,
        short_url=build_short_url(link.code),
        url=link.target_url,
        created_at=link.created_at,
    )


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    code: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_api_key),
):
    """Soft-deletes a link and clears cache. Requires API key."""
    deleted = await soft_delete_link(db, code)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return None


@router.get("/{code}/stats", response_model=LinkStatsResponse)
async def get_stats(code: str, db: AsyncSession = Depends(get_db)):
    """Retrieves click statistics for a link."""
    stats = await get_link_stats(db, code)
    if not stats:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    return stats
