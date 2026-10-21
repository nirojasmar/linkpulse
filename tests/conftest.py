import os

# Ensure testing environment variables are present before settings are instantiated
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/linkpulse"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("API_KEY", "dev-secret-api-key")
os.environ.setdefault("CHAOS_ENABLED", "true")
os.environ.setdefault("BASE_URL", "http://localhost:8000")
