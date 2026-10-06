# LabelLens backend — staging image (Stage 18.5).
#
# Build from the repository root so `snapshots/` ships alongside
# `backend/` (the snapshot adapter resolves it relative to the
# repo layout, unchanged from development):
#
#   docker build -f backend/Dockerfile -t labellens-api:staging .
#
# Production dependencies only: the image installs the project
# WITHOUT the `[test]` extra, so pytest/pytest-asyncio are absent.
# Dependency versions resolve fresh at build time; a generated
# constraints file for byte-reproducible builds is follow-up work
# (see STAGE_18_5_DEPLOYMENT.md).

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# System deps kept to the minimum (TLS for Supabase/JWKS/OCR).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dependencies and code install in one layer: the wheel build
# needs the app sources present (setuptools finds `app*`), so
# caching granularity is traded for a correct single install.
# Production dependencies only (no `[test]` extra).
COPY backend/pyproject.toml /srv/backend/pyproject.toml
COPY backend/app /srv/backend/app
COPY backend/migrations /srv/backend/migrations
COPY snapshots /srv/snapshots
RUN pip install --upgrade pip \
    && pip install /srv/backend

# Never run as root inside the container.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /srv
USER appuser

WORKDIR /srv/backend

# Cloud Run injects PORT; default 8080 matches its convention.
# Single worker: the rate limiter is process-local by design, and
# staging runs max 1 instance, so one worker keeps budgets exact.
CMD ["sh", "-c", "uvicorn app.serve:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
