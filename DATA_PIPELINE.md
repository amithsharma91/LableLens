# LabelLens Data Pipeline — Technical Reference

**Version:** 1.0  
**Date:** 2026-10-04  
**Scope:** End-to-end chemistry and evidence data pipeline from label image to user explanation.

---

## Overview

The LabelLens pipeline transforms a product label image into verified, evidence-backed chemical explanations. It is a strict, linear sequence of 10 stages. **No stage may silently overwrite the previous stage.** Each stage appends its output; prior stage artifacts are preserved for audit and debugging.

```
Label image
    │
    ▼ Stage 1
  OCR output (raw_text, confidence, engine)
    │
    ▼ Stage 2
  Extracted ingredient list
    │
    ▼ Stage 3
  User-corrected text (optional; original preserved)
    │
    ▼ Stage 4
  Normalized candidate strings
    │
    ▼ Stage 5
  Resolved entity candidates (with match status)
    │
    ▼ Stage 6
  Verified chemical record (all quality gates passed)
    │
    ▼ Stage 7
  Computed descriptors via RDKit (where applicable)
    │
    ▼ Stage 8
  Domain-specific role assignment
    │
    ▼ Stage 9
  Evidence + confidence assembly (claim-level)
    │
    ▼ Stage 10
  Grounded user explanation
```

---

## Stage 1 — OCR

### Purpose
Convert a label image into machine-readable text.

### Input
- Raw image (JPEG, PNG, or similar raster image formats)
  - Note: PDF and active document formats (DOCX, SVG with embedded scripts, HTML) are not accepted in MVP per API security policy. PDF support is post-MVP only.

### Output contract

```json
{
  "raw_text": "string",
  "overall_confidence": "clear | readable | uncertain | poor | unusable",
  "bounding_regions": [
    { "text": "string", "bbox": [x1, y1, x2, y2], "confidence": "float 0–1" }
  ],
  "engine": "string",
  "model_version": "string",
  "timestamp": "ISO 8601"
}
```

`bounding_regions` is included when the engine provides it; omitted otherwise, never synthesized.

### Confidence states

| State | Meaning |
|-------|---------|
| `clear` | High-confidence, unambiguous recognition |
| `readable` | Recognizable with minor uncertainty |
| `uncertain` | Partial recognition; downstream stages must flag |
| `poor` | Low confidence; user review strongly recommended |
| `unusable` | Cannot proceed without user correction |

### Preservation requirements
- Raw recognized text must be stored as-is — no cleaning, no normalization at this stage.
- Engine name and model version must be recorded so results are reproducible.
- Timestamp is required for cache invalidation and audit.

### Quality gate (OCR → Stage 2)
- If `overall_confidence` is `poor` or `unusable`, the OCR uncertainty **must be surfaced to the user before any analysis proceeds**.
- The user must have the opportunity to correct or reject the OCR output.

### Forbidden behaviors
- Do not normalize, spell-check, or alter `raw_text`.
- Do not infer missing characters or words.
- Do not proceed silently past `poor` or `unusable` confidence.

---

## Stage 2 — Ingredient Extraction

### Purpose
Parse `raw_text` into a structured list of candidate ingredient strings.

### Input
- `raw_text` from Stage 1 (or user-corrected text from Stage 3, if already applied)
- `source_type`: one of `ocr | user_entered | user_corrected | manual`

### Output contract

```json
{
  "ingredients": [
    {
      "raw_string": "string",
      "position": "integer (ordinal in list)",
      "source_type": "ocr | user_entered | user_corrected | manual",
      "extraction_confidence": "float 0–1"
    }
  ],
  "extraction_method": "string",
  "extraction_confidence": "float 0–1"
}
```

### Example
Input: `"Ingredients: water, sugar, citric acid (330), sodium benzoate"`  
Output: `["water", "sugar", "citric acid (330)", "sodium benzoate"]`

### Important separation of concerns
Extraction confidence is independent of OCR confidence. A perfectly recognized label (`clear` OCR) can still yield a poorly extracted list if the formatting is unusual. These two confidence values must never be merged or conflated.

### Quality gate (Stage 2 → Stage 3/4)
- Extraction confidence is tracked separately from OCR confidence throughout all downstream stages.
- A low extraction confidence should be flagged; the user may need to manually verify the list.

### Forbidden behaviors
- Do not interpret, normalize, or look up chemical identity at this stage.
- Do not drop ingredients silently — if extraction is uncertain for a particular item, retain it with a low confidence score rather than omitting it.

---

## Stage 3 — User Correction

### Purpose
Allow the user to fix OCR mistakes before downstream chemical analysis.

### Input
- `raw_text` from Stage 1
- User-provided corrections

### Output contract

```json
{
  "original_ocr_text": "string",
  "corrected_text": "string",
  "correction_timestamp": "ISO 8601",
  "corrections": [
    {
      "original": "string",
      "corrected": "string",
      "reason": "string (optional, user-provided)"
    }
  ]
}
```

### Scope of correction
A user correction **improves the text input only**. It does not:
- Establish chemical formula
- Establish molecular structure
- Establish regulatory status
- Establish product role

These remain the responsibility of Stages 5–8 with verified sources.

### Preservation requirement
The original OCR text is always stored alongside the correction. Corrections are never applied destructively.

### Forbidden behaviors
- Do not treat a user-typed name as a verified chemical identity.
- Do not skip entity resolution because the user "typed it correctly."

### Stage-13 implementation note (2026-10-05)
Stage 3 is implemented as `ObservationService.correct` (service
layer only, no route): the original `raw_text` is immutable (moved
to `original_text` on first correction), the corrected reading is
stored in `display_text` with `user_corrected`, `correction_reason`,
and the `user_corrected` source type, and a fresh normalization row
is persisted for the corrected text so the pre-correction row stays
as history. Analysis and reads use the latest normalization
(`display_text or raw_text`). Exactly one revision per observation
is allowed -- a second correction is refused, so there is no silent
correction chain. Demonstrated on a documented real-label case
(Listerine `Saccharin Sodium` -> `Sodium Saccharin`, both SPL
readings cited) in `STAGE_13_REAL_LABEL_VERTICAL_SLICE.md`.

---

## Stage 4 — Normalization

### Purpose
Convert raw or corrected ingredient strings into a canonical form suitable for entity lookup.

### Input
- `raw_string` from Stage 2 (or corrected text from Stage 3)

### Output contract

```json
{
  "normalized_text": "string",
  "normalization_method": "rule | dictionary | database_alias | model_candidate | manual | hybrid",
  "normalization_confidence": "float 0–1",
  "status": "complete | partial | failed"
}
```

### Normalization methods

| Method | Description |
|--------|-------------|
| `rule` | Pattern-based cleaning (remove parenthetical codes, lowercase, strip punctuation) |
| `dictionary` | Lookup in a curated synonym/alias dictionary |
| `database_alias` | Match to known aliases from an authoritative source (PubChem, ChEBI, etc.) |
| `model_candidate` | NLP/ML model generates candidate normalized form |
| `manual` | Human-entered normalization |
| `hybrid` | Combination of the above methods |

### Critical distinction
**Normalized text ≠ chemical identity.** Normalization produces a cleaner string for lookup; it does not confirm that the entity exists, what its structure is, or whether it is a single compound.

### Quality gate (Stage 4 → Stage 5)
- Normalization status must be `complete` (or `partial` with noted limitations) before proceeding to entity resolution.
- Multiple candidate normalized forms are allowed and should all be carried forward as candidates.

### Forbidden behaviors
- Do not treat a normalized string as a verified chemical name.
- Do not collapse multiple candidate normalizations prematurely.

---

## Stage 5 — Entity Resolution

### Purpose
Map a normalized string to a specific, identifiable chemical entity (or flag ambiguity).

### Input

```json
{
  "normalized_text": "string",
  "domain": "food | cosmetic | household | pharmaceutical",
  "context": { "country": "string", "product_type": "string" },
  "identifiers": ["CAS", "E-number", "INS number", "INCI name", "..."]
}
```

### Output contract

```json
{
  "match_status": "exact_match | strong_match | probable_match | ambiguous | no_match | invalid_input",
  "confidence": "float 0–1",
  "candidates": [
    {
      "entity_id": "string",
      "name": "string",
      "source": "string",
      "match_signals": ["string"]
    }
  ],
  "reasons": ["string"]
}
```

### Match status definitions

| Status | Meaning |
|--------|---------|
| `exact_match` | Unambiguous, single entity confirmed by identifier or authoritative name |
| `strong_match` | High confidence single entity; multiple corroborating signals |
| `probable_match` | Likely correct but not fully confirmed |
| `ambiguous` | Multiple plausible entities; cannot resolve without more information |
| `no_match` | No suitable entity found in searched sources |
| `invalid_input` | Input is malformed, empty, or not resolvable |

### Match signals
The following signals contribute to match confidence:

- Normalized name match against authoritative source
- Exact identifier match (CAS number, E-number, INS number, INCI name)
- Recognized food additive number (E-xxx, INS xxx)
- Known alias or synonym from a curated source
- Domain and context agreement (ingredient plausible for this product type)
- Source database match (PubChem CID, ChEBI ID confirmed)
- Structure/identifier agreement (SMILES and InChI resolve to the same entity)

### Multiple candidates
When the input is ambiguous (e.g., a common name that maps to multiple entities), all plausible candidates are returned. **Ambiguous inputs must never be promoted to a verified entity without additional evidence.**

### Quality gate (Stage 5 → Stage 6)
- `match_status` of `ambiguous`, `no_match`, or `invalid_input` blocks promotion to verified.
- At least `probable_match` with sufficient corroborating signals is required to enter the validation gates.

### Forbidden behaviors
- Do not pick a single candidate arbitrarily from an ambiguous result.
- Do not treat a name match alone (without at least one corroborating signal) as sufficient for `exact_match`.

---

## Stage 6 — Chemical Entity Validation

### Purpose
Ensure a candidate entity meets all required quality gates before being stored as a verified chemical record.

### Input
- Entity candidate(s) from Stage 5
- Supporting identifiers and source metadata

### Validation gate sequence

```
name normalization confirmed
         │
         ▼
identifier / source validation (CAS, InChI, source DB)
         │
         ▼
entity confirmation (single unambiguous entity)
         │
         ▼
structure validation (if SMILES/InChI available and applicable)
         │
         ▼
field-level evidence check (each stored field has a cited source)
         │
         ▼
confidence assigned
         │
         ▼
Verified chemical record
```

Every gate must pass. A failure at any gate blocks verification; the entity stays in candidate status with a recorded reason.

### Output contract (verified record)

```json
{
  "entity_id": "string (internal UUID)",
  "preferred_name": "string",
  "identifiers": {
    "cas": "string | null",
    "pubchem_cid": "integer | null",
    "chebi_id": "string | null",
    "inchi": "string | null",
    "inchikey": "string | null",
    "smiles": "string | null"
  },
  "entity_type": "single_molecule | salt | polymer | material | mixture | natural_complex | formulation | trade_name | unknown",
  "verification_status": "verified | candidate | conflicted | unresolvable",
  "verification_timestamp": "ISO 8601",
  "field_evidence": [
    {
      "field": "string",
      "value": "string",
      "source": "string",
      "source_tier": "integer 1–4"
    }
  ],
  "confidence": "float 0–1",
  "limitations": ["string"]
}
```

### Forbidden behaviors
- **Never invent a CAS number.** If CAS is unknown, leave the field null and record the gap.
- **Never invent a molecular formula.** If the formula is unknown or inapplicable, leave it null.
- **Never invent or generate a SMILES string.** SMILES must come from a verified authoritative source.
- **Never treat a trade name as a unique molecule.** A trade name may refer to a formulation, mixture, or proprietary blend.
- **Never treat a mixture as a single molecule.** Mixtures, natural complexes, and formulations must be flagged as such in `entity_type`.

---

## Stage 7 — Computational Chemistry (RDKit)

### Purpose
Calculate molecular descriptors for verified chemical entities that have an appropriate, validated SMILES string.

### Eligibility check
Before running any computation, confirm ALL of the following:
1. The entity has `verification_status: verified`
2. A SMILES string is present and sourced from an authoritative source (not generated or inferred)
3. `entity_type` is NOT in the forbidden set below

**Do NOT compute for (representation types where a single molecular graph is inappropriate):**
- Mixtures (`entity_type: mixture`)
- Natural complex ingredients (`entity_type: natural_complex`, e.g., "rosemary extract")
- Formulations (`entity_type: formulation`)
- Trade names (`entity_type: trade_name`)
- Unknown entities (`entity_type: unknown`)
- Polymers where a single connected molecular graph is not appropriate (`entity_type: polymer`, case-by-case)

**Entities with `entity_type: single_molecule` or `entity_type: salt` that have a verified, appropriate SMILES may have RDKit computation performed.** The criterion is whether the entity has a verified, chemically meaningful SMILES — not whether it is `single_molecule` only. Salts with defined SMILES (e.g., sodium benzoate) are eligible.

### Computation flow

```
Verified SMILES
      │
      ▼
RDKit parser (Chem.MolFromSmiles)
      │
      ▼
Valid mol object? ──NO──► record parse failure, do not proceed
      │
      YES
      ▼
Canonical SMILES (normalized representation)
      │
      ▼
Descriptor calculation
      │
      ▼
Each descriptor stored with full provenance
```

### Output contract (per descriptor)

```json
{
  "descriptor_name": "string",
  "value": "number | string",
  "unit": "string | null",
  "software": "RDKit",
  "software_version": "string",
  "input_representation": "SMILES string used as input",
  "calculation_date": "ISO 8601"
}
```

### Critical distinctions
- **Computed ≠ experimental.** A calculated logP or molecular weight is a prediction, not a measured value. Downstream stages and explanations must treat these as estimated/computed values, not literature facts.
- **RDKit accepting a string is not validation.** RDKit may parse a malformed or incorrect SMILES without error. Acceptance by the parser does not verify chemical identity. Verification must happen in Stage 6, before computation.

### Quality gate (Stage 7 → Stage 8)
- Computed descriptors are stored with full provenance and tagged as `computed`.
- If computation fails (parse error, inappropriate entity type), the failure is recorded; no synthetic value is substituted.

### Forbidden behaviors
- Do not run computation on entities that have not passed Stage 6 verification.
- Do not synthesize or guess SMILES to enable computation.
- Do not present computed values as experimental or literature values without a clear label.

---

## Stage 8 — Role Resolution

### Purpose
Assign a domain-specific functional role to the verified chemical entity within its product context.

### Principle
**Chemical identity and product role are stored separately.** The same chemical entity can have different roles across different product domains. Examples:

| Entity | Domain | Role |
|--------|--------|------|
| Citric acid | Food | Acidity regulator |
| Citric acid | Cosmetic | pH adjuster |
| Citric acid | Household | Descaling agent |

### Input
- Verified chemical record from Stage 6
- Product domain and context
- Source evidence for role assignment

### Output contract

```json
{
  "entity_id": "string",
  "role": "string",
  "domain": "food | cosmetic | household | pharmaceutical",
  "role_taxonomy_version": "string",
  "evidence": [
    {
      "source": "string",
      "source_tier": "integer 1–4",
      "claim": "string"
    }
  ],
  "confidence": "float 0–1"
}
```

### Source requirements by claim type
Role claims must be sourced according to the authority hierarchy defined in the Evidence and Confidence Spec (section 6). Regulatory function claims require Tier 1 or Tier 2 sources. Domain-specific function claims from lower-tier sources may be used for supporting evidence but not as the primary basis for a role assignment.

### Forbidden behaviors
- Do not assign a role without cited evidence.
- Do not carry over a role assigned in one domain to a different domain.
- Do not infer role from chemical name alone.

---

## Stage 9 — Evidence Assembly

### Purpose
Build a complete, claim-level evidence record for every piece of information that will be surfaced to the user.

### Principle
Evidence is tracked at the **claim level**, not the entity level. Each individual assertion (e.g., "citric acid is an acidity regulator in EU food law") is a distinct claim with its own provenance.

### Input
- Verified chemical record (Stage 6)
- Computed descriptors (Stage 7, where applicable)
- Role assignment (Stage 8)

### Claim record contract

```json
{
  "claim_id": "string (UUID)",
  "entity_id": "string",
  "claim_type": "chemical_identity | formula | molecular_weight | smiles | product_contains_ingredient | ingredient_role | regulatory_status | experimental_property | computed_descriptor",
  // Note: this list is illustrative, not exhaustive. Use the canonical vocabulary from DATABASE_SCHEMA.md section 25.
  "field_name": "string",
  "value": "string | number",
  "provenance_type": "authoritative_db | regulatory_document | primary_literature | computed | user_input",
  "verification_status": "verified | candidate | conflicted | unverifiable",
  "confidence": "float 0–1",
  "valid_from": "ISO 8601 date | null",
  "valid_until": "ISO 8601 date | null",
  "claim_sources": [
    {
      "source_id": "string",
      "source_name": "string",
      "source_tier": "integer 1–4",
      "url": "string | null",
      "access_date": "ISO 8601",
      "excerpt": "string | null"
    }
  ]
}
```

### Source tier hierarchy

| Tier | Description | Examples |
|------|-------------|---------|
| 1 | Authoritative regulatory / official databases | FSSAI, Codex GSFA, EU Regulation, FDA, CosIng |
| 2 | Established scientific databases | PubChem, ChEBI, PubMed primary literature |
| 3 | High-quality secondary sources | Curated synonym databases, verified reference datasets |
| 4 | Conditional / community sources | Open Food Facts, Open Beauty Facts, manufacturer data |

Tier 4 sources may contribute candidate information only; they cannot be the sole basis for a verified claim.

### Conflict handling
When two sources make conflicting claims about the same entity and context:

1. Check that both claims are about the same entity and context (same form, salt, jurisdiction, date range).
2. If the scope differs (different jurisdiction, different salt form), record both claims scoped appropriately — this is not a conflict.
3. If scope is the same, apply the authority hierarchy: higher tier wins.
4. If tier is the same and claims conflict, set `verification_status: conflicted` and surface both claims with their sources. Do not silently choose one.

### Quality gate (Stage 9 → Stage 10)
- Only claims with `verification_status: verified` (or `computed` with appropriate labeling) may flow into Stage 10.
- Conflicted and unverifiable claims must be excluded or explicitly flagged as limitations.

### Forbidden behaviors
- Do not merge or average conflicting claim values.
- Do not drop a conflicted claim silently.
- Do not use Tier 4 source as the primary basis for a regulatory status claim.

---

## Stage 10 — Explanation Generation

### Purpose
Generate a user-facing explanation from verified, structured inputs only.

### Input
The explanation engine receives a structured payload — it never queries raw sources or external databases at explanation time.

```json
{
  "entity": { "...verified record from Stage 6..." },
  "verified_claims": [ "...claim records from Stage 9..." ],
  "role": { "...role record from Stage 8..." },
  "computed_descriptors": [ "...Stage 7 output where applicable..." ],
  "confidence": "float 0–1",
  "limitations": ["string"]
}
```

### Output contract

```json
{
  "explanation_id": "string (UUID)",
  "entity_id": "string",
  "sections": {
    "what_is_it": "string",
    "why_is_it_here": "string",
    "chemistry": "string | null",
    "evidence": "string",
    "uncertainty": "string"
  },
  "grounding_status": "grounded | partially_grounded | ungrounded",
  "limitations_surfaced": ["string"],
  "sources_cited": ["string"],
  "generation_timestamp": "ISO 8601"
}
```

### Grounding status definitions

| Status | Condition |
|--------|-----------|
| `grounded` | All required source claims exist; all requested fields are verified or appropriately labeled as computed; no unsupported inference; all limitations preserved |
| `partially_grounded` | Some fields verified; others absent or based on lower-confidence evidence; limitations surfaced to user |
| `ungrounded` | Required claims missing or conflicted; explanation cannot be generated without making unsupported inferences |

An `ungrounded` explanation must not be presented to the user as factual. The system should surface the limitation and indicate what information is missing.

### Prompt rule (non-negotiable)
The prompt to the explanation model must include:

> "Use only the supplied verified facts. If information is missing, say so explicitly. Do not infer molecular structure, regulatory status, safety conclusions, or medical recommendations from context or general knowledge."

### Forbidden behaviors
- Do not pass unverified, conflicted, or candidate claims into the explanation engine as facts.
- Do not allow the explanation model to query external sources.
- Do not present computed descriptors as experimental values.
- Do not infer regulatory approval from absence of a restriction.
- Do not generate safety or medical recommendations unless they are explicitly present as verified Tier 1 claims.
- Do not suppress the `uncertainty` section.

---

## Data Quality Gates — Summary

| Transition | Gate condition |
|------------|---------------|
| OCR → Extraction | OCR confidence threshold checked; `poor`/`unusable` surfaced to user before proceeding |
| Extraction → Normalization | Extraction confidence tracked separately from OCR confidence |
| Normalization → Candidates | Multiple candidates allowed; none promoted prematurely |
| Candidates → Verified | All Stage 6 gates must pass; any failure keeps entity in candidate status |
| Verified → Computed | Entity must have validated SMILES and pass eligibility check (must not be in the forbidden representation type set) |
| Computed → Explanation | Only verified claims and labeled computed values allowed as input |

At no transition may a failure or uncertainty be silently swallowed. Failures, limitations, and uncertainty must propagate forward as structured metadata.

---

## Caching Strategy

### Flow

```
User query
    │
    ▼
Local verified cache lookup (keyed by entity_id + domain + jurisdiction + date)
    │
    ├── HIT ──► Serve cached verified record + cache metadata
    │
    └── MISS
           │
           ▼
    Authoritative source lookup (see Source Routing below)
           │
           ▼
    Validate response (run through relevant pipeline stages)
           │
           ▼
    Store with full provenance + licensing metadata
           │
           ▼
    Serve verified record
```

### Cache entry requirements
Every cached entry must store:
- Full provenance (source, tier, access date)
- Licensing status confirmation — **never cache data from a source whose licensing terms prohibit caching**
- `valid_from` / `valid_until` timestamps where the source provides them
- The pipeline stage at which the data was validated

### Invalidation
Cache entries are invalidated when:
- `valid_until` date has passed
- The source database has issued a known update affecting this entity
- A higher-tier source contradicts the cached claim

### Forbidden behaviors
- Do not cache data without recording its license/terms status.
- Do not serve cached data past its `valid_until` date without re-validation.
- Do not cache Tier 4 (community) data as if it were Tier 1.

---

## Source Routing

Queries are routed to sources based on the type of information needed. Free and authoritative sources are preferred first.

| Information needed | Primary source(s) | Notes |
|--------------------|-------------------|-------|
| Chemical identity | PubChem, ChEBI | Free, authoritative; prefer for identity and structure |
| Molecular computation | RDKit (local) | Free, open-source; all computation is local |
| India food regulation | FSSAI | Official regulatory authority |
| International food additives | Codex GSFA | FAO/WHO; authoritative for Codex-member countries |
| EU food additives | European Commission (EC regulations) | Tier 1 for EU jurisdiction |
| US food additives | FDA | Tier 1 for US jurisdiction |
| EU cosmetic nomenclature | CosIng | Official EU cosmetic ingredient database |
| Product-specific data | Actual label / manufacturer | Direct source; use for product-level claims |
| Food product discovery | Open Food Facts | Tier 4 / conditional; candidate data only |
| Cosmetic product discovery | Open Beauty Facts | Tier 4 / conditional; candidate data only |
| Scientific mechanism / properties | PubMed, primary literature | Tier 2; supports identity and function claims |

### Routing rules
1. Always route identity lookups to PubChem or ChEBI before any secondary source.
2. Route regulatory status lookups to the jurisdiction-specific Tier 1 source (FSSAI, EC, FDA, Codex GSFA) — never infer regulatory status from a general chemistry database.
3. Use Open Food Facts and Open Beauty Facts only to generate candidates, never to verify claims. Any data from these sources must be re-validated against a Tier 1 or Tier 2 source before promotion.
4. Product-specific claims (specific formulation, declared ingredient list) must ultimately trace back to the actual product label or manufacturer documentation.

---

## Appendix: Forbidden Behaviors — Consolidated Reference

The following behaviors are prohibited at any stage of the pipeline.

| Behavior | Relevant stages |
|----------|----------------|
| Silently overwrite a previous stage's output | All |
| Invent a CAS number | 6 |
| Invent a molecular formula | 6 |
| Generate or infer a SMILES string without an authoritative source | 6, 7 |
| Treat a trade name as a unique molecule | 6 |
| Treat a mixture as a single molecule | 6 |
| Run RDKit on an ineligible entity (e.g., an undefined mixture) | 7 |
| Present a computed descriptor as an experimental value | 7, 10 |
| Trust RDKit acceptance as chemical identity validation | 7 |
| Carry a role from one domain to another without evidence | 8 |
| Use a Tier 4 source as the sole basis for a regulatory claim | 9 |
| Silently drop a conflicted claim | 9 |
| Pass unverified claims to the explanation engine | 10 |
| Allow the explanation engine to query external sources | 10 |
| Infer regulatory approval from absence of a restriction | 10 |
| Generate medical or safety recommendations without verified Tier 1 support | 10 |
| Cache data without licensing confirmation | Caching |
| Serve Tier 4 cached data as Tier 1 | Caching |
| Promote an ambiguous entity to verified without additional evidence | 5, 6 |
| Proceed past `poor`/`unusable` OCR confidence without user visibility | 1 |

---

*This document is the authoritative technical reference for the LabelLens data pipeline. All implementation decisions must conform to the stage contracts and forbidden behaviors defined here.*
