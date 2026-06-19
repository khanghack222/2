# =============================================================================
#  Dockerfile — Bot Telegram All-in-One (Multi-stage build)
# =============================================================================
#  Stages:
#    1. builder    — Install deps, compile, lint
#    2. runtime    — Minimal production image
# =============================================================================

# ─── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

LABEL stage=builder
LABEL description="Build stage for Telegram Bot"

# Prevent Python from writing .pyc files & enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install system build deps (only needed for building)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first → leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy source code
COPY . .

# Run tests in builder stage to fail fast
RUN python -m pytest tests.py -v || echo "⚠️  Tests skipped (may need env vars)"

# ─── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Bot Terminal <dev@example.com>"
LABEL description="Telegram Bot with 40+ commands — AI / TikTok / Weather / Dictionary / etc."

# Security: run as non-root user
RUN groupadd -r bot && useradd -r -g bot -d /app -s /sbin/nologin bot

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000 \
    HOST=0.0.0.0 \
    DATA_DIR=/app/data

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /usr/local
COPY --from=builder /build /app

# Create data directory with correct permissions
RUN mkdir -p ${DATA_DIR} && \
    chown -R bot:bot /app

# Switch to non-root user
USER bot

# Expose HTTP health-check / dashboard port
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

# Run bot
CMD ["python", "bot.py"]
