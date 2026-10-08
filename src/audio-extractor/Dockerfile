# Dictaphone audio extractor Image

# ---- base image to inherit from ----
FROM python:3.14.7-alpine3.24 AS base

# Upgrade pip to its latest release to speed up dependencies installation
RUN python -m pip install --upgrade pip

# Upgrade system packages to install security updates
RUN apk update && \
  apk upgrade

# Install audio processing tools
RUN apk --no-cache add \
  coreutils \
  ffmpeg \
  opus-tools

# ---- Back-end builder image ----
FROM base AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/

# Configure uv and Python
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies
COPY src/audio-extractor/pyproject.toml src/audio-extractor/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-install-project --no-dev

# Copy the application from the build context
COPY src/audio-extractor/audio_extractor ./audio_extractor

RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-dev

# ---- Development image ----
FROM builder AS development

ARG DOCKER_USER=10000:10000

RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --all-groups

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER ${DOCKER_USER}

CMD ["pytest"]

# ---- Production image ----
FROM base AS audio-extractor-production

ARG DOCKER_USER=10000:10000

# Create and assign the working directory
RUN mkdir -p /work && \
  chown ${DOCKER_USER} /work

# Copy the application from the builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/audio_extractor /app/audio_extractor
COPY src/audio-extractor/run-worker.sh /app/run-worker.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR=/work

WORKDIR /app

# Run as the un-privileged user
USER ${DOCKER_USER}

VOLUME ["/work"]

# Run one attempt with the same hard deadline as the backend's audio job lease.
CMD ["sh", "/app/run-worker.sh"]
