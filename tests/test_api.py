import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio


async def test_health_and_version():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/healthz")
        assert res.status_code == 200
        assert res.json() == {"status": "alive"}

        ver_res = await client.get("/version")
        assert ver_res.status_code == 200
        data = ver_res.json()
        assert "version" in data
        assert "git_sha" in data
        assert "pod" in data

        metrics_res = await client.get("/metrics")
        assert metrics_res.status_code == 200
        assert "http_requests_total" in metrics_res.text


async def test_api_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Without API key
        res = await client.post("/api/v1/links", json={"url": "https://example.com"})
        assert res.status_code == 401

        # With wrong API key
        res = await client.post(
            "/api/v1/links",
            headers={"X-API-Key": "wrong-key"},
            json={"url": "https://example.com"},
        )
        assert res.status_code == 401


async def test_links_crud_and_redirect():
    headers = {"X-API-Key": "dev-secret-api-key"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create link with custom code
        create_res = await client.post(
            "/api/v1/links",
            headers=headers,
            json={"url": "https://httpbin.org/get", "custom_code": "testlink"},
        )
        assert create_res.status_code in (201, 409)

        # Get link
        get_res = await client.get("/api/v1/links/testlink")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["code"] == "testlink"
        assert data["url"] == "https://httpbin.org/get"

        # List links
        list_res = await client.get("/api/v1/links?limit=10&offset=0")
        assert list_res.status_code == 200
        assert list_res.json()["total"] >= 1

        # Follow redirect (follow_redirects=False to verify 302)
        redir_res = await client.get("/testlink", follow_redirects=False)
        assert redir_res.status_code == 302
        assert redir_res.headers["location"] == "https://httpbin.org/get"

        # Check stats endpoint
        stats_res = await client.get("/api/v1/links/testlink/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["code"] == "testlink"
        assert "clicks_last_7_days" in stats
        assert len(stats["clicks_last_7_days"]) == 7


async def test_dashboard_views():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        assert "Recent Links" in res.text
        assert "Linkpulse" in res.text
