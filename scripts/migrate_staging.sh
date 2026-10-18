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
#               Each file is applied ATOMICALLY: the migration SQL
#               and its schema_migrations row are submitted as one
#               psql script under --single-transaction, so a file is
#               either fully applied and recorded, or neither. The
#               first failure stops the run (non-zero exit); nothing
#               is recorded for a failed file, and no later file is
#               attempted.
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
# Atomic apply removes the *mechanism* by which a lost ledger row
# could strand a partially applied database; it does not make 001
# re-runnable in isolation.
#
# HOW APPLY STAYS ATOMIC (apply and --baseline)
#
# For each file the script generates a psql script in a private
# temporary directory (mktemp -d, mode 0700, outside this repository)
# and runs it with:
#
#   psql "$DATABASE_URL" -X -1 -q -t -A -v ON_ERROR_STOP=1 -f <step>
#
# -1/--single-transaction wraps the whole file in ONE transaction,
# and \i is processed inside that transaction, so the migration and
# its ledger INSERT commit together or not at all. ON_ERROR_STOP=1
# is mandatory here: without it psql would COMMIT a partially
# applied migration.
#
# Inside that transaction, in order:
#   1. SET TRANSACTION ISOLATION LEVEL READ COMMITTED -- so the
#      check in step 3 reads a fresh snapshot even if the server
#      default isolation level was raised.
#   2. SELECT pg_advisory_xact_lock(<key>) -- serializes runners.
#      The lock is transaction-scoped, so PostgreSQL releases it on
#      COMMIT and on ROLLBACK. It is taken BEFORE the recorded-state
#      check and held through the ledger INSERT.
#   3. re-read the ledger for THIS file, inside the transaction.
#   4. \i the migration file, only if still pending.
#   5. INSERT INTO public.schema_migrations (filename) VALUES (<file>)
#
# The recorded-state check is deliberately NOT done in the shell.
# A shell-side check is a separate session, taken before the lock,
# and cannot see a concurrent runner's commit. Here the check is the
# only one, and it runs under the lock in the same transaction as
# the work it gates.
#
# IF A COMMIT REPLY IS LOST: if the connection drops during COMMIT,
# psql exits non-zero whether or not the server committed. The
# script cannot tell, so on any per-file failure it re-reads the
# ledger in a fresh session and reports which of the two happened.
# The exit status stays non-zero either way: a retry is always safe,
# because the retry re-reads the ledger under the lock and skips a
# file that really did commit.
#
# psql is invoked with -X (--no-psqlrc) on EVERY call. A COMMIT in
# ~/.psqlrc would silently void --single-transaction, and a stray
# write there would make --check write. The generated script uses
# \if and \gset, which need psql 10 (2017) or newer.
#
# WHAT THE OFFLINE TESTS DO NOT PROVE: scripts/test_migrate_staging*.py
# run a fake psql. They prove the control flow, the transaction
# options on each invocation, and the exact SQL submitted. They do
# NOT prove that PostgreSQL rolls back, that the advisory lock
# serializes across processes, or that a lost COMMIT resolves as
# described above. Those were verified by hand against a disposable
# local PostgreSQL 18.6, not against staging.
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

# Serialization key for the write modes. This MUST be a fixed literal:
# a key derived from the clock, the PID or any other per-run value
# would let two runners take two different locks and turn the lock
# into a no-op, which is exactly the race it exists to prevent.
ADVISORY_LOCK_KEY=7081702300000000001

# How long a runner waits for that lock before giving up. The lock is
# released when its transaction ends, so this only bites when another
# runner is mid-migration, or when a killed runner's backend has not
# yet noticed the dead client. Failing with a message beats blocking
# with no output.
MIGRATION_LOCK_TIMEOUT=60s

# --check is read-only. It must never create the ledger, so the DDL
# below runs only for the write modes (apply, --baseline), which both
# depend on the ledger existing. Under --check we fall through and
# probe for the ledger below instead. The advisory lock is taken in
# the same statement because CREATE TABLE IF NOT EXISTS is not itself
# race-free: two sessions creating the same relation concurrently can
# collide on the pg_class unique index.
if [ "$MODE" != "--check" ]; then
  psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -q -t -A -c \
    "SELECT pg_advisory_xact_lock($ADVISORY_LOCK_KEY); CREATE TABLE IF NOT EXISTS public.schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())"
fi

# Write the per-file psql script used by apply. $1 is the destination
# path, $2 the migration filename. See the "HOW APPLY STAYS ATOMIC"
# block at the top of this file for why each statement is here.
#
# The two CASE arms are deliberate. `\if` treats a value it cannot
# parse as FALSE and only warns, so a single probe variable would turn
# a broken probe into a silently skipped migration that still COMMITs.
# With two complementary variables, anything other than a clean
# 'yes'/'no' falls through both branches into the final SELECT, which
# is a real SQL error: ON_ERROR_STOP then aborts and --single-transaction
# rolls back, so the run fails closed instead.
#
# `\i` is not quoted and the migration path does not appear here at
# all: neither \i nor \cd strips quotes or tolerates spaces. psql is
# instead run with $MIGRATIONS as its working directory, so this can
# reference the file by its bare name.
write_step_script() {
  cat > "$1" <<SQL
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout = '$MIGRATION_LOCK_TIMEOUT';
SELECT pg_advisory_xact_lock($ADVISORY_LOCK_KEY);
SET LOCAL lock_timeout = 0;
SELECT CASE WHEN EXISTS (SELECT 1 FROM public.schema_migrations WHERE filename = '$2')
            THEN 'yes' ELSE 'no' END AS recorded,
       CASE WHEN EXISTS (SELECT 1 FROM public.schema_migrations WHERE filename = '$2')
            THEN 'no' ELSE 'yes' END AS pending \\gset
\\if :pending
\\echo labellens: applying $2
\\i $2
INSERT INTO public.schema_migrations (filename) VALUES ('$2');
\\elif :recorded
\\echo labellens: skip $2 (already recorded)
\\else
SELECT 'labellens: the recorded-state probe for $2 was unusable; refusing to apply it' AS fatal, 1/0;
\\endif
SQL
}

recorded() {
  psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -tAc \
    "SELECT filename FROM public.schema_migrations"
}

verify_schema() {
  local owners policies
  owners=$(psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -tAc "
SELECT count(*) FROM information_schema.columns
WHERE table_name IN (
  'ocr_runs', 'ocr_corrections', 'ingredient_observations',
  'ingredient_normalizations', 'ingredient_candidates',
  'entity_matches', 'verification_decisions', 'reviews')
  AND column_name = 'owner_subject';")
  policies=$(psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -tAc "
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
  ledger_probe=$(psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -tAc \
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

# Everything below is a WRITE mode. Both of them interpolate FILES
# into generated SQL, so the filenames are checked rather than
# trusted. FILES is a hardcoded list today; if it ever becomes a glob
# or a directory listing, an unexpected name is refused here instead
# of being pasted into SQL or into a \i line.
for file in $FILES; do
  case "$file" in
    [0-9][0-9][0-9]_[A-Za-z0-9_]*\.sql) ;;
    *) echo "refusing to migrate an unexpected filename: $file" >&2
       exit 2 ;;
  esac
done

# Scratch directory for the generated psql scripts. mktemp -d is mode
# 0700 and unaffected by umask. Cleanup removes the two explicit files
# this script creates and then the directory itself; it never uses
# `rm -rf`, because the parent of a mktemp path is $TMPDIR, and
# recursively deleting a path derived from mktemp's output destroys
# unrelated files. The directory is also required to be outside the
# repository so a generated script can never be committed by accident.
STEPS_DIR="$(mktemp -d)"
cleanup_steps() {
  rm -f -- "$STEPS_DIR/baseline.sql" "$STEPS_DIR/step.sql"
  rmdir -- "$STEPS_DIR" 2>/dev/null || true
}
trap cleanup_steps EXIT
# On a signal, clean up and then re-raise it, so an interrupt aborts the
# run instead of falling through to the next migration. cleanup_steps is
# idempotent, so running it from both traps is safe.
trap 'cleanup_steps; trap - INT TERM; kill -TERM $$' INT TERM
case "$STEPS_DIR/" in
  "$ROOT"/*)
    echo "refusing to write migration scripts inside the repository." >&2
    exit 2
    ;;
esac

if [ "$MODE" = "--baseline" ]; then
  if ! verify_schema; then
    echo "baseline refused: schema is incomplete; apply normally instead." >&2
    exit 1
  fi
  # All six rows go in one transaction under the same advisory lock,
  # for the same reason apply does: six independent psql sessions left
  # a ledger claiming files 001-003 were applied when nothing had been
  # verified beyond verify_schema. One transaction is all-or-nothing.
  baseline_step="$STEPS_DIR/baseline.sql"
  {
    echo "SET TRANSACTION ISOLATION LEVEL READ COMMITTED;"
    echo "SET LOCAL lock_timeout = '$MIGRATION_LOCK_TIMEOUT';"
    echo "SELECT pg_advisory_xact_lock($ADVISORY_LOCK_KEY);"
    echo "SET LOCAL lock_timeout = 0;"
    for file in $FILES; do
      echo "INSERT INTO public.schema_migrations (filename) VALUES ('$file') ON CONFLICT DO NOTHING;"
    done
  } > "$baseline_step"
  if ! psql "$DATABASE_URL" -X -1 -q -t -A -v ON_ERROR_STOP=1 \
      -f "$baseline_step"; then
    echo "baseline failed: the ledger was not modified at all." >&2
    exit 1
  fi
  rm -f -- "$baseline_step"
  for file in $FILES; do
    echo "baselined $file"
  done
  exit 0
fi

for file in $FILES; do
  step="$STEPS_DIR/step.sql"
  write_step_script "$step" "$file"
  # psql runs with $MIGRATIONS as its working directory so that the
  # generated script can \i the file by bare name. Run in a subshell
  # so the script's own working directory is unchanged.
  if ( cd "$MIGRATIONS" && psql "$DATABASE_URL" -X -1 -q -t -A \
         -v ON_ERROR_STOP=1 -f "$step" ); then
    rm -f -- "$step"
    continue
  fi
  rm -f -- "$step"
  # psql's exit status cannot tell us whether the server committed: if
  # the connection dropped during COMMIT, the client sees a failure
  # and the migration may still have landed. The ledger can, because
  # the migration and its row share one transaction. This read is
  # reporting only; the decision on the next run is made under the
  # lock by the check inside the step script.
  if recorded | grep -qx "$file"; then
    echo "$file: this run failed, but the ledger records it as applied." >&2
    echo "The commit outcome was ambiguous (the connection may have" >&2
    echo "dropped during COMMIT). Nothing later was attempted. Re-run" >&2
    echo "this script: it re-reads the ledger under the lock and will" >&2
    echo "skip this file if it really did commit." >&2
  else
    echo "$file: not applied and NOT recorded. Its database changes were" >&2
    echo "rolled back, or never made. Nothing later was attempted;" >&2
    echo "fix the migration and re-run." >&2
  fi
  exit 1
done

verify_schema && echo "migrations applied and verified."
