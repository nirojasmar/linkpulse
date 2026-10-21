# Linkpulse

A URL shortener with click analytics, built as a practice target for Kubernetes troubleshooting.

## Features

- **FastAPI** backend with async PostgreSQL (SQLAlchemy 2.0 + Alembic) and Redis cache.
- **Click analytics stream** powered by Redis Streams and background worker.
- **HTMX dashboard** with live 5s auto-refresh, displaying pod identity, app version, and git SHA.
- **Comprehensive observability**: Prometheus `/metrics`, JSON structured logging, `/healthz`, `/readyz`, `/startupz`.
- **Built-in fault injection** (Chaos endpoints under `/admin/chaos/*`) to test and practice Kubernetes failure scenarios (OOMKilled, CPU throttling/HPA, liveness restarts, readiness probe failures, etc.).

## Quick Start (Docker Compose)

Start the entire stack (PostgreSQL, Redis, Alembic migration, API, and Worker) with one command:

```bash
docker compose up --build
```

Access the services:
- **Dashboard**: [http://localhost:8000](http://localhost:8000)
- **API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus Metrics**: [http://localhost:8000/metrics](http://localhost:8000/metrics)

## API Endpoints

### Public Endpoints
- `GET /` — HTML dashboard showing 20 most recent links and total clicks (HTMX auto-refresh every 5s).
- `GET /dashboard/{code}` — Detailed stats page for a short link.
- `GET /{code}` — HTTP 302 redirect to the target URL.
- `GET /healthz` — Liveness probe (`200 OK`).
- `GET /readyz` — Readiness probe (`200 OK` if DB and Redis are reachable, `503` if any fails).
- `GET /startupz` — Startup probe (`200 OK` after boot sequence finishes).
- `GET /version` — Version, Git SHA, and Pod name metadata.
- `GET /metrics` — Prometheus metrics.

### Link Management (Requires `X-API-Key: dev-secret-api-key`)
- `POST /api/v1/links` — Create a short link (`{"url": "...", "custom_code": "optional"}`).
- `GET /api/v1/links` — List links (supports `?limit=20&offset=0`).
- `GET /api/v1/links/{code}` — Get link details.
- `DELETE /api/v1/links/{code}` — Soft-delete link and evict from cache.
- `GET /api/v1/links/{code}/stats` — Get link analytics (total clicks, 7-day breakdown, top referrers).

### Chaos Endpoints (Requires `CHAOS_ENABLED=true` and `X-API-Key`)
- `POST /admin/chaos/latency?ms=500` — Adds latency to all requests.
- `POST /admin/chaos/errors?percent=30` — Returns HTTP 500 on N% of requests.
- `POST /admin/chaos/memory?mb=200` — Allocates and holds memory (simulates leaks/OOMKilled).
- `POST /admin/chaos/cpu?seconds=60` — Spawns CPU burning thread (tests HPA / throttling).
- `POST /admin/chaos/unready` — Causes `/readyz` to return 503 until reset.
- `POST /admin/chaos/hang` — Stops answering `/healthz` (triggers liveness restart).
- `POST /admin/chaos/crash?code=1` — Exits the container process immediately.
- `DELETE /admin/chaos` — Resets all chaos faults.

## Testing & CI

```bash
# Run tests inside container or locally:
pytest -v tests/
```
