# Changelog

All notable changes to LabelLens will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `IMPLEMENTATION_AUDIT.md` — full repository reality audit. Key finding: the
  Vite/React prototype described in the master brief is not present in this
  checkout (`frontend/` holds only empty dirs; no parser/services/UI code exists).
  Audit records framework/runtime/deps, feature status for all major features,
  scan-pipeline trace (health endpoint only), and the prioritized build-out plan.
- Canonical hierarchical ingredient parser
  (`backend/app/services/ingredient_parser.py`, v1.0.0) — single Stage-2
  extraction entry point `parse_label_ingredients()`. Handles `()`/`[]`/`{}`,
  nesting, quoted delimiters, percentages, INS/E identifiers, OCR
  whitespace/newline artefacts, and malformed input without raising.
  Chemistry-free by construction (nodes start `unresolved`/`unverified`).
- Parser regression tests (`backend/app/tests/unit/test_ingredient_parser.py`) —
  brief §17 Cases A–J plus brackets/semicolons, raw-text preservation,
  no-chemistry-invention, ordering, and empty-input cases. 16/16 passing.
- Syntactic normalization layer (Stage 4,
  `backend/app/services/ingredient_normalizer.py`, v1.0.0) — canonical entry
  point `normalize_result()` consuming parser nodes only. Case/whitespace/
  unicode/punctuation canonicalization plus additive-code spacing
  (`INS471` → `INS 471`). OCR typos preserved with `possible_ocr_variation`
  warnings, never silently corrected. Idempotent. Chemistry-free by
  construction (safety regression test asserts no identity/chemistry/
  evidence fields).
- Normalization regression tests
  (`backend/app/tests/unit/test_ingredient_normalizer.py`) — gate items
  1–16 plus alias-stays-text and no-chemistry safety tests. 35/35 passing
  across the full suite.
- Candidate entity resolver (Stage 5,
  `backend/app/services/entity_resolver.py`, v1.0.0) — single canonical
  entry point `resolve_entities()` consuming Stage-4 normalized nodes.
  Provider-independent `EntityRegistry` contract + explicit
  `InMemoryRegistry`; priority exact-identifier → exact-name →
  exact-alias → controlled OCR-near (bounded, flagged) → contextual
  supporting signal → unresolved. Statuses
  `exact_match | candidate | ambiguous | unresolved`; selection only on
  exact hit, never first-of-many; qualitative confidence only; no
  chemistry/verification/RDKit/AI/network. 63/63 passing.
- Stage-6 verification architecture (`STAGE_6_VERIFICATION_ARCHITECTURE.md`,
  architecture-only, no code): verification authority = versioned local
  canonical snapshot + versioned ingestion + optional live refresh
  (Option C); frozen gate V1–V7; state machine with append-only
  transitions; claim-level entity/claim/source separation; conflict,
  freshness, provenance, and failure models; Stage-7 contract.
- Stage-7 verification engine (`backend/app/services/verification/`,
  rules v1.0.0): pure V1–V7 gate, `VerificationSource` ABC,
  read-only `SnapshotAdapter`, unavailable-by-design `ManualAdapter`
  stub, `verify_candidate()` orchestrator with frozen status mapping.
  `snapshots/canonical_v1.json`: 4 PubChem-transcribed records
  (citric acid, sodium benzoate, glycerol, ethanol) with per-field
  provenance, quality over quantity. No live providers, RDKit, AI,
  migrations, or endpoints. 113/113 passing.
- Stage-8 official evidence adapters (internal capability, V1–V7
  untouched): bounded shared HTTP layer, typed evidence model with
  conflict detection, deterministic evidence cache with offline mode,
  read-only PubChem (PUG-REST) and ChEBI (2.0 REST) adapters behind
  the existing `VerificationSource` contract, `CombinedAdapter`
  fan-out, provider-conflict mapping to the existing `conflicted`
  branch. Endpoints verified against official docs + live shapes.
  176/176 passing.
- Stage-9 human review + controlled re-verification (internal
  service layer, V1–V7 untouched): typed review lifecycle with
  append-only audit events, deterministic priority, claim-level
  identity-only approvals, `ManualAdapter` selection registry (never
  source evidence), `reverify_candidate()` routing human selections
  back through the frozen gate with stale-evidence rejection, plus a
  documentation-based PubChem/ChEBI production-readiness audit
  (quotas unknown, no credentials required). 206/206 passing.
- Stage-10 persistence boundary (V1–V7 untouched): additive
  migration `003_verification_review.sql` (claim/evidence/review/
  decision tables, RLS, append-only triggers, idempotent seed repair
  for a pre-existing invalid-UUID bug in `002`), repository
  Protocols with in-memory and Postgres/Supabase implementations,
  deterministic serialization, `backend/.env.example` placeholders.
  Live-validated against real Postgres 18. 247/247 passing.
- Stage-11 authenticated API boundary (V1–V7 untouched): FastAPI
  factory with bearer principals and reviewer role, observation/
  candidate/verification/claim/review endpoints per the spec
  envelopes, identity-only review scope, stale-evidence 409s,
  match-scoped verification IDs, process-scoped review IDs, envelope
  errors, request-ID correlation, OpenAPI error documentation, and a
  service layer + service-scope middleware so Postgres runs one
  connection/transaction per request on the serving event loop.
  289/289 passing with live DB (276 passed + 13 skipped without).
  Documented in `STAGE_11_API.md`; ADR-024.
- Stage-12 production readiness (V1–V7 untouched), three parts and
  **no new HTTP route**:
  - **A — Supabase JWT verification** (`app/api/supabase_jwt.py`,
    `app/api/jwks.py`, `app/api/auth.py`): real signature/issuer/
    audience/expiry/not-before/subject validation against the project
    JWKS document, no decode-without-verify path, asymmetric
    algorithms only (symmetric projects fail closed), a bounded JWKS
    cache (TTL 300 s, min-refresh cooldown 30 s, ≤16 keys, 64 KB cap,
    HTTPS only) that survives key rotation, reviewer authority from
    the operator allowlist `SUPABASE_REVIEWER_SUBJECTS` only,
    rejection of privileged `role` claims so the backend credential
    can never act as a person, one uniform 401 for every failure
    category, fail-closed construction in production (no Supabase
    config, or any `DEV_API_TOKENS` in production → refuse to start,
    never a silent fallback), and principals that carry only trusted
    identity (`human:{subject}` preserved). `PyJWT[crypto]` added.
  - **B — controlled canonical entity registration**
    (`app/services/registration.py`,
    `app/cli/import_canonical_entities.py`): service-role CLI import
    of approved snapshot records only, with an
    `ENTITY_IMPORT_CONFIRM=service-role` interlock and no route.
    Whole-artifact validation before any write, deterministic
    rejection report, all-or-nothing transaction, stable entity
    identity, `ON CONFLICT DO NOTHING` idempotency, entity types and
    mixtures preserved, and full provenance in
    `chemical_entities.metadata`. The resolver registry is projected
    from those rows at startup (`build_registry`), failing safe to an
    empty registry. No new migration: `metadata`,
    `first_verified_at`, and `last_verified_at` already existed.
  - **C — application rate limiting** (`app/services/rate_limit.py`,
    `app/api/limits.py`): a `RateLimiter` protocol plus a bounded
    in-memory fixed-window limiter keyed on the authenticated
    principal (never a client-supplied id or payload field), applied
    to `POST /api/v1/observations`,
    `POST /api/v1/observations/{id}/analyze`, and
    `POST /api/v1/reviews/{id}/decision`. Denial is
    `429 RATE_LIMITED` in the standard envelope with a `Retry-After`
    header; a limiter failure is `503 RATE_LIMITER_UNAVAILABLE`
    (fail closed). Budgets are configuration-driven
    (`RATE_LIMIT_*`), reads are never limited, and the single-process
    scope is documented rather than implied. No new table.
  - Tests: 155 new (JWT 35, rate limiter 24, registration 36,
    Supabase-auth API 18, rate-limit API 17, live registration 18,
    live end-to-end production flow 7). 444/444 passing with live
    Postgres, 406 passed + 38 skipped without; import re-verified on
    a fresh database. Documented in
    `STAGE_12_PRODUCTION_READINESS.md`; ADR-025, ADR-026, ADR-027.
- Stage-13 real-label deterministic vertical slice (V1–V7 untouched):
  audited both dataset CSVs and found zero usable ground truth (30/30
  placeholders, 100/100 unverified seeds; both files byte-unchanged,
  pinned by test), then transcribed four genuinely sourced real
  labels (Coca-Cola OFF OCR record, Listerine + NyQuil FDA DailyMed
  SPL inactive paragraphs, Nivea Creme INCIDecoder INCI list with its
  weaker provenance marked) into draft fixtures with cited sources,
  scope notes, and per-ingredient reviewed expectations. New
  `app/regression/` harness (`LabelInput`, `run_label`, metrics,
  developer-only `run_label_regression` CLI, no endpoint): 50
  ingredients, 4 exact matches, 2 unselected candidates, 44
  unresolved; 4 provisional, 46 unknown, 0 verified, 0 conflicted, 0
  entity-match false positives. Additive service-layer correction
  boundary (`ObservationService.correct` + repository
  `record_correction`, one documented revision, raw immutable,
  latest-normalization-wins, deterministic rerun ids); parser,
  normalizer, resolver, adapters, and registry import untouched.
  Tests: 27 new (19 slice, 3 adversarial, 5 live-Postgres proving
  persisted observations/normalizations/candidates/matches/decisions/
  claims/sources with audit rows intact). 471/471 passing with live
  DB (428 passed + 43 skipped without). Documented in
  `STAGE_13_REAL_LABEL_VERTICAL_SLICE.md`; ADR-028.
- Stage-14 systematic names and verified-path verdict (V1–V7
  untouched): traced the locant defect to the parser (unconditional
  comma-splitting broke `1,2,3` runs; the trailing-code pattern read
  word-final `e`+digits as E-codes) and fixed it syntactically
  (digit-comma-digit never separates; code tags need a token
  boundary), unlocking registered systematic-name aliases with no
  suite regressions. Independently reviewed all four Stage-13
  fixtures (byte-identical transcriptions, scope notes, and
  correction separation confirmed; audit blocks added; everything
  stays draft). Added genuinely sourced identifier-bearing fixture
  RL-14-01 (Frooti, retailer-secondary): `INS 330` resolves exactly
  to citric acid with an honestly unverified decision, pinning the
  frozen V3/V4 dual-agreement rule. The real-label VERIFIED
  criterion is reported NOT MET rather than simulated (no quotable
  English name+code co-printing found; review loop cannot waive
  dual agreement; PubChem/transcript double-counting rejected).
  Tests: 15 new (10 systematic-name unit, 4 regression, 1 live).
  486/486 passing with live DB (442 passed + 44 skipped without);
  regression CLI passes. Documented in
  `STAGE_14_SYSTEMATIC_NAMES_AND_VERIFIED_PATH.md`; ADR-029.
- Stage-15 first real-label VERIFIED path (V1–V7 untouched):
  researched label sources exhaustively (report with rejected
  candidates in `STAGE_15_VERIFIED_LABEL_RESEARCH.md`) and found
  UK SmPC excipient lists, which print `Name (EXXX)`. New draft
  fixture RL-15-01 (Simple Linctus Sugar Free, emc product 4928,
  MA PL 12965/0050): `Glycerol (E422)` and `Sodium Benzoate
  (E211)` verify through the unchanged pipeline with all seven
  gates PASS, verified/HIGH entity-linked claims with evidence,
  persisted decision/claims/sources, and full provenance — no
  waiver, shortcut, or override involved; the three unrelated
  nodes stay unknown. Tests: 14 new (13 verified-path, 1 live
  persistence). 501/501 passing with live DB (456 passed + 45
  skipped without); regression CLI passes. ADR-030.
- Stage-16 deterministic OCR boundary (V1–V7 untouched): typed
  immutable OCRResult plus a provider-independent protocol with a
  deterministic fake (no vendor SDK, secret, or binding); migration
  004 (`ocr_runs` append-only, single-revision `ocr_corrections`,
  003-style RLS); OCRService orchestration reusing the observation
  path (corrected-or-raw text, deterministic run-keyed observation
  ids, warning outcomes instead of crashes); four minimal routes
  (`POST|GET /ocr/runs`, `/correction`, `/analyze`) behind existing
  auth/envelopes and the observation rate-limit budgets. Corrupted
  OCR resolves to nothing or honestly unverified candidates (never
  repaired, never verified); documented human correction restores
  exactly the pre-corruption outcome, including the Stage-15
  VERIFIED cases. Tests: 56 new (32 unit, 12 API, 5 regression, 6
  live, +1 migration). 557/557 passing with live DB (506 passed +
  51 skipped without). Documented in `STAGE_16_OCR_BOUNDARY.md`;
  ADR-031.

### Fixed
- `entity_matches.selected_at` and `claim_sources.retrieved_at`
  serialize as real datetimes (asyncpg binds TIMESTAMPTZ strictly;
  unparseable evidence timestamps become NULL, never a fabricated
  instant).
- Analysis responses projected non-existent resolution keys, so
  `resolution.entity` and `match_status` were always empty; they now
  come from `Resolution.to_dict()`.
- Persisted review events are replayed into the hydrated queue before
  transitions, so decision events no longer reuse a positional event
  id and get deduplicated away (decisions were recorded without an
  audit event).
- `test_seed_repair_present` asserts the seeded source rows by
  identity instead of an exact count, since the service legitimately
  registers adapter provenance sources on demand.

### Fixed
- Parser strips a leading `Ingredients:` label header (per `DATA_PIPELINE.md`
  Stage 2 example) instead of merging it into the first ingredient name.
- Untracked committed `__pycache__/*.pyc` files; added root `.gitignore`.

### Planned Implementation
- Phase 1: Database migrations, seed data, golden dataset verification
- Phase 2: Backend skeleton — FastAPI health and DB connectivity
- Phase 3: Scan and OCR integration
- Phase 4: Ingredient editing and normalization
- Phase 5: Entity matching and chemistry pipeline
- Phase 6: Evidence and analysis pipeline
- Phase 7: Comparison and grounded explanation
- Phase 8: Frontend
- Phase 9: Testing and regression benchmarks
- Phase 10: Production deployment

---

## [0.1.1] — 2026-10-04 — Documentation Completion

### Added
- **ARCHITECTURE.md** — Complete system architecture, data flow, and deployment topology.
- **TEST_STRATEGY.md** — Full test pyramid, QA processes, and regression dataset usage.
- **SECURITY.md** — Threat model, prompt injection defenses, RLS, and security checklist.
- **DECISIONS.md** — 15 key architectural decision records (ADRs).
- **CHANGELOG.md** — This changelog to track future project evolution.
- **CASE_STUDY.md** — Portfolio positioning, methodologies, and technical deep-dives.
- **PRESENTATION.md** — Slide-by-slide final presentation outline and speaker notes.
- **DEMO_SCRIPT.md** — Step-by-step live demonstration script with fallback plans.
- **DEVELOPMENT_GUIDE.md** — Workflow rules, stack setup, and pre-commit checklists for agents.
- **DATA_PIPELINE.md** — Deep technical reference for all 10 stages of the chemistry pipeline.

---

## [0.1.0] — 2026-10-04 — Specification Release

Initial specification and documentation release. No implementation code shipped.
All eight specification artifacts are frozen at v1.0.

### Added

- **PRODUCT_SPEC.md v1.0** — Product definition, MVP scope, user experience design,
  ingredient intelligence model, AI boundaries, free-first constraint, success metrics,
  and portfolio positioning. Frozen.

- **CHEMISTRY_DATA_SPEC.md v1.0** — Scientific data model, entity types, validation
  rules, SMILES rules, confidence model, forbidden behaviors, and AI grounding contract.

- **EVIDENCE_AND_CONFIDENCE_SPEC.md v1.0** — Evidence architecture, claim-level
  provenance, source hierarchy, confidence model, verification gates, conflict handling,
  and audit trail design.

- **DATABASE_SCHEMA.md v1.0** — Full PostgreSQL schema covering the MVP table set,
  entity relationships, integrity constraints, index strategy, null strategy, versioning
  approach, and security model.

- **API_SPEC.md v1.0** — Full FastAPI API contract including endpoint definitions,
  error codes, security checklist, adapter contracts, end-to-end critical path, and
  acceptance criteria.

- **SOURCE_REGISTRY.md v1.0** — Approved source registry documenting 14 authoritative
  sources: PubChem, ChEBI, NIST WebBook, RDKit, FSSAI, Codex GSFA, EU Food Additives
  Database, FDA, CosIng, CDSCO, Open Food Facts, Open Beauty Facts, PubMed, and Primary
  Literature.

- **LABEL_REGRESSION_DATASET.csv v1.0** — 30-row regression dataset scaffold
  (LR-001 through LR-030) covering food, snacks, beverages, cosmetics, personal care,
  household, and other product categories. All rows marked `needs_real_label` pending
  Phase 1 verification.

- **INGREDIENT_GOLDEN_DATA.csv v1.0** — 100-row golden chemistry candidate dataset
  (GOLD-001 through GOLD-100) covering food, cosmetics, personal care, household,
  supplement, and pharma categories. All rows marked `needs_verification` pending
  Phase 1 verification.

---

[Unreleased]: https://github.com/your-org/labellens/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/labellens/releases/tag/v0.1.0
