FROM python:3.13-slim-bookworm

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md war.csv config.example.json ./
COPY dynasty_draft ./dynasty_draft
COPY scripts/start.sh ./scripts/start.sh

RUN chmod +x ./scripts/start.sh && uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1

CMD ["./scripts/start.sh"]
