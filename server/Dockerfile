FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install runtime deps from the lockfile into /app/.venv (no dev group, no project itself).
# The venv lives outside /app/server so the compose bind-mount of ./server can't clobber it.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

WORKDIR /app/server
COPY server/ ./
# Eval fixtures next to server/ (same repo-root layout as the host), so worker eval runs
# can resolve relative dataset paths like eval/calculator/chat_values/example.jsonl.
COPY eval/ /app/eval/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
