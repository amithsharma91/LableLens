# LabelLens Test Strategy

**Date:** 2026-10-04  
**Version:** 1.0  
**Status:** Active

---

## Table of Contents

1. [Philosophy](#1-philosophy)
2. [Test Pyramid](#2-test-pyramid)
3. [Unit Tests](#3-unit-tests)
   - 3.1 [Chemistry Unit Tests](#31-chemistry-unit-tests)
   - 3.2 [Evidence & Confidence Unit Tests](#32-evidence--confidence-unit-tests)
   - 3.3 [Normalization Unit Tests](#33-normalization-unit-tests)
   - 3.4 [Entity Matching Unit Tests](#34-entity-matching-unit-tests)
4. [Integration Tests](#4-integration-tests)
   - 4.1 [API Contract Tests](#41-api-contract-tests)
   - 4.2 [Database Integration Tests](#42-database-integration-tests)
5. [End-to-End Tests](#5-end-to-end-tests)
   - 5.1 [Critical Path Flow](#51-critical-path-flow)
   - 5.2 [User Flow Scenarios](#52-user-flow-scenarios)
6. [Regression Dataset](#6-regression-dataset)
7. [Golden Chemistry Dataset](#7-golden-chemistry-dataset)
8. [Performance Benchmarks](#8-performance-benchmarks)
9. [CI Strategy](#9-ci-strategy)
10. [Fixture Management](#10-fixture-management)
11. [Test Data Separation](#11-test-data-separation)
12. [Success Metrics](#12-success-metrics)
13. [Definition of Done](#13-definition-of-done)

---

## 1. Philosophy

LabelLens processes real product labels to extract, normalize, and analyze ingredient data. Errors propagate: a misread ingredient can cause a wrong entity match, which causes a wrong chemistry result, which causes a wrong explanation. The test strategy therefore enforces correctness at every layer before trusting downstream results.

**Core principles:**

- **Test at the right level.** Logic errors are cheapest to catch in unit tests. Contract errors are caught in integration tests. Workflow errors are caught in E2E tests. Do not push unit-level assertions into E2E tests and do not mock away the things integration tests are meant to verify.
- **Ground truth is explicit.** Every test assertion traces to a documented expected value — a golden dataset entry, a spec section, or a recorded fixture. No assertions based on "looks right."
- **Regression before release.** The full label regression dataset (section 6) and golden chemistry dataset (section 7) must pass before any version is declared production-ready.
- **Never declare done without verification.** After any meaningful change, run lint, type checks, unit tests, build, and key E2E flows. A passing CI pipeline is a prerequisite for merge, not a post-merge activity.
- **Fail loudly, fail early.** Ambiguous or conflicted states must be explicitly represented and tested; silent defaults to "verified" or "unknown" without evidence are test failures.

---

## 2. Test Pyramid

```
          ┌─────────────────────────────┐
          │         E2E Tests           │  ~10%
          │  Critical paths, user flows │
          ├─────────────────────────────┤
          │     Integration Tests       │  ~25%
          │  API contracts, DB, OCR     │
          ├─────────────────────────────┤
          │        Unit Tests           │  ~65%
          │  Chemistry, evidence,       │
          │  normalization, matching    │
          └─────────────────────────────┘
```

**Rationale for proportions:**

- Unit tests are fast, isolated, and cover the combinatorially large space of chemistry inputs, evidence configurations, and normalization edge cases.
- Integration tests verify that the API contracts defined in `API_SPEC.md` are honored and that the database schema handles real data correctly.
- E2E tests cover the critical scan-to-result path and the most important user journeys. They are expensive (real OCR provider calls or recorded VCR cassettes) and kept narrow.

**Test isolation requirements:**

- Unit tests: no network, no database, no filesystem beyond fixtures.
- Integration tests: test database only (never production); external providers stubbed via recorded cassettes or a controlled test double.
- E2E tests: dedicated test environment with seeded fixtures; no shared state with production.

---

## 3. Unit Tests

### 3.1 Chemistry Unit Tests

Chemistry unit tests validate structure parsing, formula derivation, molecular weight calculation, and the resolution of entity identity from the golden dataset (section 7). They must not call external chemistry APIs; all expected values are pre-computed and stored in the golden dataset.

#### 3.1.1 Valid Structure Tests

Each case provides a SMILES or InChI string and asserts exact formula, molecular weight (within ±0.01 Da), and canonical SMILES round-trip.

| Category | Example inputs | Key assertions |
|---|---|---|
| Simple organic molecules | ethanol, acetic acid, glycerol | formula, MW, canonical SMILES |
| Salts | sodium chloride, potassium sorbate, magnesium stearate | component formulas, charge balance |
| Stereochemical examples | L-ascorbic acid, D-glucose, (R)-linalool | stereo flag preserved, InChI layer correct |
| Multiple functional groups | citric acid, EDTA, retinol | all functional groups detected |

#### 3.1.2 Invalid and Ambiguous Input Tests

These cases assert that the system returns a structured validation failure, never a silently incorrect result.

| Input type | Example | Expected behavior |
|---|---|---|
| OCR typo in name | "sodlum benzoate" | `resolution_status: no_match` or `ambiguous`; no silent best-guess |
| Partial name | "vitamin c" (no disambiguation) | returns candidate list with confidence scores |
| Abbreviation | "PEG-40" | recognized as polymer class; `representation_type: polymer` |
| Unknown trade name | "Naticide®" | `resolution_status: no_match`; trade name recorded |
| Incorrect SMILES | malformed bracket atom | `validation_failure` with parse error detail |
| Empty string | `""` | `validation_failure: empty_input` |

#### 3.1.3 Non-Single-Molecule Entity Tests

Entities that cannot be represented as a single structure must be classified correctly and must not receive a molecular weight or canonical SMILES.

| Entity type | Example | Expected classification |
|---|---|---|
| Mixture | "fragrance" | `representation_type: mixture`; no structure |
| Natural complex | "shea butter" | `representation_type: natural_complex`; no structure |
| Polymer | "carbomer 940" | `representation_type: polymer`; no MW |
| Formulation | "mineral oil (and) lanolin" | `representation_type: formulation`; no structure |

#### 3.1.4 Identifier Collision Tests

When two entities have similar names or identifiers, the resolver must distinguish them correctly.

| Collision type | Pair | Expected disambiguation |
|---|---|---|
| Similar names | "niacinamide" vs "nicotinic acid" | resolved to distinct CAS/InChI |
| Parent vs salt | "retinol" vs "retinyl palmitate" | distinct entities; parent relationship recorded |
| Isomers | "tocopherol" (α vs γ) | stereo/positional isomer flag; not collapsed |
| Hydrate vs non-hydrate | "citric acid" vs "citric acid monohydrate" | distinct MW; hydrate flag |

### 3.2 Evidence & Confidence Unit Tests

These tests exercise the evidence aggregation logic defined in `EVIDENCE_AND_CONFIDENCE_SPEC.md` (sections 46–47). Each test provides a set of source records and asserts the resulting confidence level and verification status.

#### 3.2.1 Correct Evidence Tests

- A claim backed by a verified primary source resolves to `confidence: verified`.
- The resolved claim's `source_id` references the input source record exactly.
- No additional sources are fabricated.

#### 3.2.2 Weak Evidence Tests

- A claim backed only by a weak-confidence source resolves to `confidence: unverified` (not `verified`).
- Promoting a weak-source claim to `verified` is a test failure.

#### 3.2.3 Conflict Tests

- Two sources making mutually exclusive claims about the same property produce `confidence: conflicted`.
- The conflict record includes references to both source IDs.
- No conflict collapses silently to either value.

#### 3.2.4 Missing Source Tests

- A claim with no attached source resolves to `confidence: unknown`.
- Generating a `verified` claim without a source reference is a test failure.

#### 3.2.5 Expired / Dynamic Information Tests

- A regulatory claim with an expiry date in the past triggers `re_verification_required: true`.
- The system does not serve the stale claim as current without flagging staleness.

#### 3.2.6 Computed Claim Tests

- A claim derived by software (e.g., molecular weight calculated from SMILES) records: method name, software version, input value, and output value.
- Missing any provenance field is a test failure.

#### 3.2.7 AI Hallucination Guard Tests

- An explanation text containing a formula that does not match the verified formula for that entity fails validation.
- An explanation referencing a name that does not match the canonical or alias list fails validation.
- An explanation asserting a role not present in the entity's approved role list fails validation.
- An explanation citing a source ID that does not exist in the evidence store fails validation.
- An explanation asserting the existence of a structure field for a mixture-class entity fails validation.

### 3.3 Normalization Unit Tests

Normalization converts raw OCR text into a structured ingredient list. Unit tests cover:

| Case | Input | Expected output |
|---|---|---|
| Comma-separated list | `"water, glycerin, niacinamide"` | three distinct ingredient tokens |
| Parenthetical sub-ingredients | `"tocopherols (alpha, gamma)"` | parent + two sub-ingredients |
| INCI-style capitalization | `"AQUA (WATER)"` | normalized to canonical lowercase with alias |
| Trailing punctuation / noise | `"water."`, `"glycerin,"` | punctuation stripped |
| Percentage annotations | `"salicylic acid 2%"` | ingredient + concentration extracted separately |
| Multilingual label | mixed English/French INCI names | both languages normalized to same canonical |
| OCR artifact characters | `"w@ter"`, `"glycer1n"` | flagged as `ocr_suspect: true`; not silently normalized |

### 3.4 Entity Matching Unit Tests

Entity matching resolves a normalized ingredient token to a known entity in the database. Tests use the golden chemistry dataset (section 7) as the source of truth.

| Case | Input | Expected result |
|---|---|---|
| Exact canonical name | `"glycerol"` | `resolution_status: verified`; correct entity ID |
| Known alias | `"glycerin"` (alias for glycerol) | `resolution_status: verified`; same entity ID |
| Known abbreviation | `"PEG-200"` | `resolution_status: verified`; polymer class entity |
| Ambiguous token | `"vitamin e"` | `resolution_status: ambiguous`; candidate list returned |
| Unknown token | `"unicorn extract"` | `resolution_status: no_match` |
| CAS number lookup | `"64-17-5"` | resolves to ethanol |
| INCI name lookup | `"AQUA"` | resolves to water |

Role classification is tested separately:

| Ingredient | Expected primary role | Expected secondary roles (if any) |
|---|---|---|
| glycerol | humectant | solvent |
| sodium benzoate | preservative | — |
| citric acid | pH adjuster | chelating agent |
| niacinamide | skin-conditioning agent | — |

---

## 4. Integration Tests

### 4.1 API Contract Tests

API contract tests verify that every endpoint defined in `API_SPEC.md` returns the correct HTTP status codes, response shapes, and error structures. External dependencies (OCR provider, chemistry APIs) are replaced with recorded cassettes or deterministic test doubles that return fixture data.

#### 4.1.1 Scan Endpoints

| Scenario | Request | Expected status | Key assertions |
|---|---|---|---|
| Valid image upload | POST `/scans` with valid JPEG | 201 | `scan_id` present; `status: created` |
| Invalid file type | POST `/scans` with `.exe` | 415 | error code `unsupported_media_type` |
| Malformed multipart | POST `/scans` with no file part | 422 | validation error detail |
| Oversized file | POST `/scans` exceeding size limit | 413 | error code `payload_too_large` |
| Duplicate upload (idempotency key) | POST `/scans` with same key twice | 200 on second | returns existing scan, not new record |

#### 4.1.2 OCR Endpoints

| Scenario | Request | Expected status | Key assertions |
|---|---|---|---|
| Valid scan → OCR | POST `/scans/{id}/ocr` | 202 | `job_id` present; `status: queued` |
| Poll completed job | GET `/api/v1/scans/{scan_id}/ocr` after completion | 200 | `status: complete`; `raw_text` present |
| Repeated OCR request | POST `/ocr` on already-processed scan | 200 | idempotent; returns existing result |
| Provider failure | OCR provider returns 503 | 200 with structured error | `status: failed`; `error.provider` set |

#### 4.1.3 Correction Endpoints

| Scenario | Expected behavior |
|---|---|
| PATCH correction | `original_text` unchanged; `corrected_text` recorded; `correction_source: human` |
| Re-analysis after correction | triggers new normalization pass using corrected text |
| Correction on non-existent scan | 404 |

#### 4.1.4 Entity Matching Endpoints

| Scenario | Expected status | Key assertions |
|---|---|---|
| Exact known ingredient | 200 | `resolution_status: verified`; entity ID matches golden dataset |
| Ambiguous ingredient | 200 | `resolution_status: ambiguous`; `candidates` array non-empty |
| Unknown ingredient | 200 | `resolution_status: no_match`; no entity ID |

#### 4.1.5 Chemistry Endpoints

| Scenario | Expected status | Key assertions |
|---|---|---|
| Valid structure (SMILES) | 200 | formula and MW present; matches golden dataset |
| Invalid SMILES | 422 | `error.type: invalid_structure` |
| Mixture entity | 200 | `representation_type: mixture`; no MW field |
| Polymer entity | 200 | `representation_type: polymer`; no canonical SMILES |

#### 4.1.6 Evidence Endpoints

| Scenario | Expected status | Key assertions |
|---|---|---|
| Verified claim | 200 | `confidence: verified`; `source` object present |
| Missing source | 200 | `confidence: unknown`; no source object |
| Conflicting sources | 200 | `confidence: conflicted`; `conflict_refs` array present |

#### 4.1.7 Comparison Endpoints

| Scenario | Expected status | Key assertions |
|---|---|---|
| Two valid scans | POST `/comparisons` → 201 | comparison ID; diff structure present |
| Ambiguous ingredients in either scan | 201 | ambiguity preserved in diff; not resolved silently |
| One scan ID invalid | 422 | clear error referencing invalid ID |

### 4.2 Database Integration Tests

Database integration tests run against the test database only (see section 11). They verify that the schema handles real data correctly and that repository layer operations produce correct SQL behavior.

**Coverage areas:**

- **Referential integrity:** ingredient observations reference valid scan records; evidence records reference valid entity and source records; deleting a scan cascades correctly.
- **Uniqueness constraints:** duplicate canonical names at the entity level are rejected; duplicate CAS numbers are rejected.
- **Index correctness:** queries used in hot paths (ingredient name lookup, entity alias search, scan status filter) use the expected index and do not perform full table scans (verified via `EXPLAIN`).
- **JSON/JSONB fields:** structured fields (aliases, identifiers, roles) serialize and deserialize correctly; partial JSON updates do not corrupt adjacent fields.
- **Pagination:** `LIMIT`/`OFFSET` and cursor-based pagination return consistent results under concurrent inserts.
- **Migration correctness:** each migration can be applied forward and rolled back cleanly on an empty database and on a seeded test database.

---

## 5. End-to-End Tests

E2E tests exercise the full system from HTTP request to final response using the real application stack against a seeded test environment. They use VCR cassettes for OCR provider calls to avoid non-determinism and external cost.

### 5.1 Critical Path Flow

The following sequence, derived from `API_SPEC.md` section 77, constitutes the critical path and must pass for every release:

```
1.  POST   /scans                    → scan_id (201)
2.  POST   /scans/{scan_id}/ocr      → job_id (202)
3.  GET    /api/v1/scans/{scan_id}/ocr             → status: complete, raw_text (200)
4.  POST   /scans/{scan_id}/ingredients/extract  → ingredient_list (200)
5.  PATCH  /scans/{scan_id}/observations/{obs_id} → correction recorded (200)
6.  POST   /api/v1/ingredient-observations/{id}/normalize    → normalized tokens (200)
7.  POST   /api/v1/ingredient-observations/{id}/match        → entity matches (200)
8.  POST   /scans/{scan_id}/analyze  → analysis_id (202)
9.  GET    /analyses/{analysis_id}   → status: complete (200)
10. GET    /analyses/{analysis_id}/items/{item_id} → item detail (200)
11. GET    /api/v1/ingredients/{entity_id}/chemistry → chemistry (200)
12. GET    /api/v1/ingredients/{entity_id}/evidence  → evidence (200)
13. POST   /comparisons              → comparison_id (201)
14. GET    /comparisons/{comparison_id} → diff (200)
```

**Assertions at each step:**

- HTTP status matches the spec.
- Response body matches the documented schema (validated against the OpenAPI contract).
- IDs from earlier steps are correctly threaded into later steps.
- No step silently succeeds with an empty or null payload where a real value is required.

### 5.2 User Flow Scenarios

These scenarios cover divergent paths not exercised by the critical path alone.

#### Scenario A: Poor-quality label with OCR correction

1. Upload poor-quality label fixture (`poor_quality_label.jpg`).
2. OCR returns text with known OCR traps (from regression dataset, section 6).
3. User submits a correction via PATCH.
4. Re-analysis is triggered; corrected text is used, not original.
5. Assert: final ingredient list matches expected post-correction list, not the raw OCR list.

#### Scenario B: Ambiguous ingredient preserved through comparison

1. Upload two product fixtures that share an ambiguous ingredient token.
2. Both scans complete analysis with `resolution_status: ambiguous`.
3. POST comparison.
4. Assert: comparison diff correctly marks the shared ingredient as ambiguous; it is not silently resolved to a specific entity.

#### Scenario C: Mixture and polymer ingredients

1. Upload a cosmetics label containing "fragrance" and "carbomer 940".
2. Analysis completes.
3. Assert: "fragrance" has `representation_type: mixture`, no structure, no MW.
4. Assert: "carbomer 940" has `representation_type: polymer`, no canonical SMILES.
5. Assert: neither triggers a `validation_failure` (correct: these are valid non-single-molecule entities).

#### Scenario D: Evidence conflict surfaced to user

1. Seed two conflicting evidence records for the same claim on a known ingredient.
2. Run analysis on a label containing that ingredient.
3. Assert: evidence endpoint returns `confidence: conflicted`; both source refs are present.
4. Assert: the explanation for that ingredient does not assert a definitive value for the conflicted claim.

---

## 6. Regression Dataset

The regression dataset is the ground-truth corpus for label processing accuracy. It is stored under `tests/fixtures/labels/` and is never used in production.

### 6.1 Dataset Composition

The dataset scales in defined phases:

| Phase | Total labels | New in phase |
|---|---|---|
| Initial | 30 | 30 |
| Phase 2 | 50 | 20 |
| Phase 3 | 100 | 50 |
| Phase 4 | 250+ | 150+ |

**Category breakdown for initial 30 labels:**

| Category | Count |
|---|---|
| Food, snacks, and beverages | 10 |
| Cosmetics | 5 |
| Personal care | 5 |
| Household products | 5 |
| Other (supplements, pharma OTC, pet food) | 5 |

### 6.2 Per-Label Record Structure

Each label entry in the dataset contains:

```yaml
label_id: "label_001"
category: food
original_image: "tests/fixtures/labels/label_001.jpg"
expected_raw_text: |
  INGREDIENTS: Water, Sugar, Citric Acid, Natural Flavors...
expected_normalized_ingredients:
  - token: "water"
    canonical: "water"
    entity_id: "ent_water"
  - token: "sugar"
    canonical: "sucrose"
    entity_id: "ent_sucrose"
expected_entity_matches:
  - token: "citric acid"
    resolution_status: verified
    entity_id: "ent_citric_acid"
    confidence: verified
expected_roles:
  - entity_id: "ent_citric_acid"
    primary_role: "pH adjuster"
known_ocr_traps:
  - pattern: "Nat. Fla\/ors"
    expected_correction: "Natural Flavors"
known_ambiguous_cases:
  - token: "natural flavors"
    reason: "mixture; no single entity"
    expected_resolution_status: ambiguous
```

### 6.3 Regression Test Execution

- Regression tests are parameterized over all entries in the dataset.
- Each test: load image → run OCR (via cassette) → normalize → match → compare to `expected_*` fields.
- **OCR accuracy gate:** ≥95% of ingredient tokens correctly extracted (exact or fuzzy match within edit distance 1).
- **Entity match gate:** false entity-match rate ≤5%; unknown entity rate ≤10% (for ingredients present in the golden dataset).
- Regression tests run in CI on every PR targeting `main`. Full 250+ dataset run is triggered nightly and on release tags.

### 6.4 Adding Labels to the Dataset

1. Capture real label image (minimum 150 DPI, JPEG or PNG).
2. Run OCR manually; record raw output as `expected_raw_text`.
3. Manually verify normalized ingredients against INCI or product documentation.
4. Resolve entity matches against the golden dataset; record IDs.
5. Document all OCR traps and ambiguous cases found.
6. Submit label record alongside the image in the same PR.

---

## 7. Golden Chemistry Dataset

The golden dataset contains 100 high-importance ingredient entities used as the canonical reference for chemistry, entity resolution, and explanation tests. It is stored at `tests/fixtures/golden_chemistry.yaml`.

### 7.1 Entity Record Structure

```yaml
entity_id: "ent_glycerol"
canonical_name: "glycerol"
aliases:
  - "glycerin"
  - "glycerine"
  - "propane-1,2,3-triol"
identifiers:
  cas: "56-81-5"
  inchi: "InChI=1S/C3H8O3/c4-1-3(6)2-5/h3-6H,1-2H2"
  inchikey: "PEDCQBHIVMGVHV-UHFFFAOYSA-N"
  smiles: "OCC(O)CO"
formula: "C3H8O3"
molecular_weight: 92.09
representation_type: single_molecule
domain_roles:
  - role: humectant
    domain: cosmetics
    confidence: verified
    source_id: "src_inci_2024"
  - role: solvent
    domain: food
    confidence: verified
    source_id: "src_efsa_2023"
evidence:
  - source_id: "src_inci_2024"
    claim: "role:humectant"
    confidence: verified
  - source_id: "src_pubchem_cid_753"
    claim: "formula:C3H8O3"
    confidence: verified
confidence: verified
```

### 7.2 Dataset Use in Tests

| Test type | How the golden dataset is used |
|---|---|
| Entity resolution unit tests | Input aliases/CAS → assert correct `entity_id` |
| Chemistry unit tests | Input SMILES → assert formula/MW match golden record |
| Role classification tests | Input entity ID → assert roles match golden record |
| Evidence unit tests | Seed evidence records from golden → assert confidence |
| Explanation verification | Assert explanation text does not contradict golden record |
| UI regression tests | Render entity cards → assert displayed values match golden |
| Demonstration / onboarding | Seed database with golden 100 for demo environment |

### 7.3 Golden Dataset Maintenance

- The golden dataset is immutable in feature branches; changes require a dedicated `chore/golden-dataset` PR with reviewer sign-off.
- Any new entity added must have: all identifier fields, at least one verified evidence record, at least one domain role.
- Entities with `confidence: unverified` are permitted only in the "known-ambiguous" annex, not the main 100.
- Molecular weight values must be computed from the SMILES/InChI and rounded to two decimal places; hand-entered MW values are not accepted without a cross-check.

---

## 8. Performance Benchmarks

Performance benchmarks are not part of the unit or integration test suites; they run separately on a representative hardware target (or CI performance runner) and produce a report artifact.

### 8.1 Target Thresholds

| Operation | p50 target | p95 target | p99 target |
|---|---|---|---|
| POST `/scans` (file upload, no OCR) | <200 ms | <500 ms | <1 s |
| GET `/api/v1/scans/{scan_id}/ocr` (completed scan) | <100 ms | <250 ms | <500 ms |
| POST `/api/v1/ingredient-observations/{id}/match` (single ingredient) | <50 ms | <150 ms | <300 ms |
| POST `/api/v1/ingredient-observations/{id}/match` (20-ingredient list) | <200 ms | <500 ms | <1 s |
| GET `/analyses/{id}` (full analysis, 20 ingredients) | <300 ms | <800 ms | <1.5 s |
| GET `/api/v1/ingredients/{entity_id}/chemistry` | <100 ms | <300 ms | <600 ms |
| POST `/comparisons` (two 20-ingredient scans) | <500 ms | <1.5 s | <3 s |

### 8.2 Benchmark Methodology

- Benchmarks use the production code path with the test database seeded with 1,000 scans and 10,000 ingredient observations.
- OCR provider calls are excluded from API latency benchmarks (provider latency is measured separately and treated as an external SLO).
- Load test: 50 concurrent users, 5-minute sustained ramp, using the critical path flow (section 5.1).
- Throughput floor: the system must sustain ≥20 complete scan-to-result flows per minute under the 50-user load without degradation beyond p95 targets.
- Benchmark results are stored as CI artifacts and compared against the previous release baseline; a regression ≥20% at p95 blocks merge.

### 8.3 Scan-to-Result Completion Time

The end-to-end scan-to-result time (POST scan → GET final analysis) is tracked as a product metric. Target: ≤30 seconds at p95 for a 20-ingredient label including real OCR provider time. This is monitored in production via tracing, not enforced in the benchmark suite.

---

## 9. CI Strategy

### 9.1 Pipeline Stages

Every PR targeting `main` triggers the following stages in order:

```
Stage 1: Static Analysis (parallel)
  ├── Lint (ESLint / Ruff / language-specific linter)
  ├── Type check (tsc --noEmit / mypy / pyright)
  └── Dependency audit (npm audit / pip-audit; fail on HIGH+)

Stage 2: Unit Tests
  └── All unit tests (chemistry, evidence, normalization, matching)
      Coverage gate: ≥80% line coverage on changed files

Stage 3: Integration Tests
  ├── API contract tests (test DB, cassettes)
  └── Database integration tests (test DB, migrations applied fresh)

Stage 4: Build
  └── Production build (no type errors, no lint errors)

Stage 5: E2E Tests (critical path only on PR)
  └── Critical path flow (section 5.1) + Scenarios A–D

Stage 6: Regression Dataset (nightly + release tags only)
  └── Full label regression dataset (all phases accumulated)
```

### 9.2 Branch Rules

- **feature/** and **fix/** branches: Stages 1–5 must pass before merge.
- **main**: protected; no direct commits. All merges via PR with at least one reviewer approval.
- **release/** tags: full pipeline including Stage 6 plus performance benchmarks. Release is blocked if Stage 6 fails or benchmarks regress ≥20% at p95.

### 9.3 Test Parallelism

- Unit tests are parallelized across CPU cores (no shared state; each test is fully isolated).
- Integration tests run with a per-worker test database (created fresh per CI run, destroyed on success).
- E2E tests run sequentially to avoid state collisions; the test environment is reset between scenarios.

### 9.4 Failure Handling

- Any stage failure blocks all subsequent stages.
- Flaky tests must be fixed or quarantined within 2 business days of first detection. Quarantined tests are tracked in `tests/QUARANTINE.md` with owner and deadline.
- No test may be permanently disabled without removing the feature it covers or replacing it with an equivalent test.

### 9.5 Coverage Requirements

| Module | Minimum line coverage |
|---|---|
| Chemistry logic | 85% |
| Evidence aggregation | 85% |
| Normalization | 80% |
| Entity matching | 80% |
| API route handlers | 75% |
| Database repositories | 75% |
| Overall project | 78% |

Coverage is measured on the unit + integration suite combined. E2E coverage is not counted toward the gate.

---

## 10. Fixture Management

### 10.1 Fixture Types

| Type | Location | Purpose |
|---|---|---|
| Label images | `tests/fixtures/labels/` | Input images for OCR and regression tests |
| Label records | `tests/fixtures/labels/*.yaml` | Ground-truth metadata per label |
| Golden chemistry dataset | `tests/fixtures/golden_chemistry.yaml` | 100-entity canonical reference |
| API response cassettes | `tests/fixtures/cassettes/` | Recorded OCR provider responses |
| Database seed files | `tests/fixtures/seeds/` | SQL or seed scripts for integration/E2E |
| API fixture payloads | `tests/fixtures/api/` | Named request/response pairs per spec section |

### 10.2 API Fixture Payloads

The following named fixtures correspond to `API_SPEC.md` section 96 and are used across contract and E2E tests:

| Fixture name | Description |
|---|---|
| `valid_label` | Clear, high-quality food label; all ingredients resolvable |
| `poor_quality_label` | Low-resolution image; known OCR errors present |
| `ocr_typo_label` | Deliberate OCR typos matching known traps in regression dataset |
| `ambiguous_ingredient` | Label containing "vitamin e" and "fragrance" |
| `unknown_ingredient` | Label containing a made-up trade name not in golden dataset |
| `verified_chemical` | Label containing an ingredient with full golden dataset entry |
| `mixture_ingredient` | Label where one ingredient is a mixture (e.g., "parfum") |
| `polymer_ingredient` | Label containing a polymer (e.g., "carbomer") |
| `trade_name_ingredient` | Label containing a cosmetics trade name not in INCI |
| `conflicting_evidence` | Seeded evidence records with conflicting claims |
| `missing_source` | Claim record with no attached source |
| `valid_smiles` | Request body with a valid, parseable SMILES string |
| `invalid_smiles` | Request body with a structurally invalid SMILES string |
| `two_comparable_products` | Pair of scan IDs with overlapping ingredients for comparison |
| `two_products_ambiguous_overlap` | Pair of scans where the shared ingredient is ambiguous |

### 10.3 Cassette Management

- OCR cassettes are recorded once against the real provider in a dedicated recording session.
- Cassettes are committed to the repository. Re-recording requires explicit opt-in (`RECORD_CASSETTES=true` env flag).
- Cassette files must not contain API keys or PII; the recording pipeline redacts authorization headers before commit.
- When the OCR provider's API changes, cassettes must be re-recorded and reviewed in a dedicated PR.

### 10.4 Fixture Governance

- Fixtures are read-only at test runtime. Tests that mutate state operate on database transactions that are rolled back, or on isolated per-test DB instances.
- Binary fixtures (label images) are stored in Git LFS. The repository must not accumulate untracked binary test artifacts.
- Fixture additions for new regression labels follow the intake process in section 6.4.

---

## 11. Test Data Separation

Test data must never reach the production database or production object storage. The following controls enforce separation:

### 11.1 Environment Configuration

- The test environment uses a distinct database connection string, set via `DATABASE_URL_TEST`. CI injects this; it is never the same value as `DATABASE_URL`.
- Object storage for test label images uses a dedicated test bucket (`labellens-test-*`). The application verifies at startup in non-production environments that the configured bucket name contains `test`.
- The golden dataset and regression dataset are loaded only when `NODE_ENV=test` (or the language-equivalent flag) is active.

### 11.2 Database Isolation

| Test type | Database strategy |
|---|---|
| Unit tests | No database; repositories are mocked |
| Integration tests | Dedicated `labellens_test` database; migrations applied fresh per CI run |
| E2E tests | `labellens_e2e` database; seeded from fixtures before each scenario, reset after |
| Performance benchmarks | `labellens_perf` database; seeded with synthetic load data; never reset mid-run |

### 11.3 No Production Data in Tests

- Real user data (real product images, real ingredient scans) must not be used as test fixtures without explicit anonymization and user consent documentation.
- Label images in the regression dataset are sourced from publicly available product packaging or synthetic replicas.
- If a real-world label is found to contain PII (e.g., a name or address printed on a custom label), it must be removed from the dataset and its cassettes deleted before the next release.

### 11.4 Secrets

- No API keys, database credentials, or provider tokens are hardcoded in test files or fixtures.
- Tests that require provider credentials read them from environment variables only.
- Cassette files are the standard way to avoid requiring live credentials in CI (see section 10.3).

---

## 12. Success Metrics

The following metrics, derived from `PRODUCT_SPEC.md` section 17, define what "good" looks like for the test suite and the product under test.

| Metric | Target | Measurement method |
|---|---|---|
| OCR ingredient extraction accuracy | ≥95% token-level accuracy | Regression dataset (section 6) |
| False entity-match rate | ≤5% | Regression dataset, entity match assertions |
| Unknown entity rate (for golden-dataset ingredients) | ≤10% | Regression dataset |
| Role-classification accuracy | ≥90% | Golden dataset role assertions |
| Scan-to-result completion rate | ≥99% of initiated scans reach `complete` | E2E critical path + monitoring |
| OCR correction burden | ≤20% of scans require human correction | Regression dataset OCR trap count |
| Compare-flow completion rate | ≥99% | E2E Scenario B + monitoring |
| API error rate (5xx) | <0.5% of requests | Integration test error injection + monitoring |
| Automated test suite pass rate | 100% required to merge | CI pipeline |
| Build pass rate | 100% required to merge | CI pipeline |

---

## 13. Definition of Done

A feature, fix, or release is not done until all of the following are true:

- [ ] Lint passes with zero errors.
- [ ] Type checks pass with zero errors.
- [ ] All unit tests pass; coverage gates met (section 9.5).
- [ ] All integration tests pass against a freshly migrated test database.
- [ ] The production build compiles without errors.
- [ ] E2E critical path (section 5.1) and all four scenarios (section 5.2) pass.
- [ ] Any new endpoints or behaviors are covered by at least one contract test.
- [ ] Any new ingredient entities are added to the golden dataset per section 7.3 if they appear in the regression dataset.
- [ ] Any new regression labels follow the intake process in section 6.4.
- [ ] No quarantined tests have been marked permanently disabled without replacement.
- [ ] Performance benchmarks do not regress ≥20% at p95 (required for release tags only).
- [ ] Full regression dataset passes (required for release tags only).
- [ ] No test data is present in or connected to the production environment.

### 6.5 Stage-13 Real-Label Slice (implemented 2026-10-05)

The `LABEL_REGRESSION_DATASET.csv` rows are all still
`needs_real_label` placeholders and the golden CSV is still
`needs_verification` seed data, so neither can ground a test. The
first executable slice lives separately and does not pretend
otherwise:

- Fixtures: `backend/app/regression/fixtures/real_labels/`
  (`RL-13-01` Coca-Cola OFF OCR, `RL-13-02` Listerine DailyMed SPL,
  `RL-13-03` Nivea Creme INCIDecoder transcription,
  `RL-13-04` NyQuil DailyMed SPL), each with cited source,
  retrieval date, scope note, per-ingredient expectations, and
  `review_status: "draft"`.
- Runner: `backend/app/regression/runner.py` (`run_label`) over the
  unchanged service layer; `backend/app/cli/run_label_regression.py`
  prints metrics and exits non-zero on mismatch (no HTTP endpoint).
- Tests: `backend/app/tests/regression/` — slice expectations (19),
  adversarial fixture handling (3), live-Postgres persistence (5).
- Governance: a test asserts both CSVs still hold zero verified
  rows, so placeholders can never be silently promoted to truth.

Current slice metrics (50 ingredients): 4 exact matches, 2
unselected candidates, 44 unresolved; 4 provisional, 46 unknown, 0
verified, 0 conflicted, 0 entity-match false positives. Bare
registered names verify only to provisional (single source cannot
corroborate itself); the `glycerin` synonym gap, generic terms
(alcohol, flavor, parfum), color additives, and all unregistered
substances stay unresolved. The §12 gates are not applied to this
4-label slice (it is a pipeline proof, not a market sample); the
false-positive count is asserted at exactly 0.

### Stage-14 extension (2026-10-05)

- Added `RL-14-01` (Frooti Mango Drink 1L, retailer-secondary
  transcription, draft): an identifier-bearing English label. Its
  `Acidity Regulator (INS 330)` node resolves `exact_match` to
  citric acid with an honestly `unverified` decision, pinning the
  frozen V3/V4 name+identifier dual-agreement rule; nested INS
  children stay in the parse tree; the retailer's own unbalanced
  parenthesis is preserved literally.
- Systematic-name syntax fix (parser only): locants and
  hyphenation survive intact, registered systematic-name aliases
  now resolve, unregistered ones stay unresolved.
- Current slice metrics (57 ingredients): 5 exact matches, 2
  candidates, 50 unresolved; 4 provisional, 1 unverified, 52
  unknown, 0 verified, 0 conflicted, 0 false positives. The
  real-label VERIFIED criterion is documented as not met
  (`STAGE_14_SYSTEMATIC_NAMES_AND_VERIFIED_PATH.md` §4) rather
  than simulated.
