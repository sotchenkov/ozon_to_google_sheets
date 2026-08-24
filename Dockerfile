# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.14.7-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.14.7-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --home-dir /app app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

USER app

ENTRYPOINT ["ozon-to-google-sheets"]
