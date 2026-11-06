# Dictaphone audio extractor Image

# ---- base image to inherit from ----
FROM python:3.14.8-alpine3.24 AS base

# Upgrade pip to its latest release to speed up dependencies installation
RUN python -m pip install --upgrade pip

# Upgrade system packages to install security updates
RUN apk update && \
  apk upgrade

# Install audio processing tools
RUN apk --no-cache add \
  coreutils \
  opus-tools

# Pull latest fmpeg from alpine edge
RUN apk add --no-cache \
    --repository=https://dl-cdn.alpinelinux.org/alpine/edge/main \
    --repository=https://dl-cdn.alpinelinux.org/alpine/edge/community \
    'ffmpeg=9.0.2-r1'

# ---- Minimal filesystem exposed to media parsers ----
FROM base AS media-rootfs

COPY src/audio-extractor/build-media-rootfs.py /tmp/build-media-rootfs.py
RUN python /tmp/build-media-rootfs.py /opt/media-rootfs

# ---- Pinned gVisor runtime, including its required companion binaries ----
FROM base AS gvisor-download

ARG TARGETARCH
ARG GVISOR_VERSION=20261102.0
COPY src/audio-extractor/gvisor-SHA512SUMS /tmp/gvisor-SHA512SUMS
RUN apk add --no-cache curl && \
  case "${TARGETARCH:-$(uname -m)}" in \
    amd64|x86_64) arch=x86_64 ;; \
    arm64|aarch64) arch=aarch64 ;; \
    *) exit 1 ;; \
  esac && \
  cd /tmp && \
  curl -fsSL "https://storage.googleapis.com/gvisor/releases/release/${GVISOR_VERSION}/${arch}/gvisor.tar.bz2" -o "gvisor-${arch}.tar.bz2" && \
  awk -v file="gvisor-${arch}.tar.bz2" '$2 == file' gvisor-SHA512SUMS | sha512sum -c - && \
  mkdir /gvisor && \
  tar -xjf "gvisor-${arch}.tar.bz2" -C /gvisor

FROM base AS worker-base

COPY --from=media-rootfs /opt/media-rootfs /opt/media-rootfs
COPY --from=gvisor-download /gvisor/runsc /usr/local/bin/runsc
COPY --from=gvisor-download /gvisor/gvisor-bin /usr/local/bin/gvisor-bin

# ---- Back-end builder image ----
FROM worker-base AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/

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
FROM worker-base AS audio-extractor-production

ARG DOCKER_USER=10000:10000

# Create and assign the working directory
RUN mkdir -p /work && \
  chown ${DOCKER_USER} /work

# Copy the application from the builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/audio_extractor /app/audio_extractor
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
COPY src/audio-extractor/run-worker.sh /app/run-worker.sh

# Remove pip to reduce attack surface in production
RUN pip uninstall -y pip

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR=/work

WORKDIR /app

# Run as the un-privileged user
USER ${DOCKER_USER}

VOLUME ["/work"]

# Recycle after 15 minutes, with an independent 20-minute shutdown watchdog.
CMD ["sh", "/app/run-worker.sh"]
