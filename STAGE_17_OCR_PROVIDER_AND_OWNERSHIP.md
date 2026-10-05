# Stage 17 — OCR Ownership and First Real Provider

Date: 2026-10-05
Scope: exactly two areas — (A) per-user ownership/data isolation
for OCR runs and OCR-derived records, (B) one real OCR provider
adapter (OCR.space) behind the existing protocol.

Verification rules V1–V7 are **unchanged**. No RDKit, roles, AI
explanations, frontend, compare UI, resolver redesign, or
verification-rule change. No production-code change was needed to
the parser, normalizer, resolver, registry, or adapters.

---

## 1. Part A — ownership schema (migration 005)

- `ocr_runs.owner_subject TEXT NOT NULL`,
  `ocr_corrections.owner_subject TEXT NOT NULL`: the
  authenticated LabelLens subject (JWT `sub` or static-token
  subject). Never a token, never a provider account, never a
  display field. Orphan pre-ownership rows backfill to `''`,
  which matches no subject and stays unreadable (fail closed).
- `ingredient_observations.owner_subject TEXT NULL`: NULL marks
  pre-ownership rows (direct observations, regression fixtures),
  which keep legacy readability; every API-created observation
  from Stage 17 on carries its creator (OCR-derived observations
  inherit the run's owner, never the caller's).
- Enforcement is two-layer. Service: row owner vs authenticated
  principal on every OCR and observation read/write path;
  foreign rows answer 404 exactly like missing rows, so runs
  cannot be enumerated (documented choice, tested consistently).
  Database: RLS policies (`ocr_runs_owner_read`,
  `ocr_corrections_owner_read`,
  `ingredient_observations_owner_read`) predicate on
  `current_setting('app.current_subject', true)`; authenticated
  writes stay denied everywhere (default deny, no INSERT/UPDATE/
  DELETE policies); the service role bypasses by design, as in
  003/004. A missing/unset subject setting matches nothing.
- Claims, reviews, and audit events carry no owner yet — open
  and stated, not smuggled in.
- Bug found by the suite during this stage: re-applying 005
  aborted mid-file on pre-existing policies (asyncpg runs each
  migration file in an implicit transaction, and the fixtures
  swallow duplicate-object errors), silently rolling back the
  column additions. Fixed with `DROP POLICY IF EXISTS` guards
  for every policy the file manages; re-application is now
  provably idempotent.

## 2. Part A — API behavior

All four OCR routes pass `owner=principal.subject`; direct
observation routes (`POST|GET /observations`,
`.../analyze`, `.../candidates`, verification views) do the
same, so OCR-derived rows are isolated even through the old
endpoints. User B gets 404/`NOT_FOUND` on user A's run,
correction, analysis, and observations. Legacy NULL-owner rows
remain readable by everyone, exactly as before.

## 3. Part B — provider selected: OCR.space

Rationale: free development tier, key-only auth (no OAuth, no
SDK — plain `httpx`, already a dependency), one HTTPS POST
endpoint, and a response taxonomy that maps 1:1 onto explicit
failures (invalid key, quota exhaustion, processing errors,
empty results). Credentials come only from `OCR_SPACE_API_KEY`
(missing/blank fails at construction with a clear message);
the key travels as a form field, never in URLs, logs, results,
or rows. Image bytes travel only in memory (`OCRDocument.content`
or a `url` locator); nothing is persisted, and serialization
builders take whitelisted scalars so bytes cannot leak into a
row. Deployment injects `{"ocr-space": OCRSpaceProvider(key)}`
into `create_app(ocr_providers=…)` — no auto-wiring magic. No
live call was made from this environment (no key here); all
provider tests use injected `httpx.MockTransport`.
`FakeOCRProvider` remains available and is still the default in
tests and development.

## 4. Part B — failure handling

Missing/blank key → `ValueError` at construction. Invalid key,
quota messages, and processing errors → `ProviderFailure` with
the category preserved. HTTP 429 → quota failure; other 4xx/5xx
→ explicit HTTP errors; unreadable JSON → malformed-response
failure; missing/empty `ParsedResults` → no-results failure;
timeouts → timeout failure; connection errors → network failure;
unexpected exceptions → wrapped `ProviderFailure`. Extraction
always runs before any write, so failures persist nothing (the
API maps them to 503 `OCR_PROVIDER_UNAVAILABLE`). The adapter
returns text + confidence + overlay flag only — there is no code
path that could emit an entity, formula, CAS, SMILES, weight,
role, or verification state.

## 5. Verification performed

- `pytest app/tests`: **531 passed, 52 skipped** offline;
  **583 passed, 0 failed** live (557 Stage-16 + 26 new).
  (`SET ROLE authenticated` + subject setting: owners see only
  their rows, unset sees none, all authenticated writes denied)
  and the full OCR→verified path under ownership.
- `flake8 --max-line-length=88` clean, `compileall` clean,
  `git diff --check` clean.
- Regression CLI passes; Stage-15 VERIFIED cases remain
  VERIFIED; false positives remain 0; metrics unchanged
  structurally (one new fixture-free stage: no fixture added).
- New tests: 7 ownership unit, 16 provider adapter, 3 API
  (budget reuse + 2 cross-user), 1 live RLS (+1 migration
  file-exists from the 003–005 validation).

## 6. Known limitations / explicitly not implemented

- Per-user scoping stops at observations: claims, reviews, and
  audit events have no owner columns (claim/review ids remain
  unguessable UUIDs; documented residual).
- No real vendor is called from any environment here; production
  wiring is deployment configuration, documented above.
- No runs list endpoint, no image storage, single-revision
  corrections (unchanged from Stage 16).
- The pre-existing dev cluster lost its socket across a host
  restart; live results come from a rebuilt `labellens_test`
  (schema migrated from scratch by fixtures — equivalent).
