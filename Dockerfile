# ==============================================================================
# CHIKITSASETU - Multi-Stage Container Architecture
# Base Image: Python 3.11 Slim
# Targets: api (FastAPI REST & ML), web (Flask Web Portal & Dashboards)
# ==============================================================================

FROM python:3.11-slim AS base

WORKDIR /app

# Set Python runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime tools and build dependencies for compiled wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    libpq-dev \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && apt-get purge -y --auto-remove gcc build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy application source code and models
COPY . .

# Set execution permissions on entrypoint script
RUN chmod +x /app/docker-entrypoint.sh

# -----------------------------------------------------------------------------
# Target: FastAPI REST API & Clinical Machine Learning Service
# -----------------------------------------------------------------------------
FROM base AS api

EXPOSE 8000
ENV FASTAPI_PORT=8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["api"]

# -----------------------------------------------------------------------------
# Target: Flask Hospital Presentation Portal & Operational Dashboards
# -----------------------------------------------------------------------------
FROM base AS web

EXPOSE 5000
ENV FLASK_PORT=5000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD curl -f http://localhost:5000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["web"]
