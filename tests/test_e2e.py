import asyncio

from httpx import ASGITransport, AsyncClient
import pytest
import redis.asyncio as redis

from app.config import get_settings
from app.main import app
from app.worker import GROUP_NAME, STREAM_NAME, init_consumer_group, process_batch

pytestmark = pytest.mark.asyncio


async def test_end_to_end_flow():
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create a unique short link
        create_res = await client.post(
            "/api/v1/links",
            headers=headers,
            json={"url": "https://example.org/e2e-target"},
        )
        assert create_res.status_code == 201
        link_data = create_res.json()
        code = link_data["code"]

        # 2. Follow redirect (simulate click)
        redir_res = await client.get(
            f"/{code}",
            headers={
                "Referer": "https://e2e-referrer.com",
                "User-Agent": "E2ETestAgent/1.0",
            },
            follow_redirects=False,
        )
        assert redir_res.status_code == 302
        assert redir_res.headers["location"] == "https://example.org/e2e-target"

        # 3. If a background worker is running (in docker compose), it will process the event.
        # Otherwise, process manually here.
        stats = None
        for _ in range(10):
            stats_res = await client.get(f"/api/v1/links/{code}/stats")
            assert stats_res.status_code == 200
            stats = stats_res.json()
            if stats["total_clicks"] >= 1:
                break

            # If not yet processed by worker container, read and process manually
            r = redis.from_url(settings.redis_url, decode_responses=True)
            try:
                await init_consumer_group(r)
                entries = await r.xreadgroup(
                    groupname=GROUP_NAME,
                    consumername="e2e-manual-consumer",
                    streams={STREAM_NAME: ">"},
                    count=10,
                    block=500,
                )
                if entries:
                    for _, stream_entries in entries:
                        await process_batch(stream_entries, r)
            finally:
                await r.aclose()

            await asyncio.sleep(0.5)

        assert stats is not None
        assert stats["total_clicks"] >= 1, f"Expected clicks >= 1, got {stats['total_clicks']}"
        assert any(ref["referrer"] == "https://e2e-referrer.com" for ref in stats["top_referrers"])

        # 4. Check dashboard HTML page for this link
        dash_res = await client.get(f"/dashboard/{code}")
        assert dash_res.status_code == 200
        assert code in dash_res.text
        assert "https://e2e-referrer.com" in dash_res.text
