# Stage 18 — Data Isolation and Provider Validation

Date: 2026-10-06
Scope: exactly two objectives — (A) schema-wide ownership/access
isolation for user-derived label analysis, (B) a controlled real
OCR provider smoke path. No RDKit, roles, AI explanations,
frontend, compare UI, verification-rule or resolver change.

Verification rules V1–V7 are **unchanged**. The parser,
normalizer, resolver, registry, and adapters are untouched.

---

## 1. Ownership matrix by table

| Table | Class | Owner column | Read rule (`authenticated`) | Write rule |
|---|---|---|---|---|
| `ocr_runs` | user-owned | NOT NULL | owner only | service role only |
| `ocr_corrections` | user-owned | NOT NULL | owner only | service role only |
| `ingredient_observations` | user-owned | NULL = legacy | owner or NULL | service role only |
| `ingredient_normalizations` | user-owned | NULL = legacy | owner or NULL | service role only |
| `ingredient_candidates` | user-owned | NULL = legacy | owner or NULL | service role only |
| `entity_matches` | user-owned | NULL = legacy | owner or NULL | service role only |
| `verification_decisions` | user-owned | NULL = legacy | owner or NULL | service role only |
| `reviews` | user-owned + reviewer-visible | NULL = legacy | owner or NULL (reviewers via API, see §3) | service role only |
| `chemical_entities`, `ingredient_aliases`, `sources`, `domains`, `roles` | shared canonical | none, by design | pre-existing grants | service role / import only |
| `claims`, `claim_sources`, `verification_events` | shared by content | none, by design | all authenticated (global) | service role only |
| `review_events` | global audit | none, by design | all authenticated (global) | service role only |

Lineage: subject → run → correction → observation →
normalization → candidates/match → decision → review. Writes
inherit the **data** owner's subject, never the caller's: analyze
and observe read the parent row's owner first, so a caller cannot
relabel someone else's analysis by passing an owner value.

Why claims stay shared: claim identity (entity + field + value)
is deterministic chemistry content — two observers verifying
citric acid share one claim row rather than forking canonical
truth per user. Claim rows carry no observer, no label text, and
no owner linkage. Decisions (match-scoped, per-analysis) and
reviews (per-routing) are the user-scoped records; they link to
shared claims without owning them.

Why review events stay global: actor/reason/state/hash/rules —
no raw label text. They are reachable at the service layer only
through an owned-or-reviewer review read; direct database reads
remain authenticated-global, the pre-existing posture.

## 2. Migration 006 (`006_analysis_ownership.sql`)

- Nullable `owner_subject` on the five newly-scoped tables;
  legacy NULL rows keep prior readability and match no subject
  (nothing is backfilled — inventing historical ownership would
  be data fabrication).
- Owner-or-NULL SELECT policies for `authenticated` on all five
  plus the Stage-17 three; default-deny writes everywhere (no
  INSERT/UPDATE/DELETE policies); SELECT grants alongside each
  policy where 003 had revoked everything.
- Retired the permissive 003 audit policies on the two tables
  that became owner-scoped (`audit_read_decisions`,
  `audit_read_reviews`): permissive policies combine with OR and
  would have silently preserved global readability.
- Re-runnable: every managed policy is dropped before creation
  (the Stage-17 lesson: asyncpg runs each migration file in one
  implicit transaction and fixtures swallow duplicate-object
  errors, so a mid-file abort silently rolled back column
  additions — fixed the same way in 005).
- Static migration validation now covers 003–006; every live
  reset helper applies 001–006.

## 3. RLS/security behavior

- Subject travels in `app.current_subject`; unset matches
  nothing (fail closed). Service role bypasses by design.
- Service layer: `require_owner_match` (one shared helper)
  compares row owner vs authenticated principal on every OCR,
  observation, verification, and review read/write path;
  foreign rows answer 404 exactly like missing rows
  (anti-enumeration, tested consistently, never 403 with a
  distinguishing body).
- Reviewers (allowlisted role) bypass the owner filter through
  the API only — `list_pending`/`get` take an explicit
  `reviewer` flag; claim/decision were already reviewer-gated.
  Direct database access stays owner-scoped for everyone.
- Identical analyses from different users can share one review
  id (candidate-key routing dedupes); the row keeps its original
  owner, so each user reads only their own — and identical
  content leaks nothing new to either side.
  Rationale: human review of provisional items requires seeing
  candidates (including raw text); reviewers are operators, not
  arbitrary users; crippling the queue for symmetry would trade
  a real workflow for a theoretical one.

## 4. API access audit

All routes require authentication. Owner = verified token
subject; reviewer = allowlisted role:

- `POST /ocr/runs`: creator becomes owner.
- `GET /ocr/runs/{id}`, `POST .../correction`, `POST .../analyze`:
  run owner (or legacy-NULL), else 404.
- `POST /observations`, `GET /observations/{id}`,
  `POST .../analyze`, `GET .../candidates|resolution|verification`:
  creator/owner (or legacy-NULL), else 404.
- `GET /claims/{id}`: shared truth, 404 if missing (no owner).
- `GET /reviews/pending`, `GET /reviews/{id}`: own + legacy-NULL,
  else 404; reviewers see all.
- `POST /reviews/{id}/claim|decision`: reviewer role required
  (403 otherwise), no owner filter (workflow).

## 5. OCR provider smoke-test status: NOT EXECUTED live

`python -m app.cli.ocr_provider_smoke [--image F] [--document-id D]
[--pipeline]` loads `OCR_SPACE_API_KEY`/`OCR_SPACE_ENDPOINT`
from the environment only, extracts once, validates the
`OCRResult`, and prints safe metadata (provider, text length,
confidence, overlay flag, failure category, optional local
parse/normalize counts). Exit 0 success / 1 provider failure /
2 not-configured-or-bad-arguments. The key, raw text, and image
bytes never reach output, logs, or the database — the command
never opens a database at all. **No live provider request was
made in this environment (no key configured); no private/user
data was used** (default fixture is an embedded 1x1 PNG that
proves transport and contract only). Unit coverage
(`test_ocr_smoke.py`) exercises NOT_CONFIGURED, safe-output
success, categorized failure, pipeline entry, and bad-image
handling offline.

## 6. Verification performed

- Offline: **544 passed, 53 skipped** (includes 5 lineage unit,
  3 API isolation, 5 smoke, extended OCR suites).
- Live Postgres (actually executed, fresh-schema fixtures):
  **596+ passed, 0 failed**, including DB-level RLS negatives
  for every newly-scoped table, owner-threaded OCR→verified
  flow, and rerun stability.
- Regression CLI: PASS with unchanged metrics
  (labels=6 ingredients=62; exact=7; verified=2; FP=0).
- Stage-15 VERIFIED cases remain VERIFIED through corrected
  runs; Stages 13/14 suites green.
- `flake8 --max-line-length=88`, `compileall`, `git diff
  --check` clean.

## 7. Remaining limitations

- Claims, reviews' audit trail, and legacy NULL rows remain
  globally readable as documented in §1 (explicit residual,
  not an oversight to discover later).
- Real-vendor invocation is deployment configuration; the
  smoke path is proven offline only.
- No runs list endpoint; no image storage; single-revision
  corrections (unchanged).
