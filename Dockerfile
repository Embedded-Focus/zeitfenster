FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:a2657d5b8da6a702204e49b2ed2467597da15fb45eb9fee00304c127dad4b1e9 AS builder

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

FROM python:3.14-slim-bookworm@sha256:82bc3c539b8813ada9d68c63b40158fa002f7f33de9bf3312a3dfdc0620dff56

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
