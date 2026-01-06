FROM python:3.13-slim as builder

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-install-project --no-dev

FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

COPY src/ ./src/
COPY pyproject.toml ./
COPY public_key.pem ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PORT=9000

EXPOSE 9000

CMD ["sh", "-c", "python -m src.mcp.server --host 0.0.0.0 --port ${PORT}"]
