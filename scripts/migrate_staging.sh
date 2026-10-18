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
#   --check     read-only preflight: report recorded vs pending
#               files and run the schema counts. Issues NO writes:
#               no DDL, no DML, and it never creates the migration
#               ledger. A missing ledger is reported, not created.
#               Pending files are informational and do NOT change
#               the exit status (exit 0 still means "the schema
#               verified", not "everything is applied").
#   --baseline  for adopting a database that already carries the
#               schema (applied by other means): verify the full
#               expected schema first, and only then record every
#               file as applied. Refuses when anything is missing.
#               This is a WRITE mode: it creates and populates the
#               ledger.
#
# Exit codes:
#   0  schema verified (pending files may still be listed)
#   1  schema verification failed (owner columns / owner RLS
#      policies are not 8/8)
#   2  usage or environment problem: unknown flag, extra argument,
#      empty argument, DATABASE_URL unset, or psql not installed.
#      Nothing was contacted.
#   3  --check only: the migration ledger public.schema_migrations
#      does not exist. It is never created to satisfy the check.
#   4  --check only: psql or query failure. No verdict was reached.
#
# What --check does NOT verify (unchanged by the read-only fix):
# FILES below is a hardcoded list, so a new 007_*.sql is invisible
# to every mode until this line is edited. verify_schema is a total
# count of 8 owner columns and 8 owner RLS policies; it does not
# check which tables they belong to, and it says nothing about any
# other table, index, constraint, trigger or grant. A passing
# --check is not a schema attestation.
#
# Migrations 003-006 are guarded (IF NOT EXISTS / DROP IF EXISTS).
# 001_initial_schema.sql is NOT: it has five bare CREATE TABLE
# statements, so a lost ledger row makes a re-apply fail rather
# than succeed. Migrations are forward-only: there is no rollback
# SQL by design, and no *_rollback.sql file exists in this repo.
#
# Run BEFORE the first staging deploy and again whenever a new
# migration file lands. Never on container boot (the application
# must not mutate schema as a side effect of starting).
set -euo pipefail

usage() {
  echo "usage: migrate_staging.sh [--check|--baseline]" >&2
}

# No argument means apply. An empty argument is a usage error, not
# apply: "${1:-apply}" treats "" as unset, so an unquoted empty
# expansion would otherwise apply every migration. More than one
# argument is a usage error, never a silent mode choice.
if [ "$#" -gt 1 ]; then
  usage
  exit 2
fi
if [ "$#" -eq 1 ] && [ -z "$1" ]; then
  usage
  exit 2
fi
case "${1:-apply}" in
  apply|--check|--baseline) MODE="${1:-apply}" ;;
  *) usage; exit 2 ;;
esac
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

# --check is read-only. It must never create the ledger, so the DDL
# below runs only for the write modes (apply, --baseline), which both
# depend on the ledger existing. Under --check we fall through and
# probe for the ledger below instead.
if [ "$MODE" != "--check" ]; then
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c \
    "CREATE TABLE IF NOT EXISTS public.schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())"
fi

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
  # Read-only from here down. Ledger presence is probed with a catalog
  # read, never created. to_regclass returns NULL (not an error) when
  # the relation is absent, so a missing ledger is distinguishable
  # from a broken connection.
  ledger_probe=$(psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -tAc \
    "SELECT to_regclass('public.schema_migrations')") || {
    echo "psql could not be queried; no verdict was reached." >&2
    exit 4
  }
  if [ -z "$ledger_probe" ]; then
    echo "migration ledger public.schema_migrations is absent." >&2
    echo "This database has not been migrated or baselined by this" >&2
    echo "script. --check will not create it. Use --baseline to adopt" >&2
    echo "an existing schema, or run with no flag to apply." >&2
    exit 3
  fi

  echo "recorded migrations:"
  recorded_out=$(recorded) || {
    echo "could not read the migration ledger; no verdict was reached." >&2
    exit 4
  }
  printf '%s\n' "$recorded_out"

  echo "pending files:"
  # Both inputs come from shell variables; no process substitution and
  # no `|| true`, so a failed read cannot be silently reported as an
  # empty pending list.
  comm -23 <(printf '%s\n' "$FILES" | tr ' ' '\n' | sort) \
    <(printf '%s\n' "$recorded_out" | sort) || true

  if verify_schema; then
    echo "schema verification: OK"
    exit 0
  fi
  echo "schema verification: FAILED" >&2
  exit 1
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
