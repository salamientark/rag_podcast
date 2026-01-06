FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-install-project --no-dev

COPY src/ ./src/
COPY public_key.pem ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PORT=9000

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % (int(__import__('os').environ.get('PORT', 9000))), timeout=5)" || exit 1

CMD ["sh", "-c", "python -m src.mcp.server --host 0.0.0.0 --port ${PORT}"]
