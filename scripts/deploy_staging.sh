#!/usr/bin/env bash
# LabelLens staging deploy to Google Cloud Run (Stage 18.5).
#
# Usage:
#   PROJECT_ID=<gcp-project> ./scripts/deploy_staging.sh
#
# Prerequisites (checked below, never fabricated):
#   - gcloud authenticated with permission to deploy
#   - Artifact Registry repository `labellens` in asia-south1
#   - Secret Manager secrets created (see STAGE_18_5_DEPLOYMENT.md):
#       labellens-staging-database-url        (required)
#       labellens-staging-supabase-url        (required)
#       labellens-staging-ocr-space-api-key   (optional; see below)
#   - migrations 001–006 already applied via scripts/migrate_staging.sh
#
# The script never prints secret values. `set -x` is deliberately
# off so expanded secret references cannot leak into CI logs.
#
# Invocation is public (`--allow-unauthenticated`) on purpose:
# Cloud Run IAM stays open so the application's own Supabase JWT
# boundary can be smoke-tested end to end (missing/invalid tokens
# must yield the app's 401s). Every data route still requires a
# valid bearer token; nothing anonymous is served.
set -euo pipefail

SERVICE="${SERVICE_NAME:-labellens-api-staging}"
REGION="${REGION:-asia-south1}"
REPO="${ARTIFACT_REPO:-labellens}"

if [ -z "${PROJECT_ID:-}" ]; then
  echo "PROJECT_ID is required (no default project is assumed)." >&2
  exit 2
fi
command -v gcloud >/dev/null || {
  echo "gcloud CLI is required but not installed." >&2
  exit 2
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/labellens-api-staging:$(git -C "$ROOT" rev-parse --short HEAD)"

echo "building image $IMAGE"
gcloud builds submit \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --tag "$IMAGE" \
  "$ROOT"

SECRETS="DATABASE_URL=labellens-staging-database-url:latest,SUPABASE_URL=labellens-staging-supabase-url:latest"
if [ "${OCR_SECRET_NAME:-labellens-staging-ocr-space-api-key}" != "none" ]; then
  SECRETS="$SECRETS,OCR_SPACE_API_KEY=${OCR_SECRET_NAME:-labellens-staging-ocr-space-api-key}:latest"
fi

EXTRA_ARGS=()
if [ -n "${SERVICE_ACCOUNT:-}" ]; then
  EXTRA_ARGS+=(--service-account "$SERVICE_ACCOUNT")
fi

echo "deploying $SERVICE to $REGION (max 1 instance: process-local limiter)"
gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE" \
  --platform managed \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --cpu 1 \
  --memory 512Mi \
  --timeout 60s \
  --concurrency 20 \
  --set-env-vars "ENVIRONMENT=production,ALLOWED_ORIGINS=,LOG_LEVEL=info" \
  --update-secrets "$SECRETS" \
  "${EXTRA_ARGS[@]}"

echo "deployed. Service URL:"
gcloud run services describe "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format "value(status.url)"
