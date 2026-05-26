# ── Stage 1: dependency installer ────────────────────────────────────────────
# Uses the official uv image so we get the exact same resolver as local dev.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# Cache-mount speeds up repeated builds; LINK_MODE=copy keeps the venv portable
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependency files first — only re-runs uv sync when these change
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Stage 2: lean runtime image ───────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

# Security: run as a non-root user
RUN useradd --create-home appuser

WORKDIR /app

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /app/.venv ./.venv

# Copy application source (no tests, no dev tooling)
COPY app/       ./app/
COPY ai_pipeline/ ./ai_pipeline/
COPY alembic/   ./alembic/
COPY alembic.ini ./

# Put the venv on PATH so `uvicorn` resolves correctly
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
