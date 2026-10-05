# LabelLens — Stage-10 Persistence + Supabase Boundary

**Date:** 2026-10-05  
**Branch:** `feat/label-pipeline-foundation`  
**Scope:** persistence boundary only. V1–V7 untouched (`gate.py` has
zero Stage-10 diffs). No endpoints, frontend, RDKit, chemistry, AI.

## Schema decisions

Migration `003_verification_review.sql` (additive; history preserved)
creates 10 tables: the six spec-defined tables missing so far
(`ingredient_observations`, `ingredient_normalizations`,
`ingredient_candidates`, `entity_matches`, `claims`, `claim_sources`,
`verification_events` — seven incl. the event table) plus the three
gate-specified records the schema did not define
(`verification_decisions`, `reviews`, `review_events`).

Deliberate, documented extensions to spec tables:

- `claims`: nullable `source_version`, `freshness_class`,
  `last_checked_at` (freshness required by the evidence
  architecture; first/last-verified derive from
  `verification_events` history, not new columns).
- `claim_sources`: nullable `provider`, `source_version`,
  `retrieved_at`, `response_hash` (evidence provenance per §8).
- `entity_matches`: no new columns -- Stage-5 alternatives live as
  `ingredient_candidates` rows, exactly per spec.
- Deferred FKs stored as plain UUIDs with migration-header comments
  (`claims.product_id/product_label_id/entity_role_id`,
  `observations.scan_id/ocr_run_id`): their target tables land in a
  later phase; constraints activate then.
- `sources.name` gained a UNIQUE constraint (needed for idempotent
  `ensure_source`); the table was previously unconstrained.

Status vocabularies are CHECK-constrained to the evidence-spec and
gate-spec sets. Query-critical columns carry indexes (§25 of the
brief); nothing else is indexed.

## Pre-existing 002 defect (repaired)

`002_seed_data.sql` used non-hex UUID literals (`g…`, `h…`, `i…`) so
its source INSERT could never parse -- sources stayed at zero rows
everywhere it ran. The literals were corrected in place to valid hex
(the statement never successfully applied, so no applied state is
rewritten) and `003` re-seeds idempotently (`WHERE NOT EXISTS`).

## Repository boundary

Services depend on Protocols (`repositories/protocols.py`); two
implementations exist: `memory.py` (contract reference, offline
development, future service-test fakes) and `postgres.py`
(SQLAlchemy Core, parameter-bound, `ON CONFLICT DO NOTHING`
idempotency). `db.py` centralizes engine creation (URL from
environment only) and the `atomic` transaction scope. Serialization
lives in `serialize.py` with deterministic uuid5 IDs and a
`validate_no_secrets` gate on stored payloads.

## Migrations

`001` (Phase-1 tables), `002` (seeds, repaired literals),
`003_verification_review.sql` (Stage-10 tables + seed repair + RLS +
triggers). All three apply cleanly and re-apply idempotently
(verified live, twice in a row). No rollback files (repo convention:
none exist); no destructive statements anywhere.

## RLS

Enabled on all 10 new tables. `anon`/`authenticated` writes revoked;
authenticated may SELECT the six audit tables; event tables additionally
reject UPDATE/DELETE via trigger. Service role bypasses by design and
stays backend-only. Role-dependent statements are conditional on the
roles existing (Supabase provides them; bare Postgres skips policies
with a NOTICE). Per-user row policies are impossible yet (no user_id
on these tables) -- that lands with the auth stage. **Not claimed
production-ready**: RLS behavior itself was validated live (deny/allow
matrix in integration tests), but production roles/policies still need
a Supabase-project review.

## Append-only enforcement

Database triggers on `review_events` and `verification_events`
reject UPDATE/DELETE; repository classes expose no mutators for event
tables (append + read only), tested live. History rows are never
updated: corrections are new rows/events.

## Transaction strategy

Multi-write transitions (`submit_review` + created event, claim
status + verification event, conditional `transition_review` + event)
execute in one connection scope: `atomic()` for Postgres,
snapshot-rollback for memory. A failing batch leaves no partial
state (tested on both implementations).

## Concurrency

Claim uses conditional `UPDATE..WHERE status=expected RETURNING`:
zero rows means lost race (`ReviewClaimConflict`) or missing row
(`KeyError`), distinguished explicitly. Postgres path validated live;
memory path mirrors the semantics deterministically.

## Idempotency

Deterministic IDs everywhere (uuid5 over stable inputs; domain-native
`REV-####`/`REV-####:###` for reviews/events) plus `ON CONFLICT DO
NOTHING` (Postgres) / PK-dedupe (memory). Retried submissions,
decisions, links, and events store exactly once (tested).

## Testing limitations

Contract suite runs offline against memory. Live suite
(`tests/integration/test_postgres.py`, skipped without
`TEST_DATABASE_URL`) validated against real Postgres 18: migration
application, seed repair, RLS deny/allow matrix, trigger blocks,
CHECK/FK violations, idempotent resubmission, claim races, atomic
rollback, full-chain round-trip. RLS was tested with locally created
`anon`/`authenticated` roles -- Supabase-project policy review is
still required before production claims.

## Security model

Writes default to the service role in every repository method;
`authenticated` reads audit data; `anon` gets nothing (all enforced
in code AND in RLS). `validate_no_secrets` refuses credential-like
keys/values pre-write; hostile strings (SQL-injection payloads,
reviewer names) round-trip as inert data (parameter binding only --
no SQL string construction anywhere). No credentials exist in code,
snapshots, tests, or `.env.example` (placeholders only).
