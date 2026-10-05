# LabelLens — Architecture Document

**Document:** ARCHITECTURE.md
**Project:** LabelLens
**Version:** 1.0
**Date:** 2026-10-04
**Status:** Active — MVP Definition

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Diagram](#2-system-diagram)
3. [Core Architectural Principles](#3-core-architectural-principles)
4. [Frontend Architecture](#4-frontend-architecture)
5. [Backend Architecture](#5-backend-architecture)
6. [Data Flow](#6-data-flow)
7. [Provider Adapter Pattern](#7-provider-adapter-pattern)
8. [Chemistry Engine](#8-chemistry-engine)
9. [Evidence and Confidence Layer](#9-evidence-and-confidence-layer)
10. [Database Architecture](#10-database-architecture)
11. [API Design](#11-api-design)
12. [Deployment Architecture](#12-deployment-architecture)
13. [Security Boundaries](#13-security-boundaries)
14. [Scalability Notes](#14-scalability-notes)
15. [Non-Functional Requirements](#15-non-functional-requirements)

---

## 1. Overview

LabelLens is a full-stack product-label intelligence application. It scans real-world product labels, extracts ingredient lists, resolves each ingredient to a verified chemical entity, computes chemistry where applicable, classifies product-domain roles, assembles claim-level evidence, generates grounded explanations, and supports product comparisons.

The application spans multiple product domains — food, supplements, cosmetics, cleaning products, and others — and is designed to make technically complex ingredient information understandable without asserting false certainty.

**One-line description:** LabelLens turns real-world product labels into understandable chemical information.

**What LabelLens is not:** a medical diagnosis system; an automatic "safe/unsafe" chemical judge; a replacement for regulators, doctors, pharmacists, toxicologists, or laboratory testing; a system permitted to invent chemistry when evidence is missing.

### Technology Stack

| Layer      | Technology                                      |
|------------|-------------------------------------------------|
| Frontend   | Next.js, TypeScript, Tailwind CSS               |
| Backend    | FastAPI, Python                                 |
| Database   | PostgreSQL via Supabase                         |
| Chemistry  | RDKit                                           |
| OCR        | Provider adapters (pluggable)                   |
| AI         | Provider adapters — Gemini, OmniRoute, or other |
| Frontend host | Vercel                                       |
| Backend host  | Python-capable free-tier host               |
| Storage    | Supabase Storage                                |

---

## 2. System Diagram

```text
┌──────────────────────────────────────────────────────────────────┐
│                          USER DEVICE                             │
│                                                                  │
│   ┌────────────────────────────────────────────────────────┐    │
│   │               Next.js Frontend (Vercel)                │    │
│   │                                                        │    │
│   │  Camera / File Upload → Scan UI → Ingredient View     │    │
│   │  Analysis View → Comparison View → Evidence Panel     │    │
│   │                                                        │    │
│   │  lib/api/ ─────────────────────────────────────────── │    │
│   │  (client.ts, scans.ts, ingredients.ts, analyses.ts,   │    │
│   │   comparisons.ts)                                      │    │
│   └─────────────────────────┬──────────────────────────── ┘    │
└─────────────────────────────│────────────────────────────────── ┘
                              │ HTTPS / JSON
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Python host)                  │
│                                                                  │
│  app/main.py  ─→  api/v1/ routers                               │
│                        │                                         │
│              ┌─────────▼──────────┐                             │
│              │    Validation       │  (Pydantic schemas)         │
│              └─────────┬──────────┘                             │
│                        │                                         │
│              ┌─────────▼──────────────────────────────┐         │
│              │            Business Services            │         │
│              │                                         │         │
│              │  ┌────────────┐  ┌──────────────────┐  │         │
│              │  │ ScanService│  │ OCRService        │  │         │
│              │  └────────────┘  └──────────────────┘  │         │
│              │  ┌────────────────────────────────────┐ │         │
│              │  │ ExtractionService                  │ │         │
│              │  └────────────────────────────────────┘ │         │
│              │  ┌─────────────────┐ ┌────────────────┐ │         │
│              │  │ NormalizationSvc│ │ EntityResolvSvc│ │         │
│              │  └─────────────────┘ └────────────────┘ │         │
│              │  ┌─────────────┐  ┌──────────────────┐  │         │
│              │  │ ChemistrySvc│  │ RoleService       │  │         │
│              │  └─────────────┘  └──────────────────┘  │         │
│              │  ┌─────────────┐  ┌──────────────────┐  │         │
│              │  │ EvidenceSvc │  │ ExplanationSvc    │  │         │
│              │  └─────────────┘  └──────────────────┘  │         │
│              │  ┌─────────────────────────────────────┐ │         │
│              │  │ ComparisonService                   │ │         │
│              │  └─────────────────────────────────────┘ │         │
│              └─────────────┬───────────────────────────┘         │
│                            │                                      │
│              ┌─────────────▼───────────────────────────┐         │
│              │           repositories/                  │         │
│              │  products, scans, ingredients,           │         │
│              │  claims, sources                         │         │
│              └─────────────┬───────────────────────────┘         │
└────────────────────────────│─────────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   PostgreSQL via Supabase    │
              │   + Supabase Storage         │
              └─────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Approved External Sources  │
              │   (behind adapter interfaces)│
              └─────────────────────────────┘

Provider Adapters (called by backend services only):
  ┌──────────────────────┐   ┌──────────────────────┐
  │   OCR Providers      │   │   AI Providers        │
  │   (adapter interface)│   │   (adapter interface) │
  └──────────────────────┘   └──────────────────────┘
```

---

## 3. Core Architectural Principles

These principles govern every design decision in LabelLens.

**1. Strict data-class separation.**
The following are distinct data classes and must never be collapsed into each other:

```text
Raw OCR text
  ≠ Extracted ingredient text
  ≠ Normalized ingredient
  ≠ Candidate entity
  ≠ Matched chemical entity
  ≠ Verified chemical facts
  ≠ Product-domain role
  ≠ AI-generated explanation
```

Each stage preserves its own provenance, confidence, and status. No stage silently inherits the trust level of another.

**2. AI is not a primary data source.**
AI providers (LLM-based) may generate structured candidates and explanations. They may not write directly to verified chemistry records. All AI output is observational until a human or deterministic process confirms it.

**3. Chemistry is deterministic and testable.**
The chemistry engine (RDKit) operates on validated inputs and produces auditable outputs. Every result carries the input representation, software version, calculation status, and provenance.

**4. External sources are behind adapter interfaces.**
No service calls an external provider SDK directly. All OCR, AI, and external chemistry source access goes through defined interface contracts. This isolates swap-out, testing, and failure handling.

**5. Secrets never reach the frontend.**
Provider API keys, database credentials, and other secrets are backend-only. No frontend environment variable exposes secrets to the browser.

**6. Typed validation at every boundary.**
FastAPI Pydantic schemas validate all incoming requests. Frontend TypeScript types mirror API response models. Untyped or unvalidated data does not enter the system.

**7. Free-first operation.**
The architecture does not require a paid AI or OCR call for every scan. Paths that resolve entities from the local database or cached sources incur no provider cost.

**8. Evidence is first-class.**
Claims, sources, and confidence are stored and returned as structured data — not as UI decorations. Evidence is an architectural layer, not an afterthought.

---

## 4. Frontend Architecture

The frontend is a Next.js application written in TypeScript, styled with Tailwind CSS, and deployed to Vercel.

### Directory Structure

```text
frontend/
└── src/
    ├── lib/
    │   └── api/
    │       ├── client.ts       ← base fetch wrapper, error normalization
    │       ├── scans.ts        ← scan create, get, OCR trigger
    │       ├── ingredients.ts  ← ingredient lookup
    │       ├── analyses.ts     ← analysis job, poll, result
    │       └── comparisons.ts  ← comparison create, get
    └── types/
        └── api.ts              ← shared TypeScript types mirroring API schemas
```

### API Client Layer

All backend communication is routed through `lib/api/`. Raw `fetch()` calls are not scattered across UI components. The client layer provides:

- A single error-normalization path that converts structured API error envelopes into typed errors.
- Request ID propagation from response metadata.
- Consistent handling of 4xx and 5xx status codes.

### State Strategy

Frontend state is divided into two categories that must not be conflated:

**Server state** — data owned by the backend, cached locally:
- Scans
- Analysis results
- Ingredients
- Sources
- Comparisons

**Local UI state** — ephemeral state that belongs to the UI only:
- Camera active/inactive
- OCR text editing mode
- Modal open/closed
- Selected ingredient
- Active filters

Canonical API data is not duplicated into multiple independent local states. Server state management (query/cache) is kept separate from UI event state.

### Real-Time / Async Operations

Long-running operations (OCR, analysis) follow a polling pattern:

```text
POST job → receive job_id
  ↓
poll GET /status until complete
  ↓
GET result
```

WebSockets and Server-Sent Events are not required for the MVP. They may be introduced later only if polling demonstrably degrades the user experience at scale.

---

## 5. Backend Architecture

The backend is a FastAPI application written in Python.

### Directory Structure

```text
backend/
├── app/
│   ├── main.py              ← app factory, middleware, router registration
│   ├── config.py            ← settings (env vars, provider config)
│   ├── dependencies.py      ← FastAPI dependency injection
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── health.py
│   │       ├── scans.py
│   │       ├── ingredients.py
│   │       ├── analyses.py
│   │       ├── comparisons.py
│   │       ├── products.py
│   │       ├── sources.py
│   │       └── search.py
│   │
│   ├── schemas/
│   │   ├── common.py        ← shared envelope, error, pagination types
│   │   ├── scan.py
│   │   ├── ingredient.py
│   │   ├── analysis.py
│   │   ├── chemistry.py
│   │   ├── evidence.py
│   │   └── comparison.py
│   │
│   ├── services/
│   │   ├── scan_service.py
│   │   ├── ocr_service.py
│   │   ├── extraction_service.py
│   │   ├── normalization_service.py
│   │   ├── entity_resolution_service.py
│   │   ├── chemistry_service.py
│   │   ├── role_service.py
│   │   ├── evidence_service.py
│   │   ├── explanation_service.py
│   │   └── comparison_service.py
│   │
│   ├── providers/
│   │   ├── ocr/             ← OCRProvider implementations
│   │   ├── ai/              ← AIProvider implementations
│   │   └── chemistry/       ← chemistry source adapters
│   │
│   ├── repositories/
│   │   ├── products.py
│   │   ├── scans.py
│   │   ├── ingredients.py
│   │   ├── claims.py
│   │   └── sources.py
│   │
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── contract/
│
├── migrations/
└── pyproject.toml
```

### Layering Rules

```text
Routers (api/v1/)
  ↓  validate with schemas/
  ↓  call services/
      ↓  call repositories/
          ↓  query PostgreSQL
      ↓  call providers/ (OCR, AI, chemistry)
          ↓  external adapter interfaces only
```

Routers do not call repositories directly. Repositories do not call providers. Cross-cutting concerns (auth, logging, rate limiting) are handled in middleware or FastAPI dependencies.

### Service Responsibilities

| Service                        | Responsibility                                                     |
|--------------------------------|--------------------------------------------------------------------|
| `scan_service`                 | Manage scan lifecycle, coordinate OCR and extraction               |
| `ocr_service`                  | Call the OCRProvider adapter, store raw observation                |
| `extraction_service`           | Parse raw OCR text into structured ingredient observations         |
| `normalization_service`        | Normalize ingredient text (spelling, abbreviations, aliases)       |
| `entity_resolution_service`    | Match normalized text to verified chemical entities                |
| `chemistry_service`            | Validate SMILES, compute descriptors, render structures            |
| `role_service`                 | Classify entity role within a product domain                       |
| `evidence_service`             | Assemble claims, sources, and confidence per entity                |
| `explanation_service`          | Generate grounded AI explanation from verified claims              |
| `comparison_service`           | Diff two or more products by ingredient, role, or chemistry        |

### Background Tasks

Long-running operations (OCR, full analysis) are handled as async background tasks in FastAPI. For the MVP, no external queue (Redis, Celery, Kafka) is introduced. Status is tracked in the database and polled by the frontend. A queue may be added later if the workload requires it.

---

## 6. Data Flow

The complete journey from label image to verified explanation:

```text
1.  USER uploads label image or enters text
        ↓
2.  FRONTEND sends multipart POST /api/v1/scans
        ↓
3.  VALIDATION  ← file type, MIME, size, dimensions checked
        ↓
4.  scan_service  creates scan record
        ↓
5.  ocr_service  calls OCRProvider adapter
        ↓  returns: text, confidence, regions, engine, model_version
6.  Observation stored as raw OCR text (immutable)
        ↓
7.  extraction_service  parses ingredient list from OCR text
        ↓  result: ingredient_observations (per ingredient, positional)
8.  normalization_service  normalizes each observation
        ↓  result: ingredient_normalizations (cleaned text, alias resolution)
9.  entity_resolution_service  matches normalized text to chemical_entities
        ↓  result: ingredient_candidates + entity_matches with match_status
10. chemistry_service  computes descriptors / validates SMILES (RDKit)
        ↓  result: chemical_properties, structures (deterministic, versioned)
11. role_service  classifies entity role per product domain
        ↓  result: entity_roles (e.g. preservative, emulsifier, solvent)
12. evidence_service  assembles claims + sources per entity
        ↓  result: claims, claim_sources (with confidence and freshness)
13. explanation_service  calls AIProvider adapter with verified claims only
        ↓  result: grounded explanation (status: grounded / partial / unsupported)
14. analysis_run  finalized in database
        ↓
15. FRONTEND fetches GET /api/v1/analyses/{analysis_id}
        ↓
16. USER views ingredients, roles, chemistry, evidence, explanation
```

Each transition is a discrete database record. No stage overwrites the previous stage's data. The system can reconstruct the full pipeline trail for any analysis.

---

## 7. Provider Adapter Pattern

All external integrations are accessed through internal interface contracts. No service in `services/` imports a provider-specific SDK directly. All provider-specific code lives under `providers/`.

### AI Provider Interface

```python
class AIProvider:
    async def generate_structured_candidate(...): ...
    async def generate_explanation(...): ...
```

Possible implementations:
- `providers/ai/gemini.py` — Gemini API
- `providers/ai/omniroute.py` — OmniRoute-routed models
- `providers/ai/local.py` — local model (future)

The rest of the application depends on the `AIProvider` interface, not any specific SDK. Swapping providers requires adding a new implementation class and updating configuration — no service code changes.

**Constraint:** AI providers may only be called by `explanation_service` and `entity_resolution_service` (for candidate generation). AI output is never written directly to `chemical_entities` or `claims` as verified data.

### OCR Provider Interface

```python
class OCRProvider:
    async def extract_label(...): ...
```

Returns a structured observation:

```json
{
  "text": "...",
  "confidence": "medium",
  "regions": [],
  "engine": "...",
  "model_version": "..."
}
```

OCR output is stored as an immutable observation record. It is never treated as verified ingredient data.

### Chemistry Provider Interface

The chemistry engine is accessed through `ChemistryService`, implemented with RDKit:

```python
class ChemistryService:
    def validate_smiles(...): ...
    def calculate_descriptors(...): ...
    def render_structure(...): ...
    def compare_structures(...): ...
```

Every chemistry result carries: input representation, software name, software version, calculation status, and provenance. RDKit runs locally — no external API call is required for chemistry calculations.

### Source Adapter Pattern

External reference sources (chemical databases, regulatory sources) are accessed through a source adapter layer rather than ad-hoc HTTP calls. Sources are registered in the Source Registry with a class (A–E), a status (approved / conditional / discovery_only / blocked / retired), and defined claim types for which they are appropriate. A source appropriate for chemical identity is not necessarily appropriate for regulatory status or medical interpretation.

---

## 8. Chemistry Engine

LabelLens uses RDKit as the local computational chemistry engine. RDKit is deterministic, open-source, and requires no external API call.

### Responsibilities

- **SMILES validation:** confirms a SMILES string represents a valid, parseable chemical graph.
- **Descriptor calculation:** computes molecular descriptors (molecular weight, topological polar surface area, H-bond donors/acceptors, rotatable bonds, and others as applicable) from a verified SMILES. Note: Chemical formula is stored as a canonical entity property sourced from an authoritative database, not computed by RDKit at analysis time.
- **Structure rendering:** generates 2D structure images for display.
- **Structure comparison:** compares two chemical structures for similarity.

### Constraints

- Chemistry calculations are only performed on entities with validated SMILES representations.
- When a SMILES string cannot be validated, the chemistry fields are set to null with a `CHEMISTRY_NOT_APPLICABLE` or `CHEMISTRY_CALCULATION_FAILED` status rather than using placeholder values.
- Chemistry results are stored with the RDKit version used, so results can be reproduced or re-computed when the library version changes.
- The chemistry engine does not produce safety verdicts, toxicity assessments, or medical conclusions.

### Chemistry Data Flow

```text
entity_match confirmed
  ↓
retrieve SMILES from chemical_entities
  ↓
validate_smiles() → valid / invalid
  ↓ (if valid)
calculate_descriptors() → molecular weight, TPSA, H-bond counts, etc.
render_structure() → SVG / PNG
  ↓
store chemical_properties with:
  - input: SMILES string
  - software: "rdkit"
  - software_version: "X.Y.Z"
  - status: computed / failed / not_applicable
  - provenance: entity source reference
```

---

## 9. Evidence and Confidence Layer

Evidence and confidence are architectural components, not UI decorations. Every important fact in LabelLens must have an identifiable evidence path, a meaningful confidence state, and a clear distinction between observed, verified, computed, inferred, and unknown.

### Trust Hierarchy

```text
Observation   ← raw, unverified (OCR text, user input)
  ↓
Extraction    ← structured but unverified
  ↓
Normalization ← cleaned, still unverified
  ↓
Candidate     ← proposed identity, not yet confirmed
  ↓
Verification  ← matched to a canonical source
  ↓
Claim         ← a specific verifiable factual statement
  ↓
Evidence      ← one or more claims with sources
  ↓
Confidence    ← derived from source class, freshness, match quality
  ↓
Explanation   ← grounded in verified claims only
```

An AI explanation is not allowed to skip this chain or assert facts that do not have corresponding claims.

### Claim-Level Evidence

Each important factual statement is a separate claim with its own evidence. For example, for a single ingredient these are distinct claims:

```text
Claim A: The ingredient is sodium benzoate.
Claim B: Its molecular formula is C7H5NaO2.
Claim C: Its SMILES is [Na+].[O-]C(=O)c1ccccc1.
Claim D: In food products it serves a preservative role.
Claim E: This product label contains it.
```

Claims A and E may have different confidence levels from Claim B or D. The system preserves this distinction rather than assigning a single confidence to an entire ingredient.

### Confidence States

Claims carry one of these verification statuses:

```text
verified      ← confirmed from authoritative source (class A)
supported     ← backed by high-quality reference (class B)
computed      ← derived deterministically (RDKit, formula calculation)
provisional   ← plausible but not yet fully confirmed
candidate     ← proposed, awaiting confirmation
unverified    ← no source confirmed yet
conflicted    ← sources disagree
unknown       ← information not available
obsolete      ← superseded by a newer record
```

### Evidence Service Contract

```python
class EvidenceService:
    async def get_claims(...): ...
    async def get_sources(...): ...
    async def validate_claim(...): ...
    async def assess_freshness(...): ...
```

Evidence logic is independent from AI explanation code. The explanation service receives pre-assembled, validated claims — it does not perform its own evidence retrieval.

### Source Registry Integration

Evidence sources are drawn from the approved Source Registry. Sources are classified by authority class:

| Class | Description                                    |
|-------|------------------------------------------------|
| A     | Primary / authoritative (government, official) |
| B     | High-quality scientific reference              |
| C     | Product / manufacturer                         |
| D     | Secondary reference                            |
| E     | Discovery only (not used as final evidence)    |

Source class feeds into confidence level. A claim backed only by a class D source carries lower confidence than one backed by a class A source.

---

## 10. Database Architecture

PostgreSQL via Supabase is the source of structured application truth.

### Central Rule

The database must never collapse the processing stages into a single `ingredients` text field. Raw observations, normalized data, verified scientific facts, contextual roles, computed values, and AI-generated explanations are different data classes and must remain distinguishable.

### Logical Architecture

```text
                       ┌───────────────┐
                       │    sources    │
                       └──────┬────────┘
                              │
                              ▼
┌──────────┐   ┌──────────────────────────┐
│ products │──▶│       product_scans      │
└────┬─────┘   └────────────┬─────────────┘
     │                      │
     │                      ▼
     │             ┌──────────────────────┐
     │             │ ingredient_observ.   │
     │             └──────────┬───────────┘
     │                        │
     │                        ▼
     │             ┌──────────────────────┐
     │             │ ingredient_candidates│
     │             └──────────┬───────────┘
     │                        │
     │                        ▼
     │             ┌──────────────────────┐
     │             │ entity_matches       │
     │             └──────────┬───────────┘
     │                        │
     │                        ▼
     │             ┌──────────────────────┐
     │             │ chemical_entities    │
     │             └──────────┬───────────┘
     │                        │
     │          ┌─────────────┼──────────────┐
     │          ▼             ▼              ▼
     │     structures     properties      roles
     │                        │              │
     │                        └──────┬───────┘
     │                               ▼
     │                           claims
     │                               │
     │                               ▼
     │                         claim_sources
     │                               │
     ▼                               ▼
analysis_runs ──────────────▶   evidence
     │
     ▼
analysis_items
     │
     ▼
comparisons
```

### Build Phases

The schema is introduced in six phases to keep the MVP manageable:

| Phase | Tables                                                                                              |
|-------|-----------------------------------------------------------------------------------------------------|
| 1     | `domains`, `roles`, `sources`, `chemical_entities`, `ingredient_aliases`                            |
| 2     | `products`, `product_labels`, `product_scans`, `ocr_runs`, `ingredient_observations`                |
| 3     | `ingredient_normalizations`, `ingredient_candidates`, `entity_matches`                              |
| 4     | `entity_roles`, `claims`, `claim_sources`, `chemical_properties`                                    |
| 5     | `analysis_runs`, `analysis_items`                                                                   |
| 6     | `comparisons`, `comparison_items`, `user_corrections`, `verification_events`                        |

### Key Conventions

- All primary keys are UUIDs generated database-side.
- All timestamps use `timestamptz`.
- Verification-relevant records carry `first_verified_at` and `last_verified_at` in addition to `created_at` / `updated_at`.
- Unknown values use `NULL` or explicit status fields — never fabricated placeholders.
- Historical scan observations are immutable once written.
- Chemical entity records are versioned and may evolve with new verifications.
- Row-Level Security (RLS) is enforced at the Supabase layer.

---

## 11. API Design

### Base URL

```text
/api/v1
```

Breaking changes require a version bump to `/api/v2`. Existing clients are not silently broken.

### Response Envelopes

All responses use consistent envelopes:

**Single resource:**
```json
{
  "data": {},
  "meta": {
    "request_id": "uuid",
    "api_version": "v1"
  }
}
```

**Collection:**
```json
{
  "data": [],
  "meta": {
    "request_id": "uuid",
    "api_version": "v1",
    "pagination": { "page": 1, "page_size": 20, "total": 100 }
  }
}
```

**Error:**
```json
{
  "error": {
    "code": "ENTITY_NOT_FOUND",
    "message": "The ingredient could not be confidently identified.",
    "details": { "observation_id": "uuid" }
  },
  "meta": {
    "request_id": "uuid",
    "api_version": "v1"
  }
}
```

Raw provider error text is never returned to clients.

### Core Endpoints

| Method | Path                                    | Description                          |
|--------|-----------------------------------------|--------------------------------------|
| GET    | `/api/v1/health`                        | Health check                         |
| POST   | `/api/v1/scans`                         | Create a new scan (image upload)     |
| GET    | `/api/v1/scans/{scan_id}`               | Get scan record                      |
| POST   | `/api/v1/scans/{scan_id}/ocr`           | Trigger OCR on a scan                |
| POST   | `/api/v1/scans/{scan_id}/analyze`       | Trigger full analysis pipeline       |
| GET    | `/api/v1/analyses/{analysis_id}`        | Get analysis result                  |
| GET    | `/api/v1/ingredients/{ingredient_id}`   | Get ingredient detail with evidence  |
| POST   | `/api/v1/comparisons`                   | Create a product comparison          |
| GET    | `/api/v1/comparisons/{comparison_id}`   | Get comparison result                |
| GET    | `/api/v1/sources`                       | List approved sources                |
| GET    | `/api/v1/search`                        | Search ingredients / entities        |

### Request IDs

Every request receives a unique `X-Request-ID`. It is included in logs, errors, and response metadata.

### File Upload Validation

Image uploads validate: MIME type, file extension, file size, image dimensions, and file signature. The filename alone is never trusted.

---

## 12. Deployment Architecture

```text
┌──────────────────┐         ┌──────────────────────┐
│  Vercel          │         │  Python-capable host  │
│  (Frontend CDN)  │ ──────▶ │  (FastAPI backend)    │
│  Next.js         │  HTTPS  │  Free-tier            │
└──────────────────┘         └──────────┬────────────┘
                                        │
                                        ▼
                             ┌──────────────────────┐
                             │  Supabase            │
                             │  PostgreSQL + Storage│
                             └──────────────────────┘
```

### Principles

- **Free-first.** The baseline deployment uses Vercel free tier, a free-tier Python host, and Supabase free tier. No paid services are required to run the application at low volume.
- **No paid AI call per scan.** Scans that resolve entirely from the local database incur no provider cost. AI calls are made only when needed for candidate generation or explanation.
- **No infrastructure overhead at MVP.** No Redis, no Celery, no Kafka, no separate worker cluster. Background tasks run within the FastAPI process using Python async. This constraint is revisited if workload requires it.
- **Supabase Storage** holds label images. The backend retrieves images from Storage to pass to the OCR provider — images are not held in memory longer than needed.

### Environment Separation

Backend secrets (provider API keys, database credentials) are set as server environment variables. The frontend holds no secrets. CORS is restricted to the known frontend origin. Security headers are applied.

---

## 13. Security Boundaries

### No Secrets in the Frontend

Provider keys, database connection strings, and internal tokens are backend-only. Next.js public environment variables (`NEXT_PUBLIC_*`) must never contain secrets. All authenticated API calls are proxied through the FastAPI backend.

### Input Validation

- Every HTTP request body is validated against a Pydantic schema before reaching service code.
- File uploads are validated for type, size, dimensions, and magic bytes.
- Unvalidated data never enters the service layer.

### Prompt Injection Protection

AI provider calls are constructed from verified, structured data — not from raw user input or raw OCR text. The explanation service assembles prompts from pre-validated claims. Raw label text is never interpolated directly into a prompt.

### Database Security

- Row-Level Security (RLS) is enforced at the Supabase layer.
- The API returns stable public response models, not raw database table rows.
- Internal sequential IDs are not exposed in public URLs; UUIDs or application-level short IDs are used.

### CORS

CORS is restricted to the known frontend origin. Wildcard origins are not used in production.

### HTTP Security Headers

Security headers (Content-Security-Policy, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and others) are set on all responses.

### Rate Limiting

Rate limiting is applied at the API level. The `RATE_LIMITED` error code (HTTP 429) is returned for clients exceeding limits.

### No Medical or Safety Verdicts

The architecture enforces that no service, endpoint, or response model produces medical advice, safety verdicts, or toxicity conclusions. This is not a UI policy — it is enforced in the service and schema layers.

---

## 14. Scalability Notes

The MVP architecture is deliberately minimal. Scalability extensions are defined here for reference but are not built until demonstrated need.

### Horizontal Scaling

The FastAPI backend is stateless. Horizontal scaling requires only a load balancer in front of multiple backend instances. Session state is not stored in-process.

### Database

Supabase (PostgreSQL) handles typical LabelLens workloads comfortably at MVP scale. Indexes on frequently queried columns (scan status, entity match status, analysis run status) are defined in schema migrations. If read load increases, Supabase read replicas or PgBouncer connection pooling can be added without schema changes.

### Provider Adapter Swap

Because all OCR and AI providers are behind adapter interfaces, swapping to a higher-throughput or lower-cost provider requires adding a new implementation class — no service code changes. This isolates provider scaling decisions from application logic.

### Background Jobs

If analysis pipeline latency becomes a user experience problem at volume, the background task model can be migrated to a dedicated queue (e.g., a lightweight task queue backed by PostgreSQL) without changes to the service layer. The job/poll/result pattern used by the frontend is already queue-compatible.

### Chemistry Engine

RDKit runs in-process. If chemistry calculation becomes a throughput bottleneck, it can be extracted into a separate worker without changing the `ChemistryService` interface.

### Caching

Repeated entity resolution and chemistry calculations for known ingredients can be cached at the repository layer. Because the chemistry engine is deterministic, cached results are safe to reuse for the same SMILES input and RDKit version. Cache invalidation is triggered by entity record updates.

---

## 15. Non-Functional Requirements

| Requirement          | Approach                                                                              |
|----------------------|---------------------------------------------------------------------------------------|
| Mobile-first         | Tailwind CSS responsive design; camera/image capture as a primary input path          |
| Typed validation     | Pydantic (backend), TypeScript types (frontend) at all boundaries                     |
| Graceful failures    | Partial results returned when safe; explicit status fields for every pipeline stage   |
| Safe retries         | Write operations support idempotency keys; polling pattern is inherently retry-safe   |
| Security headers     | Applied on all API responses; CSP on frontend                                         |
| RLS                  | Enforced at Supabase layer for all data access                                        |
| Prompt injection     | AI prompts constructed from structured verified data, not raw user/OCR text           |
| No frontend secrets  | All provider keys and credentials are server-side only                                |
| CORS restricted      | Production CORS limited to known frontend origin                                      |
| Auditability         | Every pipeline stage is a distinct immutable-or-versioned database record             |
| Testability          | Chemistry engine is deterministic; provider adapters are mockable; contract tests exist for API boundaries |
| OpenAPI docs         | FastAPI generates OpenAPI documentation from typed schemas automatically              |

---

*End of ARCHITECTURE.md*
