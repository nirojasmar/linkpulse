from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

# HTTP metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests received",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0),
)

# Redirect metrics
REDIRECTS_TOTAL = Counter(
    "redirects_total",
    "Total redirects served by result",
    ["result"],  # "hit", "miss", "not_found"
)

# Event publishing metrics
CLICK_EVENTS_PUBLISHED_TOTAL = Counter(
    "click_events_published_total",
    "Total click events published to Redis stream",
)

CLICK_EVENTS_PUBLISH_ERRORS_TOTAL = Counter(
    "click_events_publish_errors_total",
    "Total errors encountered while publishing click events",
)

# Worker metrics
WORKER_EVENTS_PROCESSED_TOTAL = Counter(
    "worker_events_processed_total",
    "Total click events processed by worker",
)

WORKER_BATCH_DURATION_SECONDS = Histogram(
    "worker_batch_duration_seconds",
    "Duration of worker batch processing in seconds",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

WORKER_STREAM_PENDING = Gauge(
    "worker_stream_pending",
    "Number of pending unacknowledged events in worker consumer group",
)

# Database query duration
DB_QUERY_DURATION_SECONDS = Histogram(
    "db_query_duration_seconds",
    "Duration of database queries in seconds",
    ["query_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


def metrics_response() -> Response:
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
