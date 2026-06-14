# Railway API service — builds the FastAPI backend from the uv workspace root.
# Context is the repo root so all workspace members under packages/ are available.
FROM python:3.12-slim

WORKDIR /app

# git is required at runtime: GitPython initializes on import and the
# ingestion/workspace services clone target repositories.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy the whole workspace and sync all members into /app/.venv.
COPY . .
RUN uv sync --frozen

# Run from the API package; uv resolves the workspace venv at /app/.venv.
WORKDIR /app/apps/api

# Apply migrations, then start. PORT is injected by Railway.
CMD uv run alembic upgrade head && \
    uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}