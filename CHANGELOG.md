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
