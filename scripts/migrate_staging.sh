#!/usr/bin/env bash
# LabelLens staging migrations (Stage 18.5).
#
# Usage:
#   DATABASE_URL='<service-role-or-owner-url>?ssl=require' \
#     ./scripts/migrate_staging.sh [--check|--baseline]
#
# Applies backend/migrations/00{1..6}_*.sql in deterministic
# filename order, recording each file in
# public.schema_migrations. Behavior:
#
#   no flag     apply every unrecorded migration, then verify.
#               The first failure stops the run (non-zero exit);
#               nothing is recorded for a failed file, and no
#               later file is attempted.
#   --check     verify-only: report recorded vs pending files and
#               run the schema checks. Changes nothing.
#   --baseline  for adopting a database that already carries the
#               schema (applied by other means): verify the full
#               expected schema first, and only then record every
#               file as applied. Refuses when anything is missing.
#
# Every file is written idempotently (IF NOT EXISTS / DROP-IF-EXISTS
# guards), and re-running this script after success is a no-op that
# still runs the verification queries. Migrations are forward-only:
# there is no destructive rollback SQL by design.
#
# Run BEFORE the first staging deploy and again whenever a new
# migration file lands. Never on container boot (the application
# must not mutate schema as a side effect of starting).
set -euo pipefail

MODE="${1:-apply}"
if [ "$MODE" != "apply" ] && [ "$MODE" != "--check" ] && \
   [ "$MODE" != "--baseline" ]; then
  echo "usage: migrate_staging.sh [--check|--baseline]" >&2
  exit 2
fi
if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required (never committed; pass it in the environment)." >&2
  exit 2
fi
command -v psql >/dev/null || {
  echo "psql is required but not installed." >&2
  exit 2
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATIONS="$ROOT/backend/migrations"
FILES="001_initial_schema.sql 002_seed_data.sql 003_verification_review.sql 004_ocr_boundary.sql 005_ocr_ownership.sql 006_analysis_ownership.sql"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c \
  "CREATE TABLE IF NOT EXISTS public.schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())"

recorded() {
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc \
    "SELECT filename FROM public.schema_migrations"
}

verify_schema() {
  local owners policies
  owners=$(psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc "
SELECT count(*) FROM information_schema.columns
WHERE table_name IN (
  'ocr_runs', 'ocr_corrections', 'ingredient_observations',
  'ingredient_normalizations', 'ingredient_candidates',
  'entity_matches', 'verification_decisions', 'reviews')
  AND column_name = 'owner_subject';")
  policies=$(psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc "
SELECT count(*) FROM pg_policies
WHERE tablename IN (
  'ocr_runs', 'ocr_corrections', 'ingredient_observations',
  'ingredient_normalizations', 'ingredient_candidates',
  'entity_matches', 'verification_decisions', 'reviews');")
  echo "owner columns: $owners (expect 8); owner RLS policies: $policies (expect 8)"
  [ "$owners" = "8" ] && [ "$policies" = "8" ]
}

if [ "$MODE" = "--check" ]; then
  echo "recorded migrations:"
  recorded
  echo "pending files:"
  comm -23 <(echo "$FILES" | tr ' ' '\n' | sort) \
    <(recorded | sort) || true
  verify_schema && echo "schema verification: OK"
  exit 0
fi

if [ "$MODE" = "--baseline" ]; then
  if ! verify_schema; then
    echo "baseline refused: schema is incomplete; apply normally instead." >&2
    exit 1
  fi
  for file in $FILES; do
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c \
      "INSERT INTO public.schema_migrations (filename) VALUES ('$file') ON CONFLICT DO NOTHING"
    echo "baselined $file"
  done
  exit 0
fi

for file in $FILES; do
  if recorded | grep -qx "$file"; then
    echo "skip $file (already applied)"
    continue
  fi
  echo "applying $file"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
    --single-transaction -f "$MIGRATIONS/$file"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c \
    "INSERT INTO public.schema_migrations (filename) VALUES ('$file')"
done

verify_schema && echo "migrations applied and verified."
