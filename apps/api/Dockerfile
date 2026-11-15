# API image (api, worker va Telegram boti — B6.2). Kontekst — repozitoriy ildizi (uv workspace).
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY apps/api/pyproject.toml apps/api/
COPY apps/bot/pyproject.toml apps/bot/
RUN uv sync --locked --no-dev --package upbot --no-install-workspace

COPY packages/core packages/core
COPY apps/api apps/api
COPY apps/bot apps/bot
RUN uv sync --locked --no-dev --package upbot

RUN useradd --system --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "upapi.main:app", "--host", "0.0.0.0", "--port", "8000"]
