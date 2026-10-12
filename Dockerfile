FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:8e70ac2e85d09a5bb7ef09753b80671a60a71c8d24f195e4890d71e03865e36d AS builder

ARG UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache << EOT
    uv sync --no-dev --no-install-project --frozen
EOT

COPY src/ src/
RUN --mount=type=cache,target=/root/.cache << EOT
    uv sync --no-dev --frozen
EOT

FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83

WORKDIR /app

RUN groupadd --system --gid 10001 zeitfenster \
    && useradd --system --uid 10001 --gid zeitfenster --home-dir /app --shell /usr/sbin/nologin zeitfenster \
    && mkdir -p /site \
    && chown zeitfenster:zeitfenster /site

COPY --from=builder --chown=zeitfenster:zeitfenster /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=zeitfenster:zeitfenster src/ src/

ENV ZEITFENSTER_CONFIG_PATH=/etc/zeitfenster/config.yaml
ENV ZEITFENSTER_SITE_DIR=/site

USER zeitfenster

EXPOSE 8000

CMD ["uvicorn", "zeitfenster.app:app", "--host", "0.0.0.0", "--port", "8000"]
