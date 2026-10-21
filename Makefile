.PHONY: help dev down test lint format build clean

help:
	@echo "Available commands:"
	@echo "  make dev      - Start full stack in Docker Compose"
	@echo "  make down     - Stop Docker Compose services"
	@echo "  make test     - Run test suite"
	@echo "  make lint     - Run ruff linter and format check"
	@echo "  make format   - Format code with ruff"
	@echo "  make build    - Build Docker image"
	@echo "  make clean    - Remove build artifacts and temporary files"

dev:
	docker compose up --build

down:
	docker compose down -v

test:
	docker compose exec api pytest -v tests/ || pytest -v tests/

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

build:
	docker build -t linkpulse:latest .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
