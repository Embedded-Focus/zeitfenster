FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:637619278855a77885a94312efa7decd8479ca6cec5f959e134cbab96582821e AS builder

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

# Keep the runtime on the same Python minor version as the builder stage: the
# venv is copied across stages, so a 3.15 runtime cannot load packages
# installed for 3.14 (uvicorn was missing at start-up with a 3.15 base).
FROM python:3.14-slim-trixie@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

WORKDIR /app

RUN groupadd --system --gid 10001 zeitfenster \
    && useradd --system --uid 10001 --gid zeitfenster --home-dir /app --shell /usr/sbin/nologin zeitfenster \
    && mkdir -p /site \
    && chown zeitfenster:zeitfenster /site

COPY --from=builder --chown=zeitfenster:zeitfenster /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=zeitfenster:zeitfenster src/ src/
COPY --chown=zeitfenster:zeitfenster docker/entrypoint.sh /entrypoint.sh

# Sanity check: the copied venv must work with this stage's interpreter. Run
# the real entry point, the way the CMD does. A builder/runtime mismatch
# otherwise ships an image that crash-loops at start-up (1.2.4 failed with
# "No module named 'uvicorn'").
RUN uvicorn --version && python -c "import zeitfenster.app"

ENV ZEITFENSTER_CONFIG_PATH=/etc/zeitfenster/config.yaml
ENV ZEITFENSTER_SITE_DIR=/site

USER zeitfenster

EXPOSE 8000

# Back off before exiting on failure; podman kube play restarts failed
# containers immediately and would spin the CPU on a crash loop.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "zeitfenster.app:app", "--host", "0.0.0.0", "--port", "8000"]
