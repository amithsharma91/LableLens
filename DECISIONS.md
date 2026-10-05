# LabelLens — Architectural Decision Records

> Last updated: 2026-10-04  
> All decisions recorded here reflect the specification phase. Status: **Accepted** unless noted.

---

## ADR-001 — PostgreSQL via Supabase as Primary Database

**Status:** Accepted  
**Date:** 2026-10-04

### Context

LabelLens stores structured provenance-aware data: ingredients, claims, sources, confidence scores, and relationships between them. These are relational by nature — a claim links to one or more sources, a source has an authority class, an ingredient has multiple evidence records. We need row-level access control for multi-tenant use and the flexibility to store semi-structured metadata without sacrificing queryability of important fields.

### Decision

Use PostgreSQL hosted on Supabase as the primary database.

### Rationale

- Relational integrity enforces correct claim-source links that a document store cannot guarantee.
- Supabase's free tier covers MVP scale with no upfront cost (aligns with ADR-011).
- Row-Level Security (RLS) is built into PostgreSQL and exposed directly by Supabase, enabling per-user data isolation without application-layer enforcement.
- JSONB columns provide flexibility for metadata fields that vary by ingredient type while keeping structured fields (CAS, formula, confidence scores) properly indexed and queryable.
- Supabase exposes a PostgREST auto-API and Auth, reducing boilerplate infrastructure.

### Consequences

- Schema migrations must be managed carefully as the data model evolves.
- All agents and services must connect through Supabase credentials; local SQLite shortcuts are not permitted.
- JSONB fields must not be used as an escape hatch for data that should have its own column.

**Rejected alternatives:**
- Pure document store (MongoDB, Firestore): no relational integrity for claim-source links; querying across relationships becomes application-level logic.
- SQLite: single-file design is not suitable for multi-service deployment or concurrent writes from separate backend workers.

---

## ADR-002 — FastAPI + Python as Backend

**Status:** Accepted  
**Date:** 2026-10-04

### Context

The backend must orchestrate chemistry validation (RDKit), OCR result normalization, source registry lookups, AI model calls, and evidence assembly. Language and framework choice directly constrains which libraries are available natively.

### Decision

Use FastAPI with Python as the backend framework.

### Rationale

- RDKit — the authoritative cheminformatics library — is Python-native. Using Python eliminates the need for a subprocess bridge or external microservice just for chemistry operations.
- FastAPI's async support handles concurrent I/O (database queries, AI API calls, external source lookups) efficiently.
- Pydantic models provide typed request/response validation at the boundary, catching malformed data before it enters the system.
- FastAPI auto-generates OpenAPI documentation, which serves as the authoritative API contract consumed by the frontend and any future integrations.
- Python's data science ecosystem (NumPy, Pandas, PIL) is available if needed for future image preprocessing or analysis stages.

### Consequences

- The backend is a Python service; all backend contributors must be comfortable with Python async patterns.
- Dependency management (RDKit, Pydantic v2, SQLAlchemy) requires a pinned `requirements.txt` or `pyproject.toml` to ensure reproducibility.
- OpenAPI output from FastAPI must be kept in sync with the frontend's typed API client.

**Rejected alternatives:**
- Node.js / TypeScript backend: no native RDKit support. A subprocess or HTTP bridge to a Python chemistry service would introduce latency, deployment complexity, and a second language surface.

---

## ADR-003 — Next.js + TypeScript + Tailwind as Frontend

**Status:** Accepted  
**Date:** 2026-10-04

### Context

LabelLens is primarily used on mobile devices (camera-first scan workflow). The frontend must enforce typed contracts against the backend API, deploy cheaply, and deliver a responsive mobile-first UI without a large custom CSS surface.

### Decision

Use Next.js (App Router) with strict TypeScript and Tailwind CSS, deployed to Vercel.

### Rationale

- Next.js App Router supports server components, streaming, and image optimization — all relevant for rendering product label data and structure images efficiently on mobile.
- Strict TypeScript mode forces explicit typing of all API responses, making contract drift a compile-time error rather than a runtime surprise.
- Typed API contracts generated from the FastAPI OpenAPI spec close the loop between backend and frontend types.
- Tailwind's utility-first approach delivers consistent mobile-first responsive layouts without a custom design system.
- Vercel's free tier covers MVP deployment (aligns with ADR-011) with zero-config Next.js support.

### Consequences

- All frontend code must pass TypeScript strict mode; `any` casts must be justified with a comment.
- API client types must be regenerated whenever the backend OpenAPI spec changes.
- Tailwind class usage must follow the project's established utility conventions to avoid duplication.

**Rejected alternatives:**
- Plain HTML/JS: no typed contracts between frontend and backend; poor mobile UX without a component model; no server-side rendering for initial load performance.

---

## ADR-004 — RDKit as the Chemistry Engine

**Status:** Accepted  
**Date:** 2026-10-04

### Context

LabelLens validates chemical identifiers (SMILES, InChI, CAS), calculates molecular descriptors, and renders 2D structure images. These operations must be deterministic and verifiable — the same input must always produce the same output, and results must be traceable to an open algorithm, not a black box.

### Decision

Use RDKit as the sole chemistry computation engine.

### Rationale

- RDKit is deterministic: the same SMILES input always produces the same canonical SMILES, descriptors, and structure image. This is essential for the evidence model where calculation provenance must be reproducible.
- BSD license: no commercial restrictions; open source and auditable.
- Python-native: integrates directly into the FastAPI backend without an external process.
- Supports SMILES validation, canonicalization, InChI generation, descriptor calculation (MW, formula, LogP, rings), and 2D depiction.
- Widely used in academic and pharmaceutical research; its behavior is well-documented and peer-reviewed.

### Consequences

- RDKit must be included in all backend environments (dev, CI, production). Docker images must pin the RDKit version.
- Any chemistry calculation whose result is stored in the database must record which RDKit version produced it so stale values can be recomputed after upgrades.
- Non-molecular entities (mixtures, polymers, trade names) must use the representation types defined in ADR-012 and must not be forced through RDKit validation.

**Rejected alternatives:**
- AI-generated chemistry (asking an LLM for a SMILES or formula): not deterministic, not verifiable, and explicitly prohibited by ADR-007. An LLM may hallucinate a plausible-looking but incorrect CAS or SMILES.

---

## ADR-005 — Pipeline Stage Separation: OCR → Extraction → Normalization → Matching → Verification

**Status:** Accepted  
**Date:** 2026-10-04

### Context

Label data passes through several lossy transformation steps before becoming a verified chemical identity. Conflating these steps makes it impossible to know which step introduced an error or how confident each step's output is.

### Decision

Separate the processing pipeline into distinct stages — OCR, extraction, normalization, matching, and verification — each with its own confidence score and stored output.

### Rationale

- Each stage can fail or degrade independently. An OCR stage with 0.6 confidence should not automatically promote to a verified identity.
- Per-stage confidence scores (see ADR-010) allow the UI to surface exactly where uncertainty lies, rather than presenting a single opaque score.
- Raw OCR text is never treated as verified chemistry. It must pass through normalization (synonym resolution, CAS formatting) and matching (source registry lookup, RDKit validation) before any verification flag is set.
- Storing intermediate outputs enables debugging, reprocessing, and audit trails without re-running the full pipeline.
- This is the primary anti-hallucination control: a claim cannot advance to a higher-confidence stage without evidence from that stage.

### Consequences

- The database schema must represent each stage's output as a separate record or column set with its own confidence and timestamp.
- Pipeline stages are independently retryable; the system must handle partial pipeline states gracefully.
- Any code that skips a stage (e.g., pre-loading known chemicals) must explicitly set confidence values and note the bypass reason.

**Rejected alternatives:**
- Single-pass extraction: convenient to implement but masks error sources. A user cannot tell whether a wrong structure came from OCR misread, normalization error, or wrong match.

---

## ADR-006 — Evidence-First Architecture with Claim-Level Provenance

**Status:** Accepted  
**Date:** 2026-10-04

### Context

A product ingredient may have its identity, structure, formula, and role sourced from different authorities. Storing a single description blob per ingredient makes it impossible to express that the CAS came from PubChem, the structure was validated by RDKit, and the role was extracted from the label — each with different confidence.

### Decision

Every important claim is a separate record linked to its source(s). The evidence model is the authoritative representation; display fields are derived from it.

### Rationale

- Claim-level provenance means each field (CAS, formula, SMILES, role, safety flag) carries its own source reference and confidence score.
- Allows the UI to show "CAS confirmed by PubChem (high confidence)" alongside "role extracted from label OCR (medium confidence)" for the same ingredient.
- Supports per-field update: if a new source provides a better structure, only the structure claim is updated; other claims are unaffected.
- Enables audit queries: "show all claims sourced from registry X" or "show all claims with identity_confidence < 0.7".
- Directly supports the multi-dimensional confidence model in ADR-010.

### Consequences

- Queries that need to display a complete ingredient view must join across multiple claim records; views or materialized summaries may be needed for performance.
- All write paths must record a source reference; claims without a source are not permitted.
- The frontend must handle partial evidence (some fields confirmed, others not) gracefully rather than waiting for full confirmation.

**Rejected alternatives:**
- Single `description` blob per ingredient: easy to write but impossible to verify at field level; no way to show per-field confidence or cite individual sources.

---

## ADR-007 — AI as Explanation Layer Only, Not as Authority for Scientific Data

**Status:** Accepted  
**Date:** 2026-10-04

### Context

AI language models can generate fluent, plausible-sounding chemical identifiers, formulas, and safety assessments that are factually wrong. If AI output is treated as authoritative data, hallucinated values will enter the evidence store and propagate to users as facts.

### Decision

AI models are permitted only to generate natural language explanations from verified structured input. AI outputs are candidates, not facts. AI is never permitted to invent or assert CAS numbers, molecular formulas, SMILES strings, or safety classifications.

### Rationale

- All scientific data (CAS, formula, SMILES, descriptors, safety flags) must originate from the source registry (ADR-009) or be calculated by RDKit (ADR-004) — both deterministic and auditable.
- AI-generated explanations are labeled as such in the UI; users can see they are derived from verified inputs, not independently sourced.
- AI outputs that enter the pipeline (e.g., extracted ingredient names from label text) are marked as `candidate` status and must pass normalization and matching before promotion.
- This constraint makes it impossible for a prompt injection in a product label to introduce false chemistry data.

### Consequences

- The backend must validate that no AI response is written directly to a chemistry field without passing through normalization and matching stages.
- Explanation endpoints receive pre-verified structured data as input; they must not make additional lookups or assertions about chemical identity.
- Product copy and UI must clearly communicate that explanations are AI-generated summaries of verified data, not independent AI analysis.

**Rejected alternatives:**
- Using AI as a chemistry data source: not deterministic, not verifiable, and creates legal/safety risk if a user makes a health decision based on a hallucinated safety profile.

---

## ADR-008 — OmniRoute for Model Routing Behind an AIProvider Interface

**Status:** Accepted  
**Date:** 2026-10-04

### Context

LabelLens uses AI models for OCR result extraction, normalization candidates, and explanation generation. Different tasks may benefit from different models, and model availability or pricing may change. Coupling product logic to a specific provider SDK creates high switching cost.

### Decision

All AI model calls are routed through OmniRoute behind an `AIProvider` interface. No product logic may import a provider-specific SDK directly.

### Rationale

- The `AIProvider` interface abstracts provider-specific authentication, request formatting, and response parsing.
- OmniRoute handles model selection, fallback, and load balancing without changes to calling code.
- Swapping providers (e.g., moving a task from one model to another) requires only a configuration change, not a code change.
- This isolation ensures that a provider outage or deprecation affects only the routing layer, not the product logic.
- Consistent with the free-first constraint (ADR-011): cheaper or free models can be substituted without refactoring.

### Consequences

- All AI interactions must be defined as typed task interfaces (inputs/outputs) before implementation; provider-specific quirks are handled inside the adapter, not in product code.
- The `AIProvider` interface must be versioned; breaking changes require migration of all adapters.
- Testing product logic that involves AI calls must mock the `AIProvider` interface, not a specific provider SDK.

**Rejected alternatives:**
- Direct provider SDK calls in product logic: high coupling, makes multi-provider or fallback scenarios require widespread code changes.

---

## ADR-009 — Source Registry as the Only Gateway for Trusted Sources

**Status:** Accepted  
**Date:** 2026-10-04

### Context

LabelLens's credibility depends on the trustworthiness of its data sources. If arbitrary sources can become trusted without review, the evidence model loses its meaning. A claim marked "high confidence" must mean it came from a reviewed, authoritative source.

### Decision

No source may be marked as trusted without going through the source registry review process. The registry defines, for each source: its claim types, authority class, licensing stance, freshness class, and update cadence.

### Rationale

- The registry is the single place where source authority is evaluated and recorded. Product logic that queries the registry can always know whether a source is trusted, for which claim types, and under what license.
- Preventing ad hoc source addition stops confidence inflation: a developer cannot shortcut the process by writing a quick scraper and marking its output as high confidence.
- Licensing stance is recorded per source so the product can avoid surfacing data that cannot be shown to end users under the source's terms.
- Freshness class informs the pipeline when a source's cached data should be considered stale and refreshed.

### Consequences

- Adding a new data source requires a registry entry with all required fields before any pipeline code can use it.
- The source registry must be version-controlled and reviewed alongside schema changes.
- Any source that changes its licensing terms must trigger a registry update and a review of existing claims sourced from it.

**Rejected alternatives:**
- Per-developer source addition without registry review: leads to inconsistent authority levels, unknown licensing exposure, and confidence scores that are not comparable across ingredients.

---

## ADR-010 — Multi-Dimensional Confidence Model

**Status:** Accepted  
**Date:** 2026-10-04

### Context

A single AI confidence score (e.g., 0.87) for an ingredient implies a precision that does not exist. OCR quality, extraction correctness, normalization match quality, identity confirmation, and structure validation are independent concerns that can each succeed or fail independently.

### Decision

Use a multi-dimensional confidence model with separate scores for each pipeline stage and claim type: `ocr_confidence`, `extraction_confidence`, `normalization_confidence`, `identity_confidence`, `structure_confidence`, `formula_confidence`, `role_confidence`, and `evidence_confidence`.

### Rationale

- A single score hides the source of uncertainty. An ingredient with good OCR but a failed structure lookup and a high-confidence label role extraction cannot be accurately represented by one number.
- Per-dimension scores allow the UI to show exactly what is and is not known: "identity confirmed, structure not available, role extracted from label."
- Downstream logic (e.g., flagging ingredients for manual review) can set thresholds per dimension rather than guessing from a composite.
- Avoids false precision: it is more honest to show `identity_confidence: HIGH, structure_confidence: UNKNOWN` than a composite `0.71`.

### Consequences

- All pipeline stages must write their confidence output to the correct dimension field using qualitative states; using a generic `confidence` field is not permitted.
- Numeric scores may be used internally for candidate ranking but must not be displayed to users as calibrated probabilities without validation. Display always uses qualitative states (HIGH, MEDIUM, LOW, UNKNOWN, CONFLICTED).
- UI components must handle null/missing dimension scores without implying failure; absence of a score means that dimension has not been evaluated.
- Aggregated display scores (if needed for sorting or filtering) must be computed as explicit formulas documented in the spec, not inferred from the raw dimensions.

**Rejected alternatives:**
- Single composite AI confidence score: convenient for display but misleading; conflates independent error sources and makes debugging pipeline failures harder.

---

## ADR-011 — Free-First Engineering Constraint

**Status:** Accepted  
**Date:** 2026-10-04

### Context

LabelLens is an MVP. Committing to paid infrastructure, APIs, or services before there is evidence of user demand creates cost before value. The team must be able to build, deploy, and iterate without a budget.

### Decision

Build and operate at zero or near-zero cost for MVP. Evaluate paid services only when a measured gap exists that a paid service would close. Prefer local verified datasets, free authoritative APIs, and local RDKit calculations over paid alternatives.

### Rationale

- Supabase free tier, Vercel free tier, and free public chemistry APIs (PubChem, ChEMBL) cover the MVP stack at no cost.
- RDKit runs locally; no per-calculation API cost.
- Free-first forces prioritization: only features with clear user value justify introducing a cost.
- When a paid service is evaluated, the decision must be recorded as an ADR update with the measured gap that justified it.

### Consequences

- Rate limits on free-tier services must be accounted for in the pipeline design; heavy batch operations must be queued and throttled.
- Any introduction of a paid dependency requires an explicit decision record and cost estimate before merging.
- Performance optimization should prefer algorithmic improvements and caching over scaling up paid infrastructure.

**Rejected alternatives:**
- Starting with paid infrastructure: acceptable eventually, but premature before product-market fit; creates burn rate and irreversible commitments.

---

## ADR-012 — Representation Types for Non-Molecular Entities

**Status:** Accepted  
**Date:** 2026-10-04

### Context

Not every ingredient on a product label is a discrete small molecule with a valid SMILES string. Many ingredients are mixtures, polymers, trade names, or natural complexes for which a single SMILES is meaningless or does not exist. Forcing all ingredients through a SMILES-mandatory path would cause fabricated structures to enter the database.

### Decision

Every ingredient record has an explicit representation type: one of `single_molecule`, `salt`, `polymer`, `material`, `mixture`, `natural_complex`, `formulation`, `trade_name`, or `unknown`. SMILES and structure data are only populated for types where they are meaningful. The UI shows "not applicable" for structure fields when the representation type does not support them.

### Rationale

- Prevents structure fabrication: a `mixture` type ingredient cannot accidentally receive a SMILES value, because the pipeline checks representation type before writing structure fields.
- Enables accurate UI rendering: the frontend knows not to show a structure image placeholder for a trade name, avoiding confusing empty state.
- `unknown` type allows the pipeline to store an ingredient without asserting its nature before sufficient evidence is available.
- Representation type is itself a claim with its own confidence, allowing it to be updated as evidence improves.

### Consequences

- All ingredient write paths must set representation type explicitly; `unknown` is the only permitted default when type cannot be determined.
- Chemistry validation logic must gate on representation type before calling RDKit; calling RDKit on a `mixture` is an error.
- Frontend components that display chemistry data must check representation type before rendering structure-related UI elements.

**Rejected alternatives:**
- Universal SMILES requirement: forces fabricated or placeholder structures for mixtures and trade names, undermining the anti-hallucination architecture.

---

## ADR-013 — UUID Primary Keys Throughout

**Status:** Accepted  
**Date:** 2026-10-04

### Context

LabelLens may involve multiple backend services, offline import workflows, and future distributed agents that generate records independently. Sequential integer primary keys create collision risk in these scenarios and expose internal record counts through public IDs.

### Decision

All tables use UUID primary keys generated at the application or database level.

### Rationale

- UUIDs are safe for distributed generation: two services can create records simultaneously without coordination and without collision.
- No sequential ID leakage: users and external systems cannot infer record counts or creation order from exposed IDs.
- Offline/import workflows can pre-assign UUIDs before writing to the database, enabling idempotent inserts.
- PostgreSQL has native UUID support (`uuid` type, `gen_random_uuid()`); no extension required on modern versions.

### Consequences

- UUIDs are larger than integers (16 bytes vs 4-8 bytes); index size increases. This is acceptable at MVP scale.
- URLs and logs will contain UUID strings; tooling that displays them must be comfortable with non-sequential IDs.
- Foreign key joins on UUIDs are slightly more expensive than integer joins; query plans should be reviewed if performance issues arise.

**Rejected alternatives:**
- Sequential integer PKs: simple and compact but unsafe for distributed generation and leaks record counts through public-facing IDs.

---

## ADR-014 — Vertical Slice Development Order

**Status:** Accepted  
**Date:** 2026-10-04

### Context

LabelLens has multiple subsystems (OCR, chemistry, evidence, AI explanation, comparison) that depend on each other. Building horizontally (completing all infrastructure before any feature) delays working software and makes integration problems visible late. Building by feature slice ensures each increment is testable end-to-end.

### Decision

Develop in vertical slices in this order: Health + DB → Scan → OCR → Ingredient editing → Entity matching → Chemistry → Evidence → Analysis → Compare → Grounded explanation.

### Rationale

- Each slice delivers a working, testable increment. After the OCR slice, a label image can be scanned and ingredients listed, even if chemistry data is not yet enriched.
- Dependencies flow forward: chemistry requires matching, matching requires OCR, OCR requires scan. Building in this order means each new slice has a tested foundation.
- Integration bugs surface early: the database schema, API contracts, and frontend types are exercised from the first slice, not discovered during final integration.
- The explanation slice is last because it consumes verified structured data from all prior slices; building it first would require mocking everything.

### Consequences

- Feature work that skips ahead in the slice order must explicitly mock or stub the missing dependencies; those stubs must be replaced before the dependent slice ships.
- Each slice has defined acceptance criteria before development starts.
- Refactoring that affects an earlier slice must be verified against all later slices that depend on it.

**Rejected alternatives:**
- Horizontal layered build (all DB, then all API, then all UI): delays working software; integration issues discovered late; harder to demo or gather feedback incrementally.

---

## ADR-015 — No Chat Endpoint / No Generic AI API

**Status:** Accepted  
**Date:** 2026-10-04

### Context

It would be technically simple to expose a `/chat` endpoint that passes user messages to an AI model and streams responses. However, this would make AI output the product rather than an implementation detail, undermining the evidence-first architecture and creating a path for unverified AI assertions to reach users.

### Decision

LabelLens exposes only task-specific API endpoints: `POST /normalize`, `POST /match`, `GET /chemistry`, `GET /evidence`, `GET /explanation`. There is no `/chat` endpoint and no generic AI passthrough API. AI is an implementation component; it has no externally visible surface of its own.

### Rationale

- Task-specific endpoints enforce that every AI call has a defined input schema, output schema, and validation step. A generic chat endpoint has none of these.
- Prevents prompt injection via product labels from having any effect: the API does not accept freeform user text that gets passed directly to an AI model.
- Makes the product's behavior auditable: every AI interaction is tied to a specific pipeline stage with logged inputs and outputs.
- Consistent with ADR-007: AI is an explanation layer, not an authority. A chat endpoint would imply AI authority.
- Keeps the API surface small and purposeful; each endpoint has a clear contract and testable behavior.

### Consequences

- Any new AI-assisted feature must be expressed as a new typed endpoint, not by extending a generic chat surface.
- The frontend must not display AI outputs that do not correspond to a specific structured API response.
- Documentation must clearly explain that LabelLens is not an AI chatbot about ingredients; it is a structured verification tool with AI-generated explanations.

**Rejected alternatives:**
- Generic `/chat` or `/ask` endpoint: convenient for rapid prototyping but bypasses the evidence model, creates hallucination risk, and makes the product's behavior non-auditable.

---

## ADR-016 — Single Canonical Ingredient Parser (Stage 2 Extraction)

**Status:** Accepted  
**Date:** 2026-10-05

### Context

The master brief warned of duplicated/conflicting ingredient processing
(`parseRawLabelText()` naive comma splitting vs `parseIngredientTree()` vs
`pipeline.ts` vs UI-local parsing). The 2026-10-05 implementation audit
(`IMPLEMENTATION_AUDIT.md`) found none of that code exists in this checkout —
`frontend/` is empty scaffolding and the backend is a health-endpoint skeleton.
The duplication risk is therefore prospective, and the cheapest time to prevent
it is before the first competing implementation appears.

### Decision

Exactly one canonical extraction entry point:
`backend/app/services/ingredient_parser.py :: parse_label_ingredients(text)`.
All future paths (OCR post-processing, manual-text entry, re-analysis after
user correction, seed scripts) must call it. No UI or service code may
implement its own top-level `split(",")`.

The parser is deliberately chemistry-free: it extracts nesting, percentages,
and INS/E identifiers plus syntactic normalization only. Nodes start as
`match_status="unresolved"` / `verification_status="unverified"`. Entity
resolution, chemistry, roles, and evidence arrive in later vertical slices.

### Consequences

- Parser regressions (brief §17 Cases A–J) must stay green; any extraction
  behavior change requires a test update in the same commit.
- The future normalization service (Stage 4) must not re-implement tokenizing;
  it consumes parser nodes.
- If an external prototype containing `ingredientParser.ts` /
  `labelExtractionService.ts` is later merged, its parsing logic must be
  reconciled against this canonical parser (second audit pass) rather than
  added alongside it.

**Rejected alternatives:**
- Per-caller naive splitting: fast to write, silently breaks every nested
  declaration (`A (B, C), D`) and recreates the exact conflict the brief warns about.

---

## ADR-017 — Syntactic-Only Normalization Boundary (Stage 4)

**Status:** Accepted  
**Date:** 2026-10-05

### Context

Stage 4 sits between raw observation (Stage 2 parser tree) and entity
resolution (Stage 5). Without an explicit boundary, normalization tends to
accumulate identity guesses (alias→molecule mapping, OCR autocorrect,
umbrella-term resolution) that belong to resolution/evidence stages.

### Decision

`backend/app/services/ingredient_normalizer.py :: normalize_result()` is the
only normalization entry point. It consumes parser nodes and emits
`NormalizedIngredient` records (own `id`, linked via `parser_node_id`) with:
raw text, canonical text (lowercase except spaced uppercase additive codes),
tree position, percentage, identifier, status
(`complete | partial | failed` per `DATA_PIPELINE.md` Stage 4), warnings, and
observation provenance. Warning taxonomy: `possible_ocr_variation`
(detectable artefacts only — silent typos like `Sodlum` stay uncorrected),
`uncertain_parse_<level>` (inherited parser uncertainty), `empty_observation`.

Guarantees locked by regression tests: tree shape preserved (never
flattened); `normalize(normalize(x)) == normalize(x)`; no
chemical/identity/role/evidence fields exist on the output.

### Consequences

- Entity resolution must consume normalized nodes, never re-tokenize raw
  text and never treat `normalized_text` as a verified identity.
- Any future alias dictionary lives in resolution, not here.

**Rejected alternatives:**
- Autocorrect-style normalization (edit-distance fixing of OCR typos):
  converts observations into guesses without evidence; explicitly forbidden.

---

## ADR-018 — Candidate-Only Entity Resolution (Stage 5)

**Status:** Accepted  
**Date:** 2026-10-05

### Context

Stage 5 sits between normalized text and verification. The failure mode to
prevent is silent promotion: a plausible string match becoming a verified
chemical record with formula/CAS/structure attached.

### Decision

`backend/app/services/entity_resolver.py :: resolve_entities()` is the only
resolution entry point. It reads Stage-4 nodes and an explicit
`EntityRegistry` (contract + `InMemoryRegistry`; empty registries valid) and
emits `Resolution` records with statuses
`exact_match | candidate | ambiguous | unresolved` — no `verified` status
exists. `selected_candidate` is set only on a single exact hit; ambiguity
and OCR-near results stay unselected with deterministic ordering
(method rank, score, name, ref). Internal scores are ranking-only, never
calibrated probabilities. Test registries use `TEST-###` refs and
`synthetic_test_fixture` sources so fixtures can never be mistaken for
verified chemistry. No network, RDKit, AI, or dynamic behavior: identical
registry + input always yields identical output.

### Consequences

- Verification/evidence stages must consume `Resolution` records and enforce
  the formal gate before any `verified` state; they may not reinterpret a
  candidate ref as a chemical-entity ID.
- New alias/identifier mappings require explicit registry entries, never
  algorithmic invention.

**Rejected alternatives:**
- Fuzzy-first matching as authority: unbounded similarity promotes guesses;
  OCR-near is therefore bounded (distance ≤ 2, length ≥ 5), flagged, and
  never selected.

---

## ADR-019 — Verification Authority and State Model (Stage 6)

**Status:** Accepted (architecture; implementation deferred to Stage 7)
**Date:** 2026-10-05

### Context

Stage 5 ends at plausible candidates. The `CANDIDATE → VERIFIED`
transition is the highest-risk step in LabelLens: a weak promotion rule
would silently convert string similarity into scientific fact. Full
analysis in `STAGE_6_VERIFICATION_ARCHITECTURE.md`.

### Decision

Verification authority = **Option C**: a versioned local canonical
snapshot decides; live official sources supply refresh evidence through
provider-independent adapters; manual review breaks ties. Frozen gate
V1–V7 (admissible candidate, authoritative source, identity agreement,
identifier validation, entity-type validation, source appropriateness,
context checks) with versioned rules. States split by owner (resolution:
candidate-family; verification: provisional/verified/conflicted/
unverified/unknown/obsolete) with append-only transitions. Verified
status lives per claim row, never as entity-wide implication.

### Consequences

- Stage 7 must implement the gate, orchestrator, adapter ABC, snapshot
  adapter + v1 seed, and the §15 test layers — and nothing beyond the
  persistence boundary (no chemistry, roles, explanations).
- No live source may write canonical truth without passing ingestion +
  gate as a new snapshot version.

**Rejected alternatives:**
- Option A (snapshot-only forever): goes stale on dynamic facts.
- Option B (live-API-only): non-reproducible, rate-limited, untestable
  offline, unusable without network.

---

## ADR-020 — Verification Implementation Hardening (Stage 7)

**Status:** Accepted  
**Date:** 2026-10-05

### Context

Implementing ADR-019 exposed two cases the architecture left implicit:
records curated under older gate rules, and identifier checks for
non-molecular entities that legitimately carry no identifiers.

### Decision

1. A snapshot whose `verification_rule_version` differs from the running
   gate can never yield `verified`: the orchestrator downgrades to
   `provisional` with a `snapshot_rules_version_mismatch` warning.
2. V4 passes vacuously only for non-molecular representations; molecular
   entities without identifiers stay `UNKNOWN` (hence `provisional` at
   best), preserving "UNKNOWN never counts as PASS".
3. CAS checksum validity is an integrity signal only; belonging still
   requires name+identifier dual agreement against the same record.

### Consequences

- Stage-8 live adapters inherit the same downgrade: version skew can
  only ever reduce certainty, never preserve it silently.

**Rejected alternatives:**
- Auto-accepting older-rule snapshots with a warning only: warnings are
  ignorable downstream; the status downgrade is enforced in the type.

---

## ADR-021 — Official Evidence Without Verification Authority (Stage 8)

**Status:** Accepted
**Date:** 2026-10-05

### Context

Stage 7 verifies against a local snapshot. Stage 8 adds live official
sources (PubChem PUG-REST, ChEBI 2.0 REST -- endpoints verified against
official docs and live response shapes) as *evidence*, while keeping the
frozen V1–V7 gate as the sole decider.

### Decision

1. Evidence and verification stay in separate modules: adapters produce
   field-level `EvidenceItem` rows; `CombinedAdapter` merges provider
   record lists with no entity linking and no semantics of its own.
2. The evidence cache stores parsed items with hash/TTL metadata and
   replays them byte-identically; a hit never upgrades or refreshes.
   Offline mode serves cache or degrades to `unknown`.
3. Provider-provider field conflicts (formula, InChIKey, weight,
   doubly-claimed identifiers) map to the pre-existing `conflicted`
   branch -- the only orchestrator change, justified by Stage-6
   conflict case 6. Raw SMILES/InChI strings are excluded from
   auto-conflict (serialization differs without chemical difference).
4. All network behavior is confined to one shared HTTP module with
   timeouts, size bounds, bounded retries (transient + selected 5xx
   only; never 400/404/429), and conservative spacing. Official quotas
   are not asserted; spacing is documented as conservative.
5. Salt-form verification remains blocked on provider evidence alone
   (structure records carry no reliable form signal) -- tested and
   documented as a limitation, not worked around.

### Consequences

- New providers = new adapter + registry entry; gate, orchestrator
  mapping, and tests for prior stages are untouched.
- Any future live use must add quota verification against current
  official docs plus a secrets/egress review; tests stay offline.

**Rejected alternatives:**
- Provider-returned "verified" flags or first-result assumption:
  payloads are data; only whitelisted fields are extracted.
- Cross-provider entity ID linking by assumption: agreement must come
  from field/identifier overlap.
- Canonicalizing SMILES for comparison without cheminformatics:
  would invent chemistry comparison the project cannot defend.

---

## ADR-022 — Human Review Routes Through the Gate (Stage 9)

**Status:** Accepted
**Date:** 2026-10-05

### Context

Provisional/conflicted/unknown outcomes need a human path that cannot
become a backdoor to `verified`. Full analysis in
`STAGE_9_HUMAN_REVIEW.md`.

### Decision

1. Review lifecycle (queued/in_review/approved/rejected/
   needs_more_evidence/closed_unknown) is separate from verification
   status; approvals are identity-only and reasoned, with AI
   identities rejected.
2. `ManualAdapter` holds selections but returns zero source records:
   human judgment is not evidence and is never fabricated into any.
3. `reverify_candidate` validates selection scope, candidate
   membership, and evidence-hash freshness, then runs the unchanged
   gate with disambiguation enabled. Name changes are rejected by key
   mismatch (re-resolution required, not verification).
4. Production readiness (docs audit): neither provider requires
   credentials; official quota numbers are UNKNOWN (not scraped from
   third parties); client spacing stays conservative and is never
   presented as provider quota.

### Consequences

- Any future review UI or persistence writes through these same
  transitions; direct status mutation has no code path.
- First live provider use still requires quota confirmation against
  current official docs plus an egress review.

**Rejected alternatives:**
- Human "approve" buttons writing `verified` directly: creates
  unverifiable truth by keystroke.
- Fuzzy evidence-similarity for staleness: only byte-identical
  material context reuses an approval.

---

## ADR-023 — Persistence Without Redesign (Stage 10)

**Status:** Accepted
**Date:** 2026-10-05

### Context

Stage 10 needed claim/review/decision tables, some spec-defined and
some (decisions, reviews, review events) required by the stage gates
but absent from `DATABASE_SCHEMA.md`. Full analysis in
`STAGE_10_PERSISTENCE.md`.

### Decision

1. Spec tables implemented verbatim plus documented nullable
   extensions only (freshness columns on `claims`, provenance
   columns on `claim_sources`); alternatives stay in
   `ingredient_candidates`, never as new columns.
2. Missing-table FK targets stay plain UUIDs with activation comments
   rather than stub tables or dropped columns.
3. The never-applied invalid UUID literals in `002_seed_data.sql`
   were corrected in place (no applied state rewritten); `003`
   re-seeds idempotently regardless.
4. Writes are service-role-only in code and RLS; reads are
   authenticated-only on audit tables; events are trigger-immutable.
   Per-user RLS waits for user_id (auth stage). No production-readiness
   claim until a Supabase-project review happens.

### Consequences

- Future persistence (products, scans, auth) adds tables/columns and
  activates deferred FKs; no existing table is reshaped.
- `greenlet` joins backend dependencies (SQLAlchemy asyncio
  requirement), pinned in `pyproject.toml`.

**Rejected alternatives:**
- One wide `ingredients` table: destroys claim-level states.
- Storing raw provider payloads: unbounded growth and PII/secret
  risk; hashes + locators + extracted evidence instead.
- Rewriting 001/002 history: unnecessary; additive repair only.

---

## ADR-024 — API as Authenticated Adapter (Stage 11)

**Status:** Accepted
**Date:** 2026-10-05

### Context

The persisted verification path needed a callable backend surface
without leaking domain authority into routes or inventing
production identity prematurely. Full analysis in
`STAGE_11_API.md`; endpoint contracts in `API_SPEC.md` §100.

### Decision

1. Routes are adapters only: typed principal in, validated service
   command, domain service, repository. No SQL, chemistry,
   verification, or review rules in routes.
2. Bearer tokens map to principals via a `TokenVerifier` interface;
   reviewer identity derives server-side (`human:{subject}`).
   Development/tests use an explicit static map; Supabase JWT is
   the documented (not implemented) production verifier.
3. Review scope stays identity-only (schema-enforced 422);
   stale evidence fails closed (409); verification IDs are
   match-scoped so identical text on different matches never
   shares a decision row; review IDs are process-scoped with a
   persisted-id collision probe.
4. Errors use the spec envelope with spec codes; request IDs
   correlate logs without carrying secrets.
5. Services are bound per request by middleware, not stored on
   `app.state`: Postgres opens one connection and one transaction per
   request on the serving event loop, so connections never cross
   loops and a multi-write operation commits or rolls back as one
   scope. Memory bundles are shared but never mutated outside a
   transaction scope.
6. A decision naming a canonical entity is only persisted when
   `chemical_entities` actually contains that entity (checked before
   any write, 422 `ENTITY_NOT_FOUND` otherwise). Entity registration
   is a service-role import with no route -- the API never creates
   chemistry.

### Consequences

- Future Supabase JWT support swaps the verifier only; routes,
  services, and tests keep their contracts.
- Tests must register the canonical entities their evidence names
  (offline store seed, live `chemical_entities` rows) before a
  verified decision can persist. That is the real integration
  prerequisite, now asserted instead of assumed.
- Live production still requires JWT verification, per-user row
  scoping, rate limiting, and a declared frontend origin -- all
  recorded as deferred, none claimed done.

**Rejected alternatives:**
- Client-supplied reviewer identity: unauditable impersonation.
- Generic 400/500 errors: unactionable clients and leaked internals.
- Auto-verifying analyze results into reviews without routing:
  bypasses the Stage-9 lifecycle.
- Long-lived app-scoped database connection: loop affinity bugs and
  no atomic scope per operation.
- Writing claims with a null entity link when the entity is
  unknown: silently drops provenance the record exists to carry.

---

## ADR-025 — Supabase JWKS Verification as the Production Identity (Stage 12)

**Status:** Accepted
**Date:** 2026-10-05

### Context

ADR-024 defined the `TokenVerifier` interface and deliberately left
the production identity unimplemented ("documented future"). Stage 11
shipped with static development tokens only, which cannot be
exposed to real users. Supabase's current signing model
(supabase.com/docs/guides/auth/jwts, /guides/auth/signing-keys) is
asymmetric: the project publishes a JWKS document at
`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, tokens carry a `kid`,
and the edge caches the key set for 10 minutes. Full analysis in
`STAGE_12_PRODUCTION_READINESS.md` §2.

### Decision

1. `TokenVerifier` stays provider-independent; `verify` becomes
   `async` because the production verifier performs network I/O. The
   `StaticTokenVerifier` survives for development and tests and is
   made async to match the protocol.
2. Tokens are always signature-verified. There is no decode-only
   path, no "trust the claims" shortcut, and no verification bypass
   for trusted networks.
3. Verified: signature, `alg` bound to the key, `kid`, `iss`, `aud`,
   `exp`, `nbf`, `iat`, `sub`. `exp`/`iss`/`sub` are required;
   configured algorithms are asymmetric only, so a symmetric (HS256)
   project fails closed rather than being silently accepted through
   a shared secret.
4. Tokens whose `role` claim is a database role (`service_role`,
   `anon`, `supabase_admin`, ...) are rejected. The backend's own
   credential is not a user identity, so it can never authenticate as
   a person.
5. Reviewer authority comes only from the operator allowlist
   `SUPABASE_REVIEWER_SUBJECTS`. User-writable claims
   (`user_metadata`, `app_metadata`, custom claims) are never read
   for authorization.
6. The JWKS document is cached in-process with a bound on every
   dimension: HTTPS only, TTL (300 s, below the documented 10-minute
   edge cache), a minimum-refresh floor (30 s) that also applies to
   *failed* fetches, ≤16 keys, ≤64 KB per response, one lock for
   refresh serialization. A retired key stays trusted only until the
   TTL expires — a bounded, documented grace window.
7. Configuration is entirely environmental, and construction fails
   closed in production: no Supabase issuer/JWKS, no algorithm, or
   any `DEV_API_TOKENS` present under `ENVIRONMENT=production` all
   raise instead of degrading to a weaker boundary. When Supabase is
   configured, it wins over the static map.
8. Every failure category (bad signature, expiry, `nbf`, issuer,
   audience, algorithm, missing `sub`, unknown `kid`, malformed token,
   JWKS unreachable) produces one identical public 401. The specific
   reason exists only as an internal diagnostic string that is logged
   and never returned, so callers get no oracle. Tokens and claims
   are never logged, returned, or persisted; `MAX_TOKEN_CHARS`
   rejects oversized input before parsing.
9. `Principal` carries only trusted identity: subject, role, issuer,
   `kid`, expiry, and the server-derived `human:{subject}` reviewer
   id.

### Consequences

- The Stage-11 auth contract is preserved: only the verifier
  implementation changed, so routes, services, and tests kept their
  shapes.
- Key rotation works without a restart; a new `kid` triggers at most
  one refresh per cooldown window, so bogus key ids cannot drive a
  fetch flood.
- Static tokens are impossible in production — a misconfiguration is
  a startup failure, not a quiet downgrade.
- JWKS fetch latency and availability are on the request path. The
  timeout is 5 s; failure is a 401, never an acceptance.
- Symmetric Supabase projects are unsupported by design.
- The verifier has only been exercised against a mocked JWKS
  transport. Running it against a live project is the first
  deployment check.

**Rejected alternatives:**
- Decoding claims without verifying the signature: anyone could mint
  a subject, including a reviewer.
- HS256 support with a configured shared secret: Supabase publishes
  no keys for symmetric projects and does not recommend it.
- Reviewer role read from a token claim: self-grantable by anyone who
  can edit their own profile.
- Unbounded JWKS refetch on unknown `kid`: a trivial remote amplifier.
- A configurable "skip verification in production" escape hatch: the
  exact failure this stage exists to remove.
- Distinguishing failure reasons in the HTTP response: hands an
  attacker a verification oracle.

---

## ADR-026 — Canonical Entity Registration Is a Service-Role Import (Stage 12)

**Status:** Accepted
**Date:** 2026-10-05

### Context

Stage 11 surfaced a real integration prerequisite: a decision naming a
canonical entity is only persisted when `chemical_entities` actually
contains that entity (ADR-024 §6), and no path created those rows —
tests seeded them by hand. Production therefore needs a way to
populate the canonical registry. The master brief is explicit that
the system never invents chemistry: only approved records may exist,
no user-created entities, no bulk auto-verification. Full analysis in
`STAGE_12_PRODUCTION_READINESS.md` §3.

### Decision

1. The only registration path is the CLI
   (`app/cli/import_canonical_entities.py`). There is no route, no
   admin endpoint, and no request body that can create an entity.
2. The command requires direct database credentials (the service
   role) *and* an explicit `ENTITY_IMPORT_CONFIRM=service-role`
   interlock; without it the command refuses and exits 1 before any
   connection is opened. The API process never sets it.
3. Only approved canonical records are registrable: the artifact's
   `verification_rule_version` must equal the frozen gate version
   `1.0.0`, an optional `--expect-snapshot-version` must match, every
   record must be `verification_status = verified`, entity and
   representation types must be in the approved vocabulary, and
   provenance must be complete. No chemistry is computed, derived, or
   inferred — values are transcribed verbatim.
4. The whole artifact is validated before any write. One
   unacceptable record raises `RegistrationRejected` carrying a
   deterministic report of every rejection reason, and nothing is
   written. The report is stable JSON with no timestamps.
5. Writes are all-or-nothing in one transaction; a rejected write
   (for example a constraint violation) propagates so no partial
   state survives. Entity and alias inserts use `ON CONFLICT DO
   NOTHING`, and entity identity is stable (UUID verbatim, otherwise
   `uuid5("canonical-entity:<id>")`), so re-running the import is
   idempotent and cannot create a second identity.
6. Provenance is stored in the existing `chemical_entities.metadata`
   JSONB document together with `first_verified_at`/`last_verified_at`
   — no new table and no new migration.
7. The resolver registry is a projection of the registered rows
   (`build_registry`), built at startup. A failed load leaves the
   registry empty (candidates unresolved) rather than partially
   populated, and no live provider response is ever injected into
   it. `RegistryEntry.ref` remains registry-local, preserving the
   Stage-5 invariant that a resolver match is not an entity identity.
8. A re-run of the import reaches the resolver only after an
   application restart; there is deliberately no reload endpoint.

### Consequences

- The canonical registry can only contain records a human approved
  in a versioned artifact, with a locatable source for each one.
- Operators need database credentials to register chemistry, not an
  API session; this matches the security policy that canonical
  chemistry writes are server-side only.
- Tests must register entities through the import (or a fixture that
  mirrors it) instead of inventing rows, so the registration
  prerequisite is exercised rather than bypassed.
- Registry contents are only as fresh as the last process start.
- `chemical_entities` and `ingredient_aliases` remain without RLS
  (service-role only). Enabling it is a Stage-13 candidate, not a
  silent omission.

**Rejected alternatives:**
- A `POST /api/v1/entities` admin route: any authenticated caller
  could attempt to create chemistry, and it would need a second
  authorization path for no benefit.
- Seeding entities from a live provider response: a lookup would
  return whatever the provider said at that moment, which is
  auto-verification by side effect.
- Storing provenance in a new table: an extra table for data that
  `metadata` already holds, plus a migration for no query gain.
- Importing records that are merely "not rejected": provisional and
  conflicted records are exactly the ones a human must resolve first.
- Per-record commits: a partially imported registry is a registry
  nobody can reason about.

---

## ADR-027 — Application Rate Limiting on Sensitive Writes (Stage 12)

**Status:** Accepted
**Date:** 2026-10-05

### Context

The API accepts authenticated writes that trigger the resolver, the
frozen gate, and provider evidence fetches. Nothing bounded how often
one identity could do that, and nothing distinguished an abuse
pattern from normal use. `SECURITY.md` §7 already required rate
limiting on high-cost endpoints; this stage implements it for the
three operations that actually exist.

### Decision

1. Three operations are limited, no more: `POST /api/v1/observations`
   (`observations.create`, default 30/60 s),
   `POST /api/v1/observations/{id}/analyze` (`observations.analyze`,
   20/60 s), and `POST /api/v1/reviews/{id}/decision`
   (`reviews.decision`, 20/60 s). Reads and the reviewer claim route
   are not limited.
2. `RateLimiter` is a one-method protocol (`hit(key, limit, window)`)
   so the backend can become Redis or database-backed without
   touching routes or domain code. `InMemoryRateLimiter` is the only
   implementation shipped here, with an injectable clock so tests
   are deterministic.
3. The bucket key is derived from the authenticated principal:
   `"<action>|<verified subject>"`, optionally combined with the peer
   address (`RATE_LIMIT_INCLUDE_IP`, default off because behind a
   proxy the peer address is the proxy's). No header and no body
   field can influence it.
4. Windows are fixed and lazily expired; storage is bounded by
   `RATE_LIMIT_MAX_KEYS` with least-recently-used eviction. A bounded
   limiter degrades accuracy, never correctness.
5. Denial is `429 RATE_LIMITED` in the standard error envelope with
   a `Retry-After` header, emitted by the single `ApiError` handler
   from `request.state.rate_limit_retry_after`, so every refusal
   looks the same and discloses no bucket internals.
6. If the limiter backend raises, the request is refused with `503
   RATE_LIMITER_UNAVAILABLE` — fail closed. Degrading to "allow"
   would disable the control exactly when the backend is unhealthy.
7. Budgets are configuration-driven (`RATE_LIMIT_*`); no route
   carries a hard-coded number, and `app.state.rate_limit_policy` is
   an injection seam for tests. No new database table.
8. The review-decision route passes `require_reviewer` into the
   limiter dependency so the stricter role check runs before a bucket
   is consumed.

### Consequences

- Abusive or accidental write floods are bounded per identity, and
  the refusal is a standard, machine-readable response.
- The limiter is per process: N replicas multiply the budget by N and
  a restart clears all state. This is stated in the module
  docstring, in `SECURITY.md`, and in the stage document rather than
  left for someone to discover.
- The abstraction is the same shape a shared backend will need, so
  moving to Redis is a configuration and deployment change.
- Fail-closed means an unhealthy limiter turns into 503s on those
  three routes, which is visible in monitoring rather than silent.
- Tests unrelated to rate limiting must inject a permissive policy
  (done in `app/tests/api/helpers.py`) because the default limiter is
  process-wide and would otherwise be exhausted by a whole suite.

**Rejected alternatives:**
- Keying buckets on a client-supplied user id: an attacker chooses
  their own bucket.
- Limiting reads as well: browsing becomes degraded by an abuse
  control that exists for cost and write safety.
- A 200 response with an error body: contradicts the API spec's
  status strategy and hides refusal from clients and proxies.
- Failing open on limiter errors: silently removes protection during
  the incident it was added for.
- Adding a rate-limit table to the database: not required by the
  requirement, adds write contention to the paths being protected.

---

## ADR-028 — Real-Label Slice With Draft Fixtures (Stage 13)

**Status:** Accepted
**Date:** 2026-10-05

### Context

Stage 13 required real-label input, but the audit found zero usable
ground truth: all 30 `LABEL_REGRESSION_DATASET.csv` rows are
`needs_real_label` placeholders and all 100 golden rows are
`needs_verification` seeds. Fabricating "realistic" labels was
explicitly out of scope. Four genuinely sourced labels were
transcribed instead (OFF OCR record, two FDA DailyMed SPL inactive
paragraphs, one INCIDecoder INCI transcription with its weaker
provenance marked). Full analysis in
`STAGE_13_REAL_LABEL_VERTICAL_SLICE.md`.

### Decision

1. Fixtures live outside the two CSVs, carry cited sources with
   retrieval dates and scope notes, and are marked
   `review_status: "draft"` -- sourced, not yet independently
   reviewed. A test pins both CSVs at zero verified rows.
2. Expectations encode reviewed pipeline behavior, including honest
   negatives: bare registered names verify only to provisional
   (V3 single-source corroboration), the `glycerin` synonym gap
   stays an unselected candidate (the approved names do not list
   it), and generic terms, color additives, and unregistered
   substances stay unresolved/unknown with no invented chemistry.
3. The correction boundary is a service method, not a route:
   `ObservationService.correct` keeps raw immutable, stores one
   documented revision with reason, persists a fresh normalization
   row, and refuses a second correction. Analysis/reads use
   `display_text or raw_text`; `get_normalization_for_observation`
   returns the latest row (identical for the single-row case).
4. Reruns are stable by construction: caller-supplied observation
   ids plus uuid5 normalization ids over observation + content, so
   existing `ON CONFLICT DO NOTHING` / memory upsert semantics
   reuse rows instead of duplicating them.
5. The runner (`app/regression/`) is a test harness with a
   developer-only CLI that exits non-zero on mismatch. No HTTP
   endpoint, no frontend, no AI, no RDKit, no new providers, no new
   tables or migrations; V1-V7, parser, normalizer, resolver, and
   adapters are untouched.
6. Two pre-existing behaviors were observed and deliberately left
   alone: systematic IUPAC-style names are mangled by the Stage-4
   normalizer, and `verification_events` rows are written only on
   claim state change. Both are recorded as Stage-14 candidates,
   not fixed under a regression stage.

### Consequences

- The data/chemistry trust path is proven on real label text with
  persisted claims, decisions, evidence links, and an auditable
  provenance chain in both backends.
- Draft fixtures must pass independent review before they can ground
  any stronger claim; the 4-label slice is a pipeline proof, never
  a market sample, and its metrics carry no accuracy claim.
- Unknown-expected ingredients receiving an entity is a hard
  failure (false-positive count asserted at 0), so future registry
  growth is automatically checked against over-resolution.

**Rejected alternatives:**
- Populating the placeholder CSV rows to "have ground truth": turns
  unevidenced cells into fake authority.
- Snapshot-recording pipeline output as expectations: asserts
  nothing about correctness.
- Promoting `glycerin` via a fixture-side alias: fixture truth
  overriding the canonical registry.
- Forcing all labels to `verified`: the sourced labels print no
  identifiers, so verification would be theater.
- A `PATCH /observations` route: the product has no frontend or
  accounts yet; a route would add unaudited write surface for no
  user.

---

## ADR-029 — Systematic-Name Syntax Fix and the Unmet Verified Path (Stage 14)

**Status:** Accepted
**Date:** 2026-10-05

### Context

Stage 13 left two items: a confirmed normalization defect
(`propane-1,2,3-triol` damaged into `propan E 1`) and zero verified
outcomes across 50 real-label ingredients. Stage 14 addressed both.
Full analysis in
`STAGE_14_SYSTEMATIC_NAMES_AND_VERIFIED_PATH.md`.

### Decision

1. The defect was in the parser, not the normalizer: unconditional
   comma-splitting broke locant runs, and the trailing
   additive-code pattern matched word-final `e` + digits without a
   token boundary. The fix is syntactic only -- digit-comma-digit
   without whitespace never separates; a code tag must start at a
   token boundary. No chemistry knowledge entered either module;
   resolver ranking is untouched.
2. The fix unlocks registered systematic-name aliases through the
   existing path (`propane-1,2,3-triol` -> glycerol via
   `exact_alias`); unregistered systematic names stay unresolved.
3. RL-14-01 (Frooti, retailer-secondary, draft) proves exact
   identifier resolution on a real label (`INS 330` -> citric
   acid) with an honestly unverified decision: function-names
   agree with no record, and frozen V3/V4 require name+identifier
   dual agreement on one record.
4. The real-label VERIFIED criterion is reported NOT MET rather
   than simulated: no quotable English name+code co-printing was
   found (labelling formats print a name or a code, not both), the
   review loop cannot waive dual agreement (human confirmation of
   a bare name yields provisional/MEDIUM at best), and counting
   PubChem against its own transcript as corroboration was
   rejected as verification theater.
5. Leading codes, trailing CI codes, and the global
   uncertain-parse downgrade on unbalanced input stay as
   documented limitations, not silent behavior.

### Consequences

- Systematic names survive the pipeline intact with no suite
  regressions; alias coverage grows through registration data,
  not code.
- Identifier resolution and the dual-agreement refusal are both
  regression-pinned, so future registry growth is checked in
  both directions (resolve what is registered; refuse what is
  not agreed).
- The verified path stays proven only on synthetic inputs until
  a genuine name+code label is sourced; the Frooti fixture
  documents exactly what such a label must contain.

**Rejected alternatives:**
- "Fixing" the normalizer output for locants: the damage happened
  upstream in the parser; patching downstream would leave split
  nodes and phantom identifiers in place.
- Splitting spaced digit-commas too (`1, 2`): genuinely
  list-like; only the unambiguous no-whitespace numeric run is
  protected.
- Marking the Frooti ingredient verified on identifier strength
  alone: contradicts the frozen dual-agreement rule this stage
  was asked to preserve.
- Adding PubChem live calls to manufacture a second record: the
  transcript IS PubChem; two records, one source, zero new
  corroboration.
