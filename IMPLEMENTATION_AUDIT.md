# LabelLens — Implementation Audit (Phase 0 Refresh)

**Date:** 2026-10-18
**Branch:** `feat/label-pipeline-foundation`
**HEAD:** `d0f7a50d9ff196236f7c9766055b3b051017bf89`
**Method:** six parallel read-only subagents + coordinator reconciliation
**Scope:** Repository reality check against the actual checkout. No code, migration,
deployment, or credential was modified, executed, or disclosed.

> The 2026-10-05 audit is preserved verbatim below under
> **§ARCHIVE**. Its "2 commits / single health endpoint / empty backend" characterization
> is **superseded** — it is accurate only about the frontend. See §2.

---

## 1. Baseline (recorded before work began)

| Attribute | Value |
|---|---|
| Branch | `feat/label-pipeline-foundation` |
| HEAD SHA | `d0f7a50d9ff196236f7c9766055b3b051017bf89` |
| Working tree | ` M .gitignore`; `?? backend/get_supabase_token.sh`; `?? docs/` |
| Upstream | `origin/feat/label-pipeline-foundation` — **0 ahead, 0 behind** |
| Remote | `https://github.com/amithsharma91/LableLens.git` — reachable (`ls-remote` exit 0) |
| Remote `main` | `2dbd2e15` "chore: scaffold project structure and base app" (2 commits) |
| Total commits | 48 (feat 19, docs 16, test 7, fix 2, chore 1, audit 1) |

**Read-only guarantee upheld.** After all six agents: HEAD unchanged, tree identical to
baseline, no stash, only the pre-existing one-line `.gitignore` diff.

---

## 2. Supersession of the prior audit

| Prior claim (2026-10-05) | Status now | Evidence |
|---|---|---|
| "empty frontend" | **STILL TRUE** | `find frontend -type f` → 0 files, 5 empty dirs, 0 tracked |
| "single health endpoint / 2 endpoints" | **SUPERSEDED** | 16 data routes across 5 routers, `main.py:310-319` |
| "exactly 2 commits" | **SUPERSEDED** | 48 commits |
| "no remote configured" | **SUPERSEDED** | `git ls-remote origin` exit 0 |
| "no `.env` or `.env.example` in repo" | **SUPERSEDED** | `backend/.env.example` tracked; `backend/.env` on disk (gitignored) |
| "1 test, passes" | **SUPERSEDED** | 606 collected, 48 test files |
| "OCR MISSING" | **SUPERSEDED** | `ocr_runs` table + OCR service/provider/routes (Stages 16–18) |
| "no Dockerfile, no deploy config" | **PARTLY SUPERSEDED** | Dockerfile + 4 ops scripts exist; no live deployment (Stage 18.5 = PARTIAL) |

---

## 3. Verified architecture

**Backend (FastAPI, Python 3.13) — real, substantial, tested.**
16 data routes; Supabase JWT (JWKS) auth; per-process rate limiting; 6 SQL migrations;
17 tables; Postgres + in-memory repositories; frozen V1–V7 verification gate; OCR
boundary with OCR.space adapter; human review; deterministic regression harness.

**Frontend — does not exist.** `frontend/` = 5 empty directories, 0 files, 0 tracked,
no `package.json`, no `.ts`/`.tsx` anywhere in the repo. No static mount, no template
engine, no API client. **Integration with the backend: zero points.**

**Entry points.** `app.main:create_app` (factory) and `app.serve:app_from_env`
(production, via module `__getattr__`; fail-closed).

---

## 4. Safe verification results (coordinator-run)

| Command | Result |
|---|---|
| `pytest app/tests -q` (offline, from `backend/`) | **1 failed, 551 passed, 54 skipped** |
| `pytest backend/app/tests/unit/test_serve.py` from a CWD with no `.env` | **7 passed, 1 skipped** |
| `pytest --collect-only -q` | **606 collected** |
| `pytest scripts/test_smoke_staging.py` (repo root + `PYTHONPATH`) | 5 passed |
| `python -m app.cli.run_label_regression` | `REGRESSION PASSED`, exit 0; labels=6, ingredients=62, verified=2, unknown=55, false_positives=0 |
| `flake8 app --max-line-length=88` | clean |
| `compileall -q app` | clean |
| `git diff --check` | clean |

**The single failing test is an environment artifact, not a code defect.**
`test_production_without_auth_config_fails_closed` deletes `SUPABASE_URL` from
`os.environ`, but `Settings.model_config` sets `env_file=".env"` and the local
untracked `backend/.env` supplies `SUPABASE_URL`, from which
`_derive_supabase_endpoints` re-derives issuer + JWKS. Proven by the CWD experiment
above: same code, same venv, 8/8 pass when `.env` is not resolvable. `build_token_verifier`
still fails closed when genuinely unconfigured (`api/auth.py:157-160`).

---

## 5. Findings by severity (coordinator-verified)

### P0 — blocking

**P0-1 Plaintext Supabase account email + password in `backend/get_supabase_token.sh`.**
Untracked and **not gitignored** (`git check-ignore` exit 1). One `git add -A` commits a
live credential pair. *Also functionally broken*: it indexes `os.environ` with an email
as the key, which always raises `KeyError`.

**P0-2 `chemical_entities` and `ingredient_aliases` have no RLS, no policy, no REVOKE.**
Verified: the 5 tables from `001_initial_schema.sql` are absent from the 12-table
RLS-enabled set. On a Supabase project with default `public` privileges this exposes the
canonical chemistry truth to the anon key. *(The privilege-inheritance claim is inference
from Supabase defaults, not verified live.)*

**P0-3 The entire RLS posture is inert.** Verified: zero hits for `current_setting`,
`set_config`, `SET ROLE`, or `current_subject` in non-test application code. The GUC
`app.current_subject` that all 8 owner policies depend on is **never set by the
application** — only by two integration-test helpers. The app connects as service role,
which bypasses RLS by design. RLS is configured but never activated; the only working
boundary is application-layer `require_owner_match` (6 call sites).

**P0-4 No CI of any kind.** Verified: no `.yml`/`.yaml`/`Jenkinsfile`/`Makefile`/`tox.ini`
anywhere. `TEST_STRATEGY.md:44` declares a passing pipeline "a prerequisite for merge";
none exists. Nothing would catch P0-1, the §4 test failure, or 54 silent skips.

**P0-5 Zero dependency pinning, no lockfile.** Verified: 0 pinned deps in `pyproject.toml`,
no lockfile, no `[build-system]`, floating `python:3.13-slim`. The staging image is not
reproducible. `serve.py` monkey-patches Starlette's internal `lifespan_context` — an
undocumented internal a minor bump can invalidate, with no CI to notice.

### P1 — high

**P1-1 `GET /api/v1/claims/{claim_id}` is not owner-scoped.** Verified independently by
the coordinator: the route (`api/v1/verification.py:157`) calls `service.get_claim(claim_id)`
with no owner; the method (`observation_service.py:433`) has **no `owner` parameter** at
all. Claim ids are deterministic `uuid5` over `entity|field|value`, so they are
computable offline. *Mitigating:* `006_analysis_ownership.sql:17-19` designates claims as
shared-by-content, so the global read is design-consistent — but it is undocumented, has
zero cross-user test coverage, and is the only user-data route without an ownership check.

**P1-2 `validate_no_secrets` is dead code.** Verified: zero non-test call sites (only the
definition, its own recursive self-calls, `__all__`, and the docstring). Seven green tests
cover a control the write path never invokes. Combined with unbounded free-form
`page_metadata` / `source_reference` dicts in `OCRIngestRequest`, a client can write
arbitrary JSON into `ocr_runs`.

**P1-3 `scripts/migrate_staging.sh --check` executes DDL and always exits 0.** Verified:
`CREATE TABLE IF NOT EXISTS public.schema_migrations` runs at lines 52-53, **before** the
mode branch at line 79 — while the header promises "Changes nothing". Then
`verify_schema && echo …` is followed by an unconditional `exit 0`, so a drifted schema
still returns success to any gate keying on exit status.

**P1-4 Migration apply and ledger record are not atomic.** The file runs under
`--single-transaction`; the ledger `INSERT` runs in a separate `psql` session. A crash in
between leaves the schema applied and the file unrecorded; the next run re-applies
`001_initial_schema.sql`, which has bare `CREATE TABLE` and fails immediately. Apply mode
becomes permanently broken with `--baseline` as the only escape.

**P1-5 100% of the Postgres layer is unexecuted.** 0 of 53 Postgres tests run without
`TEST_DATABASE_URL` (unset). All RLS policies, all `ON CONFLICT` idempotency, the entire
`schema_migrations` ledger, and 959 lines of `repositories/postgres.py` have **no executed
verification**. A green run is not evidence the persistence layer works.

**P1-6 Missing OCR credential is reported as 422, not 503.** With no `OCR_SPACE_API_KEY`,
the client gets `VALIDATION_ERROR "unknown ocr provider"` — a server misconfiguration
blamed on the client and indistinguishable from a typo. The wiring block
(`serve.py:77-86`) has zero test coverage.

### P2 — medium

- **P2-1** `verification_decisions.owner_subject` is written but never validated in Python.
- **P2-2** `DATABASE_URL` is passed as a `psql` argv on all 7 call sites — visible in `ps`.
- **P2-3** `DATABASE_URL` scheme conflict: `config.py` uses `postgresql+asyncpg://`; `psql`
  cannot parse it. The app and the migration script need *different* values under one name.
- **P2-4** `FILES` in `migrate_staging.sh` is hardcoded — a `007_*.sql` is silently ignored.
- **P2-5** `verify_schema` asserts only 8 columns + 8 policies; `--baseline` can bless a
  database missing `chemical_entities`.
- **P2-6** `APPLICATION` logs are lost in production: `LOG_LEVEL` is declared
  (`config.py:29`) but never read; uvicorn configures no root logger, so `labellens.*`
  INFO records (every auth rejection and request outcome) are discarded.
- **P2-7** No readiness endpoint; `/api/v1/health` is liveness-only and does not touch the DB.
- **P2-8** No security headers (HSTS, X-Content-Type-Options, X-Frame-Options, CSP).
- **P2-9** `allow_credentials=True` is unconditional; no production guard against
  `ALLOWED_ORIGINS="*"` (SECURITY.md claims the prohibition; code does not enforce it).
- **P2-10** `POST /reviews/{id}/claim` is `require_reviewer` but **unthrottled**.
- **P2-11** Client may choose `observation_id`; the API answers 201 with B's `raw_text`
  for a row owned by A (Postgres `ON CONFLICT DO NOTHING` prevents overwrite, but the
  response is false).
- **P2-12** Numeric presentation difference reported as a chemistry conflict: snapshot
  `144.1` vs PubChem `144.11` → `conflicted` for a non-existent disagreement (fails closed,
  but the stated reason is false).
- **P2-13** `unverified` resolutions with no alternatives are never routed to review.
- **P2-14** All 6 real-label fixtures are **self-reviewed by the implementing stage**; the
  CSVs are 0-row templates (`needs_real_label` / `needs_verification`).

---

## 6. Fact classification

**Verified in this checkout** — 16 routes; 6 migrations / 17 tables / 12 RLS-enabled;
Supabase JWT + JWKS with fail-closed production config; frozen gate
`VERIFICATION_RULES_VERSION = "1.0.0"` with a single guarded `VERIFIED` write site
(87-decision sweep: 0 promotions); no RDKit, no AI/LLM (grep-verified, incl. negative
assertions); OCR confidence never mapped to identity confidence (bidirectional tests);
OCR API key never logged/returned/persisted; `owner_subject` threaded on 8 tables;
regression CLI exit 0; flake8/compileall clean; frontend absent; no CI; no lockfile.

**Reported by prior stages, not rerun here** — the `CHANGELOG.md` pass-counts
(16/16 … 557/557); "live-validated against real Postgres 18". No CI log or artifact
in-repo substantiates them. Do not quote as current fact.

**Documented but not implemented** — `API_SPEC.md` §§13-47 (`scans`, `analyses`,
`comparisons`, `products`, `search`, `sources`); `DEMO_SCRIPT.md` flow; the
`DEVELOPMENT_GUIDE.md` frontend commands (no `package.json`); `TEST_STRATEGY.md`'s six-stage
CI; ≥80% coverage gate; `pip-audit`.

**Blocked by unavailable credentials or services** — any staging deployment (`gcloud`
ABSENT, `docker` ABSENT, no `PROJECT_ID`, no GCP credentials, `cloud.google.com`
unreachable); live OCR (`OCR_SPACE_API_KEY` UNSET); staging smoke (needs two real Supabase
user JWTs); live-DB integration tests (`TEST_DATABASE_URL` UNSET). Stage 18.5 correctly
self-declares **PARTIAL**.

**Unknown or conflicting** — whether the snapshot's `144.1` is a transcription error or a
deliberate value (P2-12); whether global claim reads are intentional (P1-1 — needs an owner
decision); whether `docs/research/PHASE0_AUDIT.md` (46 KB, untracked) is authoritative or
superseded by this document; which of five incompatible "Phase N" vocabularies is
canonical.

---

## 7. Phase / stage status

| Stage | Status | Note |
|---|---|---|
| 2, 4, 5 (parser / normalizer / resolver) | Complete | no `STAGE_*.md`; CHANGELOG + ADR-016/017/018 only |
| 6 (verification architecture) | Complete | architecture-only by design |
| 7–9 (gate, evidence, review) | Complete | |
| 10–12 (persistence, API, production readiness) | Complete | |
| 13–15 (real-label slice, systematic names, verified path) | Complete | ground truth self-reviewed |
| 16–18 (OCR, ownership, isolation) | Complete | |
| 18.5 (deployment) | **PARTIAL** | artifacts complete; execution blocked on credentials |
| **19 (RDKit)** | Not started — **gated** | docs say "unblocked", but 12 gaps (see §9) |
| Frontend (all phases) | **Not started** | 0 files |

**Stage 19 gate conflict:** `STAGE_18_5_DEPLOYMENT.md:236-241` says RDKit "may begin …
only execution against real GCP/Supabase credentials remains, which is an operator action,
not a code gap." That is **inaccurate** — P0-3, P0-4, P0-5, P1-5, P2-6 and P2-7 are all
*code* gaps, not operator actions.

---

## 8. Smallest safe next task (do not implement in this audit)

**Stop the credential bleed and make the isolation posture truthful.**
Commit the already-staged `.gitignore` rule and gitignore the credential script; then
decide and document the `GET /claims/{id}` ownership posture.

**Scope** — no new feature; no chemistry; no frontend; no pipeline change.
**Files** — `.gitignore` (add `backend/get_supabase_token.sh` and a `*.sh`-adjacent rule),
`SECURITY.md` (record the decision + the inert-RLS fact), and one new regression test if
the claim route is tightened.
**Acceptance criteria** — (a) `git check-ignore backend/get_supabase_token.sh` exits 0;
(b) `git add -A --dry-run` stages no credential-bearing path; (c) `.dockerignore` excludes
`.supabase-auth.env` so the build context is safe; (d) the RLS-inertness finding is
recorded as a known limitation rather than claimed as a control.
**Tests** — extend `app/tests/unit/test_persistence_security.py` / a new
`test_secret_paths_are_ignored.py` to assert the ignore rules, so the regression cannot
reopen. Do **not** weaken any ownership, auth, or RLS check.
**Dependencies** — none. Runs entirely offline. Precedes Stage 19 and any deployment.

**Explicitly NOT the next task:** Stage 19 RDKit, frontend scaffolding, deploying, or
"fixing" the §4 test by weakening it — that test is correct; the local `.env` is the
problem, and the fix is test isolation or `.env` hygiene, not a relaxed assertion.

---

## 9. Why Stage 19 (RDKit) is not the next task

Even though the docs call it unblocked, RDKit today would produce descriptors with **no**
version provenance column, **no** `input_representation` field, **no** `computed`
provenance tag (the enum exists at `003:132`; nothing writes it), **no** eligibility gate,
**no** descriptor table (`DATA_PIPELINE.md:463-475` mandates the output contract), and
**no** `unit`/derivation column on `claims` (`serialize.py:214-227` hard-codes
`unit: None`). `CONFLICT_FIELDS` deliberately excludes `smiles`/`inchi` because "only
cheminformatics could compare them" (`evidence.py:63-74`) — that becomes the first
structural change. Also note the chemistry base is a **4-record snapshot** transcribed
2026-10-05; PubChem/ChEBI adapters exist but are wired into nothing in production.

---

# TASK 0.1 — Credential Containment and Build-Context Protection

**Date:** 2026-10-18
**Branch:** `feat/label-pipeline-foundation`
**HEAD at start:** `d0f7a50d9ff196236f7c9766055b3b051017bf89`
**Status:** COMPLETE — all acceptance criteria verified (see T8)

## T0. Scope and constraints honoured

Read-only investigation by six parallel subagents (Agent 4 required one
re-spawn after returning empty). No credential file was read, printed, or
executed. `backend/get_supabase_token.sh` was never run. No migration, no
deployment, no OCR call, no database connection, no network request.

Explicitly **not** done, per the brief: the token helper was not rewritten,
no local credential file was deleted, no route behaviour was changed, no
password was rotated, nothing was pushed or deployed.

## T1. Second, unreported gap found

The Phase 0 audit recorded one containment gap. Investigation found **two**:

| Path | Ignored in working tree? | Ignored in a fresh clone at HEAD? |
|---|---|---|
| `backend/get_supabase_token.sh` | NO | **NO** |
| `backend/.supabase-auth.env` | yes — but **only** via an uncommitted line | **NO** |

`git show HEAD:.gitignore` has 32 lines and no `.supabase-auth.env` rule.
Neither `.env` nor `.env.*` can match a basename beginning `.supabase`
(verified: `x/.envrc` and `x/.supabase-auth.env.bak` both exit 1). So a
fresh clone exposed **both** files, and `git add -A --dry-run` proposed
the script.

## T2. Root causes

1. **No Git rule existed for the helper.** `.gitignore` had no `*.sh` or
   `get_supabase_token.sh` rule in HEAD or the working tree.
2. **The protective rule was never committed.** It existed only as an
   uncommitted one-line edit, so it protected no clone.
3. **`.dockerignore` semantics were misapplied — and one line was a
   no-op.** Docker matches patterns against the path relative to the build
   context root (`backend/Dockerfile:7`, repo root), *not* the basename as
   gitignore does. The pre-existing `.env` line therefore matched nothing
   under `backend/`; there is no root `.env` in the repository. Verified
   by a `moby/patternmatcher`-equivalent matcher: `(".env",)` against
   `"backend/.env"` = **no match**. `SECURITY.md` had asserted this line
   provided the protection; it did not.

## T3. Changes implemented

| File | Change |
|---|---|
| `.gitignore` | Added `/backend/get_supabase_token.sh` (lines 35-39). **Preserved** the pre-existing uncommitted `.supabase-auth.env` line 33 verbatim. |
| `.dockerignore` | Added `/backend/.env`, `/backend/.env.local`, `/backend/.supabase-auth.env`, `/backend/get_supabase_token.sh`. |
| `backend/app/tests/unit/test_secret_paths_are_ignored.py` | New, 38 tests. |
| `SECURITY.md` | Added §5.1 Implemented Boundary (verified 2026-10-18); corrected the false `.dockerignore`/`.env` claim. |
| `IMPLEMENTATION_AUDIT.md` | This section. |

Anchored path forms were chosen over `*.sh` / `*.env` on purpose: a bare
`*.sh` would silently hide any future script from `git add`, and
`scripts/deploy_staging.sh` and `scripts/migrate_staging.sh` must stay
tracked and visible. Both are asserted by a dedicated control test.

## T4. Pre-existing SECURITY.md inaccuracies corrected

Four false claims were found and are now corrected or explicitly
overridden. These were **not** introduced by this task; they were
pre-existing and are recorded here so the diff is not mistaken for new
drift.

1. §5 line 200 — "RLS policies are the last line of defense for data
   isolation." Contradicted by the application's own service-role
   connection. Now corrected in §5.1.
2. §5 line 210 — Policy Summary lists `verified_chemical_entities`. No such
   table exists; the real one is `chemical_entities`
   (`001_initial_schema.sql:50`). Superseded by the implemented matrix.
3. §6 / Stage-18 — `chemical_entities` and `ingredient_aliases` protected
   "per pre-existing grants". **No `GRANT`/`REVOKE` exists for either
   table in any migration**; `001` and `002` contain no privilege
   statement at all. Now recorded as an open gap requiring separately
   planned remediation.
4. §Stage-18.5 — "`.dockerignore` excludes `.env`". Provably false; see T2.
   Corrected with an explicit note of the previous error.

Also corrected: §5 line 219 recommends `auth.uid()`, but no policy in this
repository uses it — the owner policies use
`current_setting('app.current_subject', true)`.

## T5. Verification — exact commands and results

| Command | Result |
|---|---|
| `git check-ignore -v --no-index backend/get_supabase_token.sh` | `.gitignore:39:/backend/get_supabase_token.sh`, **rc=0** |
| `git check-ignore -v --no-index backend/.supabase-auth.env` | `.gitignore:33:.supabase-auth.env`, **rc=0** |
| `git add -A --dry-run` | Proposes `.dockerignore`, `.gitignore`, `IMPLEMENTATION_AUDIT.md`, `SECURITY.md`, `test_secret_paths_are_ignored.py`, `docs/research/PHASE0_AUDIT.md`. **Neither credential path appears.** Index verified clean afterwards. |
| `pytest app/tests` from `/tmp/opencode` (**controlled CWD**) | **590 passed, 54 skipped, 0 failed** (41.91s) |
| `pytest app/tests` from `backend/` (uncontrolled CWD) | 589 passed, 54 skipped, **1 failed** — the pre-existing `test_serve.py` failure, see T7 |
| `pytest app/tests/unit/test_secret_paths_are_ignored.py` | **38 passed** |
| `flake8 app --max-line-length=88` | **rc=0**, clean (after fixing one W292) |
| `python -m compileall -q app` | **rc=0** |
| `git diff --check` | **rc=0**, clean |

## T6. Non-vacuity proven by deliberate breakage

The acceptance criterion is that the tests **fail** when an exclusion is
removed. Both were verified by temporarily removing each rule, observing
failures, and restoring the files byte-identically (md5 confirmed).

| Removal | Failures observed |
|---|---|
| `/backend/get_supabase_token.sh` from `.gitignore` | **5 failed** — `test_secret_path_is_git_ignored`, `test_ignore_rule_is_not_a_negation`, `test_ignore_rule_comes_from_a_committed_file`, `test_git_add_dry_run_does_not_propose_secret_paths`, `test_secret_rule_resolves_to_a_path_covering_the_target` |
| the four `/backend/...` lines from `.dockerignore` | **3 failed** — `test_dockerignore_excludes_secret_paths`, `test_dockerignore_excludes_local_env_file`, `test_dockerignore_names_the_secret_paths_literally` |

Anti-vacuity devices in the test module:

- `git check-ignore --quiet` is used for the boolean, **not** `-v`.
  Verified: `-v` exits **0** even for a `!` negation
  (`.gitignore:14:!.env.example backend/.env.example` gives rc=0), so an
  exit-code-only assertion on `-v` would accept a negated match as
  "ignored". `-q` returns 1 there, correctly.
- Four negative controls: `backend/app/serve.py` and both tracked ops
  scripts must **not** be ignored by Git or Docker.
- A Docker-matcher semantics table with 20 literal cases, including the
  two trap rows that fail a gitignore-style implementation
  (`("*.env",)` against `"backend/.env"` = False; `("*.sh",)` against
  `"backend/get_supabase_token.sh"` = False).
- A forced `-f` dry-run control proving the `git add` harness is live.
- `git -C REPO_ROOT` on every invocation, so results never depend on the
  directory pytest was launched from.

## T7. Pre-existing failure — reported separately, NOT conflated

`app/tests/unit/test_serve.py::test_production_without_auth_config_fails_closed`
fails **only** when pytest runs from `backend/`, where the untracked
`backend/.env` is readable by `Settings.model_config` (`env_file=".env"`,
`config.py:122-123`). Verified by CWD experiment: from a directory without
a resolvable `.env` the whole suite is **590 passed / 0 failed**; from
`backend/` the same code yields the single failure.

This is **test-environment leakage, not credential containment**, and it
is **not** addressed by this task. The assertion is correct and security
relevant — production must refuse to start without Supabase configured.
Fixing it requires either constructing `Settings` with explicit
constructor kwargs or running unit tests from a CWD without a `.env`;
neutralising or deleting `backend/.env` is explicitly out of scope.
**No security assertion was weakened.**

## T8. Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| Both credential paths ignored in a fresh checkout | **MET** | `.gitignore:39` (anchored) and `.gitignore:33` now committed; T5 checks 1-2 |
| Dry-run staging proposes neither path | **MET** | T5 check 3 |
| Docker ignore rules exclude both from the build context | **MET** | T5 + literal-pattern assertions |
| Regression tests fail if either exclusion is removed | **MET** | T6 — 5 and 3 failures observed respectively |
| Security docs describe the real boundary and open decisions | **MET** | §5.1 records the service-role bypass, `app.current_subject` not being set, the five tables without RLS, and the claims route as an **open decision with no ruling invented** |
| Existing working-tree changes and untracked user files preserved | **MET** | `.gitignore:33` preserved verbatim; `IMPLEMENTATION_AUDIT.md` extended in place; `docs/` untouched and unstaged; no credential file deleted or modified |
| Audit lists exact commands/results and separates verified from blocked | **MET** | T5 and T9 |

## T9. Blocked / not verified — stated honestly

- **No live deployment or Cloud Build upload was performed or verified.**
  `gcloud` and `docker` are both ABSENT; `cloud.google.com` is
  unreachable. The Docker exclusions are proven against a
  `moby/patternmatcher`-equivalent matcher and by literal semantic cases,
  **not** by an executed `docker build`.
- **`gcloud builds submit` may not consult `.dockerignore` at all.** Per
  the official reference, when no `.gcloudignore` exists and a `.gitignore`
  does, gcloud generates a Git-compatible ignore file from `.gitignore`.
  No `.gcloudignore` exists here. So the *upload* filter is currently
  governed by `.gitignore` — which this task has just strengthened — and
  `.dockerignore` governs local builds and post-upload `COPY` scoping.
  Adding a `.gcloudignore` or `--ignore-file` to `deploy_staging.sh` is a
  **separate, higher-leverage change** and was deliberately not made here.
- **Password rotation was NOT performed.** The credential exposed in
  `backend/get_supabase_token.sh` (a hardcoded account email) and
  `backend/.supabase-auth.env` (which holds an account password and an
  anon key) must be treated as compromised and rotated **by the
  operator**. Ignore rules prevent accidental commit; they do not undo an
  exposure.
- **No secret has ever been committed.** 167 tracked files scanned across
  all 50 commits for JWT-, `sk-`, `sbp_`- and `sb_secret_`-shaped strings
  and `BEGIN PRIVATE KEY`: **zero matches**. History is clean.
- **Live database privileges on the five unprotected tables remain
  unverified.** Whether Supabase's default `public` grants expose
  `chemical_entities` to the anon key is inference from documented
  defaults, not a live observation.
- **`docs/research/PHASE0_AUDIT.md` remains untracked and unstaged.** It
  needs an owner decision; staging it was out of scope.
- A suspected latent defect was reported by investigation and **not**
  addressed: `deploy_staging.sh:43-47` passes no `--file` and there is no
  root `Dockerfile`, yet `--tag` requires one. Unverifiable without
  `gcloud`.

## T10. Operator actions (no credentials in chat)

1. **Rotate the exposed Supabase credential.** It exists in plaintext in
   two untracked files. Do not paste it into chat.
2. Decide the `GET /api/v1/claims/{claim_id}` ownership question. §5.1
   records it as open; no ruling was invented and no route was changed.
3. Decide whether `docs/research/PHASE0_AUDIT.md` should be tracked.
4. Consider a `.gcloudignore` so the Cloud Build upload filter is
   deterministic rather than inferred from `.gitignore`.
5. Consider `chmod 600 backend/.env` — it is currently world-readable
   (mode 644) unlike `.supabase-auth.env` (mode 600).

---

# ARCHIVE — superseded audit, preserved verbatim

> Everything below is the **2026-10-05** audit, preserved for history. Per §2 it is
> accurate only about the frontend; its backend, commit-count, remote, test-count, and
> deployment claims are superseded by §1-§9 above.

**Date:** 2026-10-05
**Branch:** `feat/label-pipeline-foundation`
**Auditor:** Implementation agent (read-only inspection + baseline test run)
**Scope:** Full repository reality check BEFORE any major implementation, per master brief §2 / §21.

> Rule honored: no major rewrite before audit. Only change so far is creating the feature
> branch. Baseline verification: `pytest backend/app/tests -v` → **1 passed**.

---

## 0. Headline finding — brief vs repository mismatch (must read first)

The master brief describes the repository as a **Vite/React Google AI Studio prototype** with
existing files such as:

- `src/lib/parsing/ingredientParser.ts`
- `src/lib/normalization/ingredientNormalizer.ts`
- `src/lib/entity-resolution/entityResolver.ts`
- `src/lib/pipeline.ts`
- `src/services/labelExtractionService.ts`
- `src/services/webResearchService.ts`
- full UI screens (Home, Scan, Product Analysis, Compare, Catalog/Search, Learn, …)

**None of those files exist in the cloned repository.**

Verified by `ls -laR frontend/`, `find`, and `git log --stat`:

- `frontend/` contains only two **empty** directories: `frontend/src/lib/api/` and
  `frontend/src/types/`. No `package.json`, no components, no router, no styles.
- `backend/app/` contains only a health endpoint, config, CORS setup, one Pydantic schema,
  and one unit test. No parsing, normalization, entity-resolution, pipeline, OCR,
  web-research, chemistry, evidence, or comparison code.
- Git history has exactly **2 commits**: `Phase 1: Core Foundation` (specs + skeleton) and
  `Fix flake8 styling`.
- No remote is configured (`git remote -v` returns empty), so
  `amithsharma91/LableLens` could not be cross-checked from here.

**Consequence:**

1. There is **no product UI to preserve** in this checkout. §14 of the brief
   ("do not downgrade the current visual product") is vacuously satisfied — there is
   nothing to downgrade, but also nothing to leverage.
2. There is **no duplicated/conflicting ingredient logic to unify yet** (§2D). That section
   of the brief is written against a different codebase state. The audit answers it as
   "not applicable — greenfield", which is actually good news: we can establish **one**
   canonical pipeline from the start instead of untangling three.
3. `INGREDIENT_GOLDEN_DATA.csv` (100 rows) is correctly marked `needs_verification` with
   **all chemistry fields empty** — it is a candidate seed, not ground truth. The brief's
   warning is accurate and must be kept.
4. `LABEL_REGRESSION_DATASET.csv` (30 rows, LR-001…LR-030) is a **scaffold with no label
   text at all** — every row is `needs_real_label`. It cannot be used as a correctness
   benchmark until real labels are ingested.

If a richer prototype exists elsewhere (another branch, another repo, a local export),
it should be added to this repo or the brief should be amended. Until then, all
"preserve the prototype" requirements are recorded as **blocked on missing input**,
and implementation proceeds on the **spec-defined target stack**
(Next.js + FastAPI + RDKit + Supabase) starting from the existing FastAPI skeleton.

---

## A. Repository reality

| Area | Finding | Evidence |
|---|---|---|
| Framework (backend) | **FastAPI + Pydantic v2**, async SQLAlchemy + asyncpg | `backend/app/main.py`, `config.py`, `dependencies.py`, `pyproject.toml` |
| Framework (frontend) | **Intended Next.js + TypeScript + Tailwind** per specs; **actually empty dirs**, no `package.json`, no code | `ls -laR frontend/` → only empty `lib/api`, `types` |
| Runtime | Python **3.13.5**, Node **v26.4.0**, npm **11.19.1** | `python3 --version`, `node --version` |
| Build system (backend) | `pyproject.toml` with pytest config only (`testpaths=["app/tests"]`, `asyncio_mode=auto`). **No** `requirements.txt`, no ruff/mypy config, no Dockerfile, no CI workflow | `backend/pyproject.toml`, repo root listing |
| Build system (frontend) | **None** — no `package.json`, no `tsconfig`, no Tailwind config, no Next.js scaffold | `find` for `package.json`/`*.ts` → no hits outside `.venv` |
| Dependency state (backend venv) | fastapi 0.142, uvicorn, pydantic 2.13, pydantic-settings, SQLAlchemy 2.1, asyncpg, httpx, pytest 9.1 + pytest-asyncio, flake8. **No RDKit, no OCR lib, no Gemini/OmniRoute SDK, no Supabase client** | `pip list` in `backend/.venv` |
| Frontend architecture | **Does not exist.** Spec target (`lib/api/client.ts`, `scans.ts`, … + `types/api.ts`) is documented in `ARCHITECTURE.md` §4 but not implemented | empty `frontend/src` |
| Backend architecture | Skeleton only: `main.py` (CORS + router mount) → `api/v1/health.py` → `schemas/common.py`. `providers/`, `repositories/`, `services/` directories exist but are **empty**. `config.py` reads `DATABASE_URL`, `ALLOWED_ORIGINS` | `ls -laR backend/app` |
| API endpoints | Exactly **2**: `GET /` and `GET /api/v1/health` (returns `{data:{status:"ok",version:"0.1.0"}}`) | `main.py`, `health.py`, `test_health.py` |
| Environment variables | Backend reads `ENVIRONMENT`, `LOG_LEVEL`, `ALLOWED_ORIGINS`, `DATABASE_URL` (default local postgres). **No `.env` or `.env.example` files exist** in repo. Required vars from specs (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `MAX_UPLOAD_BYTES`, `OCR_PROVIDER`, `AI_PROVIDER`, `PUBCHEM_BASE_URL`, …) are **not wired** | `config.py`, `find -name "*.env*"` → none |
| Current persistence | **None live.** Migrations `001_initial_schema.sql` (domains, roles, sources, chemical_entities, ingredient_aliases) and `002_seed_data.sql` (9 domains, 9 sources) exist but there is **no evidence they were ever applied** (no DB URL reachable here, no seed script, no repository code, no Supabase project reference) | `backend/migrations/*` |
| Current data sources | **None wired.** No PubChem/ChEBI/Codex/FSSAI/CosIng adapters, no local golden cache, no source-registry table access code | empty `providers/`, `repositories/` |
| Current testing | **1 test**: `test_health_endpoint` (ASGI transport, asserts 200 + status ok). **Passes.** No unit/integration/contract/E2E/regression/golden tests | `app/tests/unit/test_health.py`, pytest run 2026-10-05 |
| Docs | 17 Markdown specs + 2 CSVs present and internally consistent (see `IMPLEMENTATION_READINESS_REPORT.md`, `DOCUMENTATION_COVERAGE_REPORT.md`). `CHANGELOG.md` is at v0.1.1 (docs only, "No implementation code shipped") — accurate | root listing, `CHANGELOG.md` |
| Git hygiene | `master` clean; feature branch `feat/label-pipeline-foundation` created for this work. **Problem: `__pycache__/*.pyc` files are committed** (both commits include them). No `.gitignore` observed | `git log --stat`, `git status` |
| Deployment | **Nothing deployed.** No Vercel/Render/Railway config, no Dockerfile, no CI YAML | repo root listing |

---

## B. Feature status

Legend: WORKING / PARTIAL / MOCKED / BROKEN / MISSING / NEEDS VERIFICATION.

### User-facing surfaces

| Feature | Status | Notes |
|---|---|---|
| Home | **MISSING** | No frontend code at all |
| Scan | **MISSING** | No upload endpoint, no camera UI |
| Upload | **MISSING** | No `POST /api/v1/scans`, no multipart handling |
| Camera/file handling | **MISSING** | — |
| OCR | **MISSING** | No adapter, no `ocr_runs` table (Phase 2 table not yet migrated) |
| OCR error handling | **MISSING** | — |
| Raw OCR preservation | **MISSING** | No `ocr_runs` / `ingredient_observations` tables or code; spec contract defined in `DATA_PIPELINE.md` Stage 1 only |
| Ingredient extraction | **MISSING** | No parser of any kind (naive or hierarchical) |
| Hierarchical parsing | **MISSING** | ← **highest-value first implementation (this branch)** |
| Manual text entry | **MISSING** | — |
| Editing / deletion / reordering | **MISSING** | No observation endpoints |
| Nested ingredient handling | **MISSING** | — |
| Percentages | **MISSING** | — |
| Additive identifiers (INS/E) | **MISSING** | — |
| Normalization | **MISSING** | No normalizer code; 6-method taxonomy defined in specs only |
| Entity resolution | **MISSING** | No matcher; resolution states defined in specs only |
| Local catalog matching | **MISSING** | `chemical_entities` + `ingredient_aliases` tables defined in migration but no data, no lookup code |
| Mixture handling | **MISSING** | Representation-type taxonomy defined in specs only |
| Ambiguous ingredient handling | **MISSING** | — |
| Web research fallback | **MISSING** | No Gemini/OmniRoute integration, no `webResearchService` |
| Source extraction / provenance | **MISSING** | `sources` table defined in migration; no claim/source code |
| Confidence (multi-dimensional) | **MISSING** | Vocabulary defined in specs; no code |
| Ingredient detail | **MISSING** | No `GET /api/v1/ingredients/{id}`, no UI |
| Chemistry representation | **MISSING** | No RDKit, no formula/MW/SMILES code |
| RDKit integration | **MISSING** | `import rdkit` → `ModuleNotFoundError`. Not in `pyproject.toml` |
| Product analysis | **MISSING** | No analysis pipeline, no `analysis_runs` tables |
| Compare | **MISSING** | No comparison endpoints, no UI |
| Actual scan-to-compare flow | **MISSING** | E2E critical path (`API_SPEC.md` §77) has zero coverage |
| Persistence | **PARTIAL** | Phase-1 DDL + seeds exist on disk, unapplied; app never connects (engine created in `dependencies.py` but no route uses `get_db`) |
| Authentication | **MISSING** | No auth; acceptable per spec (MVP may operate without accounts) |
| Security (upload/MIME/rate-limit/prompt-injection/RLS) | **MISSING** | No upload path to secure yet; CORS is the only control present (`ALLOWED_ORIGINS`, `allow_credentials=True` — note §F finding below) |
| Testing | **PARTIAL** | Health test WORKING; everything else MISSING (see §F) |
| Deployment | **MISSING** | No frontend/backend deploy config |

### Backend slice status (per `DEVELOPMENT_GUIDE.md` §9 vertical slices)

| Slice | Status |
|---|---|
| 1 Health + DB | **PARTIAL** — health WORKING; DB DDL on disk, not applied, no DB test |
| 2 Scan | MISSING |
| 3 OCR | MISSING |
| 4 Ingredient editing | MISSING |
| 5 Entity matching | MISSING |
| 6 Chemistry | MISSING |
| 7 Evidence | MISSING |
| 8 Analysis | MISSING |
| 9 Compare | MISSING |
| 10 Grounded explanation | MISSING |

---

## C. Trace the actual scan pipeline

There is **no scan pipeline in code**. The intended pipeline (per `DATA_PIPELINE.md`,
`ARCHITECTURE.md` §6) vs reality:

```
Stage                              Spec contract              Code reality
─────────────────────────────────  ─────────────────────────  ──────────────
1  OCR (raw_text, conf, engine)    DATA_PIPELINE §Stage 1     MISSING — no endpoint, no ocr_runs table
2  Extraction (raw → tokens)       §Stage 2                   MISSING — no parser at all
3  User correction (non-destr.)    §Stage 3                   MISSING — no PATCH endpoint
4  Normalization (6 methods)       §Stage 4                   MISSING
5  Entity resolution (6 states)    §Stage 5                   MISSING
6  Validation gates                §Stage 6                   MISSING
7  RDKit computation (gated)       §Stage 7                   MISSING (rdkit not installed)
8  Role resolution (domain ctx)    §Stage 8                   MISSING
9  Evidence assembly (claim-lvl)   §Stage 9                   MISSING
10 Grounded explanation            §Stage 10                  MISSING
```

Executable code path today:

```
GET /api/v1/health → HealthResponse(data={status:"ok", version:"0.1.0"})
```

That is the entire backend. `dependencies.py` builds an async engine from
`DATABASE_URL`, but no router, service, or repository imports it.

---

## D. Duplicated / conflicting logic

**Not applicable — no duplication exists because no logic exists.**

The brief's §D checklist is answered against an empty set:

- [ ] OCR segmenting ingredients? No OCR code.
- [ ] `labelExtractionService.ts` extra parsing? File does not exist.
- [ ] `parseRawLabelText()` naive comma split? Function does not exist.
- [ ] `parseIngredientTree()` used consistently? Function does not exist.
- [ ] `pipeline.ts` canonical path? File does not exist.
- [ ] UI bypassing canonical pipeline? No UI.
- [ ] Normalization in multiple places? No normalizer.
- [ ] Entity matching in multiple places? No matcher.

**Architectural decision recorded for the build-out (see `DECISIONS.md` ADR-016
proposed): exactly ONE canonical extraction entry point —
`backend/app/services/ingredient_parser.py :: parse_label_ingredients(text)` —
returning a tree of nodes. All future paths (OCR post-processing, manual-text entry,
re-analysis after correction, tests, seed scripts) must call it. No UI/service may
implement its own `split(",")`. This audit establishes that rule before the first
competing implementation appears.**

---

## E. Scientific integrity audit

No chemistry-fabrication code exists yet (nothing to flag in `grep` terms — there is
no `smiles`, `cas`, `formula`, `safe`, `healthy` string anywhere in `backend/app` or
`frontend/src` outside specs). The risk is therefore **prospective**, and the audit
converts each brief §E bullet into a build-time gate:

| Risk | Current state | Gate for future code |
|---|---|---|
| Invent chemical identity / formula / SMILES / CAS | No code paths; golden CSV has all such fields **empty** (good) | Parser/normalizer/matcher must never populate chemistry fields; only a future verified-source adapter + RDKit gate may. Parser nodes carry `matchStatus="unresolved"`, `verificationStatus="unverified"` by construction |
| Assign structure to a mixture | No structures anywhere | `representation_type` allowlist enforced at parse→chemistry boundary; mixtures (`peanut butter`, `whey protein concentrate`, `lecithin`, `fragrance`, …) stay structureless |
| Claim regulatory verification without evidence | No regulatory code | Jurisdiction + source + date required per `SOURCE_REGISTRY.md`; no `verified` status without them |
| Treat AI text as verified fact | No AI integration | AI outputs enter only as `candidate` (ADR-007); no AI-writes-to-canonical path |
| Umbrella term → single molecule | No resolver | Resolver must return `ambiguous`/`no_match` for `natural flavouring`, `colour`, `spices`, etc. |
| "good/bad/safe/unsafe/healthy" labels | No UI copy | Banned vocabulary in analysis/explanation outputs; comparison must not rank products |

The canonical parser implemented on this branch is deliberately **chemistry-free**:
it extracts structure (nesting, percentages, identifiers) and performs only
**syntactic** normalization (case/whitespace/punctuation). It does not guess entities,
formulas, or roles. That separation is the primary anti-hallucination control at this
layer.

---

## F. Dependency / runtime / security / testing findings

1. **Python deps (installed):** fastapi, uvicorn, pydantic-settings, SQLAlchemy, asyncpg,
   pytest, pytest-asyncio, httpx, flake8. All import cleanly on Python 3.13.
2. **Missing for target stack:** `rdkit` (deliberately **not** added in this slice —
   parser needs no chemistry; RDKit arrives with the chemistry slice and its Dockerfile
   story, per `IMPLEMENTATION_READINESS_REPORT.md` risk #3), OCR libs, Supabase client,
   rate-limit lib (`slowapi`), image libs (Pillow). `pyproject.toml` has **no**
   `[tool.ruff]`/`[tool.mypy]` sections and no `requirements.txt` — reproducible pinning
   is a gap to fix before deployment (not blocking for parser slice).
3. **Frontend toolchain:** none. Initializing Next.js is explicitly **deferred** — no UI
   work is justified until the scan→analysis contract has a backend to talk to.
4. **Committed `.pyc` files:** `__pycache__/*.pyc` are tracked in git (both commits).
   Add `.gitignore` (Python + Node + `.env`) and untrack them — hygiene fix queued with
   this branch's commits.
5. **CORS note:** `allow_credentials=True` combined with `allow_headers=["*"]` is fine
   for local dev with an explicit origin allowlist, but production must restrict
   `allowed_origins` to the Vercel domain and avoid credentialed wildcard patterns
   (spec `SECURITY.md` §10). No change needed yet — no authenticated endpoints exist.
6. **No secrets in repo:** confirmed (`find -name "*.env*"` → none; `config.py` uses
   env vars with safe defaults). Keep it that way; add `.env.example` files when the
   DB/AI slices land.
7. **Testing gaps:** 1/1 passing. Missing per `TEST_STRATEGY.md`: parser unit tests
   (Cases A–J — **added this branch**), normalization/matcher/chemistry unit tests,
   API contract tests, DB integration tests (need test DB), E2E critical path,
   regression dataset (blocked on real labels), golden verification (blocked on source
   lookups). Coverage gates (≥80% changed files) cannot be measured — no coverage tool
   configured yet.

---

## G. Prioritized implementation plan (smallest safe sequence)

Executed and proposed order. Each item is independently verifiable.

| # | Step | Status | Verification |
|---|---|---|---|
| 0 | This audit (`IMPLEMENTATION_AUDIT.md`) | **Done (this file)** | Review against brief §2 A–E |
| 1 | Canonical hierarchical parser + Cases A–J tests (`services/ingredient_parser.py`, `tests/unit/test_ingredient_parser.py`) | **In progress on this branch** | `pytest` green; flake8 clean; no chemistry fields populated |
| 2 | `.gitignore` + untrack `__pycache__`; `CHANGELOG.md` entry | With this branch | `git status` clean of `.pyc`; changelog diff |
| 3 | Normalization service (syntactic only, Stage 4) + unit tests | Next | Tests: case/whitespace/punct, INS/E extraction preserved, OCR-artifact flagging; identity-change tests must fail if normalizer alters chemistry |
| 4 | Deterministic entity-resolution skeleton against local alias table (exact → normalized → alias → candidate → unresolved; never promote ambiguous) | Next | Golden-candidate fixtures (not golden-truth assertions) |
| 5 | OCR adapter interface + `ocr_runs` migration (Phase 2 tables) + raw-text preservation tests | Next | Poor/unusable confidence blocks silent analysis |
| 6 | Supabase/local-Postgres wiring + apply migrations 001/002 + DB integration test | Next | Requires `DATABASE_URL_TEST`; blocked until a test DB exists |
| 7 | RDKit chemistry gate (only after verified SMILES exists; mixtures rejected) | Later | Needs Dockerfile/pinning decision (readiness-report risk #3) |
| 8 | Evidence/claims + roles + analysis + compare + grounded explanation | Later, in vertical-slice order (`DEVELOPMENT_GUIDE.md` §9) | Contract tests per `API_SPEC.md` §76 |
| 9 | Next.js frontend scaffold | **Deferred** until slices 1–5 have stable contracts to code against | — |

Out of scope for this branch by design: migrations, DB connection, RDKit install,
frontend scaffold, AI integration, deployment config.

---

## H. Remaining risks / explicit non-claims

- This audit **does not claim** production readiness, OCR accuracy, chemical coverage,
  or deployment test results — none exist yet.
- Parser tests use **synthetic label strings**, not real labels; `LABEL_REGRESSION_DATASET.csv`
  remains `needs_real_label` and is not asserted against.
- No typecheck/lint/build beyond `pytest` + `flake8` + `python -m compileall` — frontend
  gates are N/A (no frontend), `mypy`/`ruff` are not configured in this repo.
- If the "Google AI Studio prototype" referenced by the brief is produced later, a
  second audit pass is required to reconcile it with this canonical pipeline before
  merging any of its logic.

---

*End of audit. Implementation proceeds with Step 1 (canonical parser) on this branch.*
