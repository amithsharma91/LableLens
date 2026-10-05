# LabelLens — Portfolio Case Study

**Date:** 2026-10-04
**Author:** 1st-year B.Tech CSE (GenAI) + Computational Chemistry student
**Positioning:** A computational-chemistry-powered product intelligence platform combining OCR, chemical entity resolution, molecular data, evidence provenance, domain-aware role classification, comparison, and explainable AI.

---

## Table of Contents

1. [Problem](#1-problem)
2. [User](#2-user)
3. [Product](#3-product)
4. [Architecture](#4-architecture)
5. [Chemistry Methodology](#5-chemistry-methodology)
6. [Data Pipeline](#6-data-pipeline)
7. [AI Boundaries](#7-ai-boundaries)
8. [Screenshots](#8-screenshots)
9. [Accuracy & Testing](#9-accuracy--testing)
10. [Deployment](#10-deployment)
11. [Challenges](#11-challenges)
12. [Design Decisions](#12-design-decisions)
13. [Limitations](#13-limitations)
14. [Future Work](#14-future-work)

---

## 1. Problem

Every day, people pick up a product — shampoo, sunscreen, a protein bar — flip it over, and stare at a wall of ingredient names they cannot parse. The average cosmetic label lists 20–40 INCI names; a household cleaner might carry proprietary trade names, pH buffers, and surfactant blends. The information exists, scattered across PubChem, ECHA, CosIng, academic papers, and safety databases, but nobody has assembled it into something a curious non-chemist can actually use.

Existing tools either require manual entry, stop at a glossary definition, or make sweeping safety pronouncements without showing their work. The gap is a product that:

- reads a real label from a photo
- resolves each ingredient to real chemical data
- honestly represents what is known, what is uncertain, and what is missing
- shows every claim's source

That is the problem LabelLens is built to solve.

---

## 2. User

The primary user is an **informed consumer** — someone already motivated enough to read a label, who wants a layer of intelligence beyond marketing copy. Secondary users include:

- **Students and educators** exploring applied chemistry or toxicology
- **Formulators and product developers** doing competitive research
- **Technical portfolio reviewers** evaluating engineering and chemistry depth

LabelLens is explicitly **not** for users seeking a medical diagnosis, a regulatory ruling, or a safety certification. That boundary is a design decision, not a gap.

---

## 3. Product

The core promise is simple: **scan a product label → understand what is inside → understand the chemistry → compare products → explore the evidence.**

LabelLens delivers that promise across five surfaces:

| Surface | What it does |
|---|---|
| **Scan / Upload** | Camera or file upload; OCR extracts the ingredient list |
| **Ingredient Cards** | Per-ingredient molecular data, role classification, and multi-dimensional confidence |
| **Evidence Panel** | Every fact linked to its source, with authority class and licensing stance |
| **Comparison View** | Side-by-side ingredient breakdown across two scanned products |
| **Explainability Layer** | AI-generated plain-English summaries, bounded by what the data actually supports |

Unknown and unverified states are first-class UI states — they are shown to the user, not hidden.

---

## 4. Architecture

LabelLens is a full-stack web application with a deliberately modular backend. Each stage in the pipeline is a separate, independently testable service boundary.

```
┌─────────────────────────────────────────────────────────┐
│                        Client                           │
│          Next.js + TypeScript  /  Tailwind CSS            │
└───────────────────┬─────────────────────────────────────┘
                    │ REST / JSON
┌───────────────────▼─────────────────────────────────────┐
│                    API Layer (FastAPI)                   │
│   /scan   /ingredient   /compare   /evidence            │
└───┬───────────────┬──────────────────┬──────────────────┘
    │               │                  │
┌───▼───┐    ┌──────▼──────┐    ┌──────▼──────┐
│  OCR  │    │  Resolver   │    │  Comparator │
│ Stage │    │  Pipeline   │    │   Service   │
└───┬───┘    └──────┬──────┘    └─────────────┘
    │               │
    │    ┌──────────▼──────────────────────────┐
    │    │        9-Stage Intelligence          │
    │    │        Pipeline (see §6)             │
    │    └──────────┬──────────────────────────┘
    │               │
    │    ┌──────────▼──────────────────────────┐
    │    │       Chemistry Layer               │
    │    │   RDKit  │  PubChem  │  ECHA/CosIng │
    │    └─────────────────────────────────────┘
    │
┌───▼────────────────┐
│  Confidence Store  │
│  (multi-dimension) │
└────────────────────┘
```

**Stack at a glance:**

- **Frontend:** Next.js, TypeScript, Tailwind CSS
- **Backend:** Python, FastAPI
- **Chemistry:** RDKit (local, deterministic), PubChem API, ECHA/CosIng lookups
- **OCR:** Tesseract / cloud Vision API with preprocessing
- **Storage:** PostgreSQL for resolved ingredient cache; flat-file golden dataset for testing
- **Deployment:** Vercel (frontend), free-tier Python host (backend), Supabase (PostgreSQL + Storage)

---

## 5. Chemistry Methodology

The chemistry layer is the heart of LabelLens and the primary differentiator from a glorified glossary app.

### 5.1 Entity Type Model

Not every ingredient is a discrete molecule. LabelLens recognises 9 canonical representation types and never forces a SMILES string onto something that does not logically have one:

| Entity Type | Example | Treatment |
|---|---|---|
| `single_molecule` | Retinol | Full structure, formula, descriptors |
| `salt` | Sodium Benzoate | Full structure, formula, descriptors |
| `polymer` | Carbomer | Repeat unit where available; no single SMILES by default |
| `material` | Silica | Material description; no organic structure |
| `mixture` | Aqua (water trace mineral mix) | Composition if known, else documented uncertainty |
| `natural_complex` | Lavender extract | Marker compounds; no single identity |
| `formulation` | Emulsifying wax NF | Constituent breakdown if published |
| `trade_name` | Tego Betain (INCI alias) | Resolved to INCI or flagged unresolved |
| `unknown` | Undecipherable text | Explicit unknown state, no SMILES |

### 5.2 Deterministic Chemistry with RDKit

SMILES strings, molecular formulas, and computed descriptors (MW, TPSA, H-bond counts) are produced exclusively by RDKit from verified input structures. The AI layer is never asked to generate or modify SMILES. If a structure cannot be found in a trusted source, the field is left empty with an explicit `unverified` state rather than fabricated. RDKit validates that a SMILES string is syntactically and chemically parseable; it does not prove that the label ingredient actually corresponds to that molecule. Identity verification requires authoritative source confirmation.

### 5.3 Role Classification

Each ingredient receives a domain-aware functional role from a controlled vocabulary (e.g., `humectant`, `surfactant`, `preservative`, `UV-filter`, `fragrance`, `solvent`). Role assignments carry a confidence score and a source reference. Where multiple roles are plausible, all are surfaced.

### 5.4 Evidence Provenance

Every data point — a safety classification, a regulatory listing, a biological activity claim — is linked to a specific source via the source registry. The registry records:

- Source authority class (regulatory, peer-reviewed, industry database, curated wiki)
- Jurisdiction (EU, US, global)
- Licensing stance (open, attribution, restricted)
- Retrieval timestamp

This makes the provenance auditable, not just decorative.

---

## 6. Data Pipeline

The ingredient intelligence pipeline has 9 sequential, independently auditable stages:

```
Stage 1 │ Raw OCR output
        │   ↓ preprocessing + denoising
Stage 2 │ Cleaned text block
        │   ↓ ingredient list segmentation
Stage 3 │ Candidate ingredient tokens
        │   ↓ INCI / synonym normalisation
Stage 4 │ Normalised names
        │   ↓ entity type classification
Stage 5 │ Typed entities
        │   ↓ external database resolution (PubChem, ECHA, CosIng)
Stage 6 │ Resolved identities + CIDs / InChIKeys
        │   ↓ RDKit structure processing
Stage 7 │ Molecular data (structure, formula, descriptors)
        │   ↓ role classification + evidence fetch
Stage 8 │ Annotated ingredient records
        │   ↓ AI summary generation (bounded prompt)
Stage 9 │ Explainable ingredient cards with confidence scores
```

Each stage emits a **stage-level confidence score**. The final per-ingredient confidence is multi-dimensional:

| Dimension | What it measures |
|---|---|
| `ocr_confidence` | Character-level OCR certainty |
| `extraction_confidence` | Segmentation correctness |
| `normalisation_confidence` | INCI / synonym match quality |
| `identity_confidence` | Database match strength |
| `structure_confidence` | SMILES / InChI validity |
| `formula_confidence` | Molecular formula agreement |
| `role_confidence` | Functional role assignment certainty |
| `evidence_confidence` | Source authority and recency |

This vector is exposed in the UI and stored for testing, so confidence degradation is visible and traceable.

---

## 7. AI Boundaries

LabelLens uses a large language model for one purpose: generating plain-English summaries of what a resolved ingredient is, what it does in a formulation, and what the evidence says. The AI is given only what the pipeline has already verified; it cannot reach external sources during generation.

**Hard constraints on the AI layer:**

- May not generate or modify SMILES strings
- May not assert a safety classification not present in the evidence record
- May not claim regulatory approval or disapproval without a source
- May not provide medical advice or diagnosis
- Must hedge appropriately when evidence confidence is low
- Output is templated and post-processed to strip disallowed claim patterns

**What the AI is allowed to do:**

- Paraphrase a confirmed functional role in plain English
- Summarise peer-reviewed findings already in the evidence record
- Note when evidence is sparse or conflicting
- Explain why a confidence score is low

This is an explicit architectural decision: the AI makes the data more readable, but the data comes from chemistry, not from the AI.

---

## 8. Screenshots

*Screenshots will be added once the UI is stable. Placeholders below reflect the intended surfaces.*

[Screenshot: Home / scan screen — camera upload widget and "paste ingredient list" toggle]

[Screenshot: Ingredient card — molecule name, entity type badge, SMILES viewer, role tags, confidence bar]

[Screenshot: Evidence panel — source list with authority class icons and claim-to-source links]

[Screenshot: Comparison view — two product columns with shared ingredient highlighting]

[Screenshot: Low-confidence state — ingredient card showing "unverified" badge with explanation]

[Screenshot: Mobile layout — compact card stack with expandable chemistry detail]

---

## 9. Accuracy & Testing

### 9.1 Golden Dataset

A curated golden dataset of labelled ingredient records is maintained alongside the codebase. Each record contains:

- Expected normalised name
- Expected entity type
- Expected CID / InChIKey (where applicable)
- Expected role(s)

**Note:** All 100 entries in the golden dataset are candidate seeds with status `needs_verification`. They are not verified facts and must be validated against approved authoritative sources before use as factual tests in production. Tests run against the golden dataset to evaluate candidate matching and schema completeness, not absolute chemical truth.

### 9.2 Current Accuracy Posture

Accuracy figures are reported only for measured subsets, never claimed universally. As of this writing:

- The golden dataset covers a representative but not exhaustive sample of INCI names from cosmetic and household categories.
- OCR accuracy is highly image-quality-dependent; controlled test images show strong performance; real-world photos of crumpled or reflective labels score lower.
- Resolution accuracy (Stage 6) depends on PubChem/ECHA coverage; less common trade names or novel actives may be unresolved.
- Role classification confidence is higher for well-documented actives and lower for proprietary blends.

These numbers will be published in a test report alongside the repository as the dataset grows.

### 9.3 Testing Approach

| Test type | What it covers |
|---|---|
| Unit tests | Individual pipeline stage transformations |
| Integration tests | Stage-to-stage data contracts |
| Golden dataset regression | End-to-end pipeline accuracy |
| Confidence calibration | Expected vs actual confidence alignment |
| AI boundary tests | Prompt output contains no disallowed claim patterns |

---

## 10. Deployment

**Deployment targets:**

- **Frontend:** Vercel (Next.js serverless functions + edge caching)
- **Backend:** Free-tier Python host (e.g., Render, Railway) for FastAPI and RDKit
- **Database:** Supabase (managed PostgreSQL + Object Storage)

**Free-first architecture:** The chemistry data sources (PubChem, ECHA CosIng via the public API) are free to access within rate limits. RDKit runs locally. The AI summary layer uses a configurable provider; the system degrades gracefully to data-only cards when no AI key is configured.

No production-scale load testing has been performed. The current architecture is appropriate for a portfolio demo and single-user exploration workloads.

---

## 11. Challenges

### OCR Quality in the Wild

Label text is typeset in small fonts on curved, glossy, or textured surfaces. Preprocessing (adaptive thresholding, deskew, contrast enhancement) improves results, but a blurry photo of a crinkled label still produces noisy tokens that downstream stages must handle gracefully. The pipeline degrades gracefully — a low OCR confidence score is propagated through the chain rather than silently corrupted.

### Trade Names and Mixtures

A significant fraction of cosmetic and household ingredients are trade names (e.g., "Tego Betain F 50") or proprietary mixtures with no single INCI entry. Forcing these into a molecular identity would be scientifically wrong. The entity type model (§5.1) was designed specifically to handle this; the harder challenge was making the UI communicate "this ingredient is a mixture and here is what is known about its components" without feeling like a failure state.

### Avoiding Hallucination Without Crippling AI Usefulness

The AI layer is useful for readability but dangerous if unconstrained. The solution was a bounded prompt architecture: the model receives only pre-verified data and is evaluated against a disallowed-claim pattern list. This required iteration — early prompts would occasionally infer safety conclusions not in the source data. The pattern filter now catches these.

### Free-First Chemistry Data

PubChem is comprehensive but has rate limits and occasional coverage gaps for newer actives. ECHA CosIng is authoritative for EU cosmetics but structured differently. Building a source registry that abstracts over these differences while preserving provenance took more design effort than the integrations themselves.

### Regulatory Data Is a Moving Target

Regulatory status is jurisdiction-specific, subject to revision, and cannot be cached indefinitely. The current architecture timestamps every retrieval and flags records older than a configurable staleness threshold. This is an honest partial solution — it surfaces the uncertainty rather than pretending the data is always current.

---

## 12. Design Decisions

**Confidence as a first-class value, not a footnote.** Most ingredient tools show a result or say "not found." LabelLens shows a multi-dimensional confidence vector for every ingredient, making uncertainty explicit and navigable. This was a deliberate product choice: a user who understands why confidence is low can decide what to do with that; a user who sees a wrong answer with no caveat cannot.

**Separate pipeline stages over a monolithic resolver.** Each of the 9 stages is independently testable and replaceable. This cost more upfront design time but makes the system debuggable — when an ingredient resolves incorrectly, the confidence scores point to which stage failed.

**RDKit for structure, AI for prose.** Separating deterministic chemistry from language generation prevents the most dangerous failure mode: an AI-invented structure presented as fact. The cost is that the AI cannot fill gaps the chemistry layer leaves open; the benefit is that every structure in the system is verified.

**Unknown as a valid UI state.** Displaying "unverified" or "resolution failed" prominently was uncomfortable to design but scientifically necessary. The alternative — hiding gaps — would make LabelLens look more polished while being less honest.

**Source registry with authority classes.** Not all sources are equal. A peer-reviewed toxicology study and a crowd-edited wiki both have a role, but they carry different weight. Encoding this distinction in the registry, rather than flattening all sources to a list of links, preserves the quality signal.

---

## 13. Limitations

These are documented honestly, not apologetically.

- **Ingredient coverage is incomplete.** PubChem and CosIng are broad but not exhaustive. Novel actives, regional trade names, and proprietary blends may not resolve.
- **Regulatory status cannot be guaranteed current.** Data is timestamped and staleness-flagged, but LabelLens is not a live regulatory feed.
- **OCR accuracy depends on image quality.** Controlled images work well; real-world label photos with glare, curvature, or damage produce lower accuracy.
- **No medical advice.** LabelLens surfaces chemical and functional data. It does not diagnose, prescribe, or assess individual safety.
- **Comparison is limited to scanned labels.** The comparison view works only on ingredients that appeared on a captured label; it cannot infer full formulations from a product name alone.
- **Golden dataset requires ongoing human verification.** Automated tests catch regressions, but adding new ingredient categories requires expert annotation.
- **Not production-scale tested.** Suitable for demo and personal exploration; not load-tested for high concurrency.

---

## 14. Future Work

The following are planned extensions, not current features:

- **Barcode / QR lookup** — resolve a product by scanning its barcode to pre-populate the ingredient list without OCR
- **User accounts and scan history sync** — persistent history across devices
- **Advanced chemical similarity search** — find structurally similar ingredients across the resolved database using RDKit fingerprints
- **Inline molecular visualization** — 3D conformation viewer (3Dmol.js or similar) on the ingredient card
- **ML-assisted role classification** — a trained classifier to supplement the rule-based role assignment, with the rule-based layer as a fallback
- **Multi-language label support** — INCI names are mostly Latin, but product-language parsing (French, German, Japanese) would expand coverage
- **PWA / offline support** — cache resolved ingredient records for offline lookup after first scan
- **Expanded regulatory coverage** — US FDA Cosmetics Database, Health Canada, ASEAN CosIng integrations

---

## Closing Note

LabelLens was built as a first-year portfolio project to demonstrate that product thinking, full-stack engineering, computational chemistry, data quality discipline, explainable AI, and honest system design can coexist in a single application. It does not claim to be a finished product, a medical tool, or an authoritative chemistry reference. It claims to be an honest, auditable, technically rigorous attempt to make product label chemistry legible — and to show its work at every step.
