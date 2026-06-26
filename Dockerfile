FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --no-install-project --frozen

COPY src/ src/
RUN uv sync --no-dev --frozen

FROM python:3.14-slim-bookworm

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY src/ src/

ENV ZEITFENSTER_CONFIG_PATH=/etc/zeitfenster/config.yaml
ENV ZEITFENSTER_SITE_DIR=/site

EXPOSE 8000

CMD ["uvicorn", "zeitfenster.app:app", "--host", "0.0.0.0", "--port", "8000"]
