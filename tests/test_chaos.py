import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routers.chaos import chaos_state

pytestmark = pytest.mark.asyncio


async def test_chaos_endpoints():
    headers = {"X-API-Key": "dev-secret-api-key"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Unready injection
        res = await client.post("/admin/chaos/unready", headers=headers)
        assert res.status_code == 200
        assert chaos_state.unready is True

        ready_res = await client.get("/readyz")
        assert ready_res.status_code == 503

        # 2. Latency injection
        res = await client.post("/admin/chaos/latency?ms=50", headers=headers)
        assert res.status_code == 200
        assert chaos_state.latency_ms == 50

        # 3. Memory injection
        res = await client.post("/admin/chaos/memory?mb=5", headers=headers)
        assert res.status_code == 200
        assert len(chaos_state.memory_buffers) >= 1

        # 4. Error rate injection
        res = await client.post("/admin/chaos/errors?percent=50", headers=headers)
        assert res.status_code == 200
        assert chaos_state.error_percent == 50

        # 5. Reset chaos
        res = await client.delete("/admin/chaos", headers=headers)
        assert res.status_code == 200
        assert chaos_state.unready is False
        assert chaos_state.latency_ms == 0
        assert chaos_state.error_percent == 0
        assert len(chaos_state.memory_buffers) == 0
