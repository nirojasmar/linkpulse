#!/bin/sh
set -e

COMMAND="${1:-api}"

case "$COMMAND" in
    api)
        echo "Starting Linkpulse API..."
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 20
        ;;
    worker)
        echo "Starting Linkpulse Worker..."
        exec python -m app.worker
        ;;
    migrate)
        echo "Running Database Migrations..."
        exec alembic upgrade head
        ;;
    *)
        exec "$@"
        ;;
esac
