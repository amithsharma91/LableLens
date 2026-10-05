# LabelLens — API Specification

**Document:** API_SPEC.md  
**Project:** LabelLens  
**Version:** 1.0  
**Backend:** FastAPI / Python  
**Frontend:** Next.js / TypeScript  
**Database:** PostgreSQL via Supabase  
**Purpose:** Define the stable application contract between the frontend, FastAPI backend, OCR/AI services, chemistry engine, evidence layer, and database.

---

# 1. API Objective

The API is the controlled boundary between the LabelLens UI and the underlying processing/data systems.

Primary responsibilities:

```text
Browser
  ↓
FastAPI
  ↓
Validation
  ↓
Business services
  ├── Scan/OCR
  ├── Ingredient normalization
  ├── Entity resolution
  ├── Chemistry
  ├── Roles
  ├── Evidence
  ├── Explanation
  └── Comparison
  ↓
PostgreSQL / approved external sources
```

The API must prevent the frontend or an AI model from directly creating or modifying verified chemistry.

---

# 2. API Principles

1. **Typed contracts first.**
2. **Validate every request.**
3. **Return explicit statuses.**
4. **Never expose provider secrets.**
5. **Never let AI output directly become canonical scientific data.**
6. **Use stable public response models instead of leaking database tables.**
7. **Preserve evidence and confidence in responses.**
8. **Return partial results when safe and meaningful.**
9. **Make errors machine-readable.**
10. **Design for a free-first deployment.**
11. **Keep external AI/OCR providers behind adapters.**
12. **Version the API before breaking contracts.**

---

# 3. Base URL and Versioning

Initial API:

```text
/api/v1
```

Examples:

```text
POST /api/v1/scans
GET  /api/v1/scans/{scan_id}
POST /api/v1/scans/{scan_id}/ocr
POST /api/v1/scans/{scan_id}/analyze
```

Do not put API version in database table names.

When a breaking response change is required:

```text
/api/v2
```

Do not silently break existing clients.

---

# 4. Content Types

### JSON

Default:

```http
Content-Type: application/json
```

### Multipart upload

For image/file input:

```http
Content-Type: multipart/form-data
```

Only accepted file types should be allowed.

At minimum validate:

```text
MIME type
extension
file size
image dimensions
file signature where practical
```

Never trust the filename alone.

---

# 5. Common Response Envelope

For successful single-resource responses:

```json
{
  "data": {},
  "meta": {
    "request_id": "uuid",
    "api_version": "v1"
  }
}
```

For collections:

```json
{
  "data": [],
  "meta": {
    "request_id": "uuid",
    "api_version": "v1",
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 100
    }
  }
}
```

For long-running work:

```json
{
  "data": {
    "job_id": "uuid",
    "status": "queued"
  },
  "meta": {
    "request_id": "uuid",
    "api_version": "v1"
  }
}
```

---

# 6. Common Error Envelope

All expected API errors should use a predictable structure:

```json
{
  "error": {
    "code": "INGREDIENT_NOT_FOUND",
    "message": "The ingredient could not be confidently identified.",
    "details": {
      "observation_id": "uuid"
    }
  },
  "meta": {
    "request_id": "uuid",
    "api_version": "v1"
  }
}
```

Do not return model/provider raw error text to users.

---

# 7. Error Codes

Initial controlled codes:

```text
INVALID_REQUEST
VALIDATION_ERROR
UNSUPPORTED_FILE_TYPE
FILE_TOO_LARGE
IMAGE_UNREADABLE
OCR_FAILED
OCR_LOW_CONFIDENCE
INGREDIENT_EXTRACTION_FAILED
NORMALIZATION_FAILED
ENTITY_NOT_FOUND
ENTITY_AMBIGUOUS
ENTITY_MATCH_LOW_CONFIDENCE
CHEMISTRY_NOT_APPLICABLE
CHEMISTRY_CALCULATION_FAILED
SOURCE_UNAVAILABLE
EVIDENCE_INSUFFICIENT
EVIDENCE_CONFLICT
ANALYSIS_NOT_READY
ANALYSIS_FAILED
COMPARISON_FAILED
RATE_LIMITED
UNAUTHORIZED
FORBIDDEN
NOT_FOUND
CONFLICT
INTERNAL_ERROR
SERVICE_UNAVAILABLE
```

---

# 8. HTTP Status Strategy

Use standard HTTP semantics.

```text
200 OK
201 Created
202 Accepted
204 No Content
400 Bad Request
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
413 Payload Too Large
422 Unprocessable Entity
429 Too Many Requests
500 Internal Server Error
503 Service Unavailable
```

Do not return `200` for a failed operation merely to simplify frontend logic.

---

# 9. Request IDs

Every API request should receive a unique:

```text
X-Request-ID
```

or application-generated equivalent.

Include it in:
- logs
- errors
- response metadata
- support/debug records

Do not expose sensitive internal logs.

---

# 10. Idempotency

Write operations that may be safely retried should support an idempotency key.

Example:

```http
Idempotency-Key: uuid
```

Recommended for:
- scan creation
- OCR job submission
- analysis start
- comparison creation
- source-ingestion operations

The backend must define which operations are idempotent before implementing retries.

---

# 11. API Domain Modules

Recommended FastAPI routers:

```text
/api/v1/
  scans
  products
  ingredients
  search
  analyses
  comparisons
  sources
  health
```

Internal service modules:

```text
services/
  scan_service
  ocr_service
  extraction_service
  normalization_service
  entity_resolution_service
  chemistry_service
  role_service
  evidence_service
  explanation_service
  comparison_service
```

Do not put all business logic inside route functions.

---

# 12. Health Endpoints

## GET `/api/v1/health`

Purpose:
- frontend health check
- deployment verification

Response:

```json
{
  "data": {
    "status": "ok",
    "version": "0.1.0"
  }
}
```

Do not expose secrets, environment variables, database credentials, or detailed infrastructure information.

---

## GET `/api/v1/health/dependencies`

Development/admin use only.

Return high-level states:

```json
{
  "data": {
    "database": "ok",
    "chemistry_engine": "ok",
    "ocr_provider": "available",
    "ai_provider": "available"
  }
}
```

Do not expose provider API keys.

---

# 13. SCAN API

## POST `/api/v1/scans`

Creates a scan.

### Multipart request

Fields:

```text
image: optional file
input_method: camera | upload | manual_text
manual_text: optional string
product_id: optional UUID
```

At least one of:

```text
image
manual_text
```

must be supplied.

### Response

```json
{
  "data": {
    "scan_id": "uuid",
    "status": "uploaded",
    "input_method": "upload"
  }
}
```

### Acceptance criteria

- Reject unsupported files.
- Reject files over configured size.
- Never execute uploaded files.
- Store only approved metadata/path references.
- Do not automatically claim a product identity from an image.
- Do not automatically verify ingredients.

---

# 14. GET `/api/v1/scans/{scan_id}`

Returns scan status and compact metadata.

Response:

```json
{
  "data": {
    "id": "uuid",
    "status": "analysis_complete",
    "input_method": "camera",
    "created_at": "timestamp",
    "product": null
  }
}
```

Do not include enormous OCR/explanation payloads by default.

---

# 15. OCR API

## POST `/api/v1/scans/{scan_id}/ocr`

Starts OCR.

### Optional request

```json
{
  "force_refresh": false,
  "engine": "default"
}
```

Response:

```json
{
  "data": {
    "job_id": "uuid",
    "status": "queued"
  }
}
```

Use asynchronous processing when OCR may exceed a normal request duration.

---

# 16. OCR Result Model

## GET `/api/v1/scans/{scan_id}/ocr`

Response:

```json
{
  "data": {
    "status": "complete",
    "ocr_run_id": "uuid",
    "raw_text": "...",
    "overall_confidence": "medium",
    "engine": "provider_or_local",
    "model_version": "version",
    "ingredients_detected": true
  }
}
```

If the OCR engine provides token/region confidence, preserve it when useful.

OCR confidence must never be presented as chemical confidence.

---

# 17. INGREDIENT EXTRACTION API

## POST `/api/v1/scans/{scan_id}/ingredients/extract`

Creates ingredient observations from OCR text.

Request:

```json
{
  "ocr_run_id": "uuid"
}
```

Response:

```json
{
  "data": {
    "status": "complete",
    "ingredients": [
      {
        "observation_id": "uuid",
        "sequence_number": 1,
        "raw_text": "Citric Acid",
        "source_type": "ocr",
        "confidence": "high"
      }
    ]
  }
}
```

Extraction must preserve the exact observed label text.

---

# 18. GET `/api/v1/scans/{scan_id}/ingredients`

Returns editable ingredient observations.

Response:

```json
{
  "data": [
    {
      "observation_id": "uuid",
      "sequence_number": 1,
      "raw_text": "Sodiurn Benzoate",
      "display_text": "Sodiurn Benzoate",
      "user_corrected": false,
      "ocr_confidence": "medium"
    }
  ]
}
```

---

# 19. PATCH `/api/v1/ingredient-observations/{observation_id}`

Allows the user to correct an observed ingredient string.

Request:

```json
{
  "display_text": "Sodium Benzoate"
}
```

Rules:
- Preserve original OCR text.
- Record correction event.
- Do not mark chemistry verified.
- Trigger re-normalization if necessary.
- Do not silently alter historical OCR run data.

Response:

```json
{
  "data": {
    "observation_id": "uuid",
    "original_text": "Sodiurn Benzoate",
    "display_text": "Sodium Benzoate",
    "user_corrected": true
  }
}
```

---

# 20. NORMALIZATION API

## POST `/api/v1/ingredient-observations/{observation_id}/normalize`

Request:

```json
{
  "text": "Sodium Benzoate"
}
```

Response:

```json
{
  "data": {
    "normalization_id": "uuid",
    "normalized_text": "Sodium Benzoate",
    "status": "complete",
    "confidence": "high",
    "method": "hybrid"
  }
}
```

Normalization does not establish chemical identity.

---

# 21. ENTITY RESOLUTION API

## POST `/api/v1/ingredient-observations/{observation_id}/match`

Response:

```json
{
  "data": {
    "normalization_id": "uuid",
    "match_status": "exact_match",
    "identity_confidence": "high",
    "entity": {
      "id": "uuid",
      "preferred_name": "..."
    },
    "alternatives": []
  }
}
```

For ambiguous input:

```json
{
  "data": {
    "match_status": "ambiguous",
    "identity_confidence": "low",
    "entity": null,
    "alternatives": [
      {
        "entity_id": "uuid",
        "name": "...",
        "reason": "..."
      }
    ]
  }
}
```

The frontend must represent ambiguity rather than automatically selecting the first candidate.

---

# 22. INGREDIENT DETAIL API

## GET `/api/v1/ingredients/{chemical_entity_id}`

Returns verified canonical chemical information.

Response:

```json
{
  "data": {
    "id": "uuid",
    "preferred_name": "...",
    "entity_type": "chemical_entity",
    "representation_type": "single_molecule",
    "identity": {
      "cas": null,
      "pubchem_cid": null,
      "chebi_id": null,
      "inchi": null,
      "inchikey": null
    },
    "structure": {
      "smiles": null,
      "available": false,
      "status": "unavailable"
    },
    "formula": null,
    "molecular_weight": null,
    "classification": {
      "chemical_class": null,
      "functional_groups": []
    },
    "properties": [],
    "roles": [],
    "evidence": [],
    "confidence": {},
    "limitations": []
  }
}
```

Do not fabricate missing values.

---

# 23. INGREDIENT SEARCH API

## GET `/api/v1/search/ingredients`

Query parameters:

```text
q
domain
status
limit
cursor
```

Example:

```text
GET /api/v1/search/ingredients?q=citric
```

Search priority:

```text
exact preferred name
exact alias
identifier
prefix
carefully controlled similarity
```

Text similarity is not chemical identity verification.

Response:

```json
{
  "data": [
    {
      "id": "uuid",
      "preferred_name": "...",
      "entity_type": "chemical_entity",
      "match_context": "alias",
      "verification_status": "verified"
    }
  ],
  "meta": {
    "pagination": {
      "next_cursor": null
    }
  }
}
```

---

# 24. DOMAIN API

## GET `/api/v1/domains`

Returns active product domains.

Response:

```json
{
  "data": [
    {
      "id": "uuid",
      "code": "food",
      "name": "Food"
    }
  ]
}
```

---

# 25. ROLE API

## GET `/api/v1/domains/{domain_id}/roles`

Returns active role taxonomy.

Response:

```json
{
  "data": [
    {
      "id": "uuid",
      "code": "preservative",
      "name": "Preservative",
      "taxonomy_version": "1.0"
    }
  ]
}
```

Roles are domain-specific.

---

# 26. PRODUCT ANALYSIS API

## POST `/api/v1/scans/{scan_id}/analyze`

Starts the complete analysis pipeline.

Request:

```json
{
  "domain": null,
  "run_ocr_if_missing": true,
  "auto_normalize": true,
  "auto_match": true,
  "calculate_descriptors": true,
  "generate_explanations": true
}
```

### Response

For asynchronous processing:

```json
{
  "data": {
    "analysis_run_id": "uuid",
    "status": "queued"
  }
}
```

The server should skip unnecessary stages when valid results already exist.

---

# 27. Analysis Pipeline

The backend should execute logically as:

```text
Input
 ↓
OCR
 ↓
Extraction
 ↓
Normalization
 ↓
Candidate matching
 ↓
Entity verification
 ↓
Role resolution
 ↓
Chemistry computation
 ↓
Evidence assembly
 ↓
Explanation grounding
 ↓
Analysis result
```

Each stage should have its own status/error.

A failure in one ingredient should not necessarily fail the entire product analysis.

---

# 28. GET `/api/v1/analyses/{analysis_run_id}`

Returns high-level analysis state.

Response:

```json
{
  "data": {
    "analysis_run_id": "uuid",
    "status": "partial",
    "pipeline_version": "1.0",
    "summary": {
      "ingredients_detected": 20,
      "normalized": 19,
      "matched": 16,
      "unresolved": 4,
      "chemistry_available": 13,
      "role_coverage": "moderate"
    }
  }
}
```

Do not convert these statistics into a fake overall accuracy score.

---

# 29. GET `/api/v1/analyses/{analysis_run_id}/items`

Returns ingredient-level analysis.

Response:

```json
{
  "data": [
    {
      "analysis_item_id": "uuid",
      "observation": {
        "raw_text": "...",
        "display_text": "..."
      },
      "identity": {
        "status": "verified",
        "entity": {
          "id": "uuid",
          "preferred_name": "..."
        },
        "confidence": "high"
      },
      "role": {
        "name": "...",
        "status": "supported",
        "confidence": "medium"
      },
      "chemistry": {
        "formula": "...",
        "molecular_weight": null,
        "structure_available": true,
        "computed_descriptors": []
      },
      "explanation": {
        "status": "grounded",
        "text": "...",
        "grounding": {
          "claim_ids": [],
          "source_ids": []
        }
      },
      "limitations": []
    }
  ]
}
```

---

# 30. Analysis Summary API

## GET `/api/v1/scans/{scan_id}/summary`

Optimized endpoint for the main product-analysis screen.

Should return:
- product/domain
- ingredient counts
- match counts
- role summary
- evidence coverage
- unresolved count
- top-level warnings

Avoid returning every source detail.

---

# 31. EVIDENCE API

## GET `/api/v1/claims/{claim_id}`

Returns one claim.

Response:

```json
{
  "data": {
    "id": "uuid",
    "claim_type": "formula",
    "field_name": "formula",
    "value": "...",
    "verification_status": "verified",
    "confidence": "high",
    "provenance_type": "source_reported",
    "sources": []
  }
}
```

---

# 32. SOURCE API

## GET `/api/v1/sources/{source_id}`

Returns source metadata.

Do not expose private source credentials.

Response:

```json
{
  "data": {
    "id": "uuid",
    "name": "...",
    "publisher": "...",
    "source_type": "scientific_database",
    "authority_level": "high",
    "jurisdiction": null,
    "url": "...",
    "last_checked_at": "timestamp",
    "freshness_class": "stable"
  }
}
```

---

# 33. Source Lookup

## GET `/api/v1/ingredients/{chemical_entity_id}/evidence`

Returns evidence relevant to that entity.

Optional parameters:

```text
field
claim_type
status
limit
cursor
```

The API should avoid returning irrelevant claims.

---

# 34. “Why Is This Here?” API

## GET `/api/v1/analysis-items/{analysis_item_id}/explanation`

Returns the current grounded explanation.

Response:

```json
{
  "data": {
    "status": "grounded",
    "text": "...",
    "sections": {
      "what_is_it": "...",
      "why_is_it_here": "...",
      "chemistry": "...",
      "evidence": "...",
      "uncertainty": "..."
    },
    "grounding": {
      "claim_ids": [],
      "source_ids": [],
      "prompt_version": "1.0",
      "model": "provider/model"
    }
  }
}
```

The API must not return an explanation as “grounded” when supporting evidence is missing.

---

# 35. CHEMISTRY API

## GET `/api/v1/ingredients/{chemical_entity_id}/chemistry`

Returns chemistry data.

Possible response:

```json
{
  "data": {
    "entity_id": "uuid",
    "representation_type": "single_molecule",
    "structure": {
      "smiles": "...",
      "validation_status": "verified"
    },
    "formula": "...",
    "molecular_weight": {
      "value": 0,
      "unit": "g/mol",
      "provenance": "source_reported"
    },
    "descriptors": [
      {
        "name": "tpsa",
        "value": 0,
        "unit": "A^2",
        "provenance": "computed",
        "software": "RDKit",
        "software_version": "..."
      }
    ]
  }
}
```

If no suitable structure exists:

```json
{
  "data": {
    "representation_type": "mixture",
    "structure": {
      "available": false,
      "status": "not_applicable"
    },
    "limitations": [
      "A single molecular structure is not appropriate for this entity."
    ]
  }
}
```

---

# 36. Chemistry Computation Endpoint

## POST `/api/v1/ingredients/{chemical_entity_id}/compute`

Development/admin endpoint initially.

Request:

```json
{
  "descriptors": [
    "molecular_weight",
    "tpsa",
    "hbond_donors",
    "hbond_acceptors"
  ]
}
```

Rules:
- Require a validated appropriate structure.
- Reject mixtures/undefined entities when a single molecular graph is not appropriate.
- Record software and version.
- Record input representation.
- Mark results as computed.
- Do not overwrite authoritative experimental values.

Response:

```json
{
  "data": {
    "status": "computed",
    "results": []
  }
}
```

---

# 37. COMPARISON API

## POST `/api/v1/comparisons`

Request:

```json
{
  "left_scan_id": "uuid",
  "right_scan_id": "uuid"
}
```

Response:

```json
{
  "data": {
    "comparison_id": "uuid",
    "status": "complete"
  }
}
```

Both scans must have usable ingredient analysis.

---

# 38. GET `/api/v1/comparisons/{comparison_id}`

Response:

```json
{
  "data": {
    "comparison_id": "uuid",
    "summary": {
      "shared": 15,
      "left_only": 3,
      "right_only": 5,
      "ambiguous": 1
    },
    "items": [],
    "limitations": []
  }
}
```

---

# 39. Comparison Item Contract

Example:

```json
{
  "comparison_type": "shared",
  "left_ingredient": {
    "name": "...",
    "entity_id": "uuid"
  },
  "right_ingredient": {
    "name": "...",
    "entity_id": "uuid"
  },
  "identity_relation": "same_verified_entity",
  "role_difference": null,
  "chemistry_difference": null,
  "evidence": []
}
```

For chemically related but non-identical substances:

```text
identity_relation = chemically_related
```

Never silently treat them as identical.

---

# 40. PRODUCT API

## GET `/api/v1/products/{product_id}`

Returns product identity and available label versions.

Do not assume current product information is identical to an older scan.

Response:

```json
{
  "data": {
    "id": "uuid",
    "brand_name": "...",
    "product_name": "...",
    "domain": {
      "code": "food",
      "name": "Food"
    },
    "label_versions": []
  }
}
```

---

# 41. Product Label API

## GET `/api/v1/products/{product_id}/labels`

Returns known label versions.

Each label includes:
- label ID
- label date if available
- country/market
- source
- status
- scan count

Never claim that a scanned historical label is the current label unless verified.

---

# 42. Recent Scans API

## GET `/api/v1/scans/recent`

If accounts are enabled, return only user-owned scans.

Parameters:

```text
limit
cursor
domain
```

Do not store history permanently unless required by product settings.

---

# 43. DELETE `/api/v1/scans/{scan_id}`

Deletes or anonymizes user-owned scan data according to the configured retention policy.

Rules:
- Do not delete canonical public chemistry merely because a user deletes their scan.
- Remove associated private images where appropriate.
- Preserve aggregate/anonymized benchmark data only where permitted.
- Log important deletion events without retaining deleted sensitive content.

---

# 44. USER CORRECTIONS API

## GET `/api/v1/scans/{scan_id}/corrections`

Returns corrections for a scan.

## POST `/api/v1/ingredient-observations/{observation_id}/corrections`

Request:

```json
{
  "new_value": "...",
  "correction_type": "ocr_correction"
}
```

Response contains the correction event.

---

# 45. Manual Verification API

Initially restricted to development/admin workflows.

## POST `/api/v1/claims/{claim_id}/verify`

Request:

```json
{
  "status": "verified",
  "confidence": "high",
  "reason": "...",
  "source_ids": []
}
```

Rules:
- Require appropriate authorization.
- Require source support for verified status.
- Record verification event.
- Never accept AI-generated text as sufficient justification by itself.

---

# 46. Candidate Review API

## GET `/api/v1/review/candidates`

Restricted.

Filters:

```text
status
domain
match_status
confidence
```

## POST `/api/v1/review/candidates/{candidate_id}/resolve`

Request:

```json
{
  "decision": "approve | reject | ambiguous",
  "chemical_entity_id": "uuid",
  "reason": "..."
}
```

Every resolution becomes auditable.

---

# 47. MODEL / AI ADAPTER CONTRACT

The application must isolate AI providers.

Internal interface:

```python
class AIProvider:
    async def generate_structured_candidate(...): ...
    async def generate_explanation(...): ...
```

Possible providers:
- Gemini
- OmniRoute-routed models
- another compatible provider
- local model later

The rest of the application must depend on the interface, not a provider-specific SDK.

---

# 48. OCR ADAPTER CONTRACT

Internal interface:

```python
class OCRProvider:
    async def extract_label(...): ...
```

Return:

```json
{
  "text": "...",
  "confidence": "medium",
  "regions": [],
  "engine": "...",
  "model_version": "..."
}
```

OCR engine output must remain observational.

---

# 49. Chemistry Service Contract

Internal interface:

```python
class ChemistryService:
    def validate_smiles(...): ...
    def calculate_descriptors(...): ...
    def render_structure(...): ...
    def compare_structures(...): ...
```

Every chemistry result should identify:
- input representation
- software
- software version
- calculation status
- provenance

---

# 50. Entity Resolution Service Contract

Input:

```json
{
  "normalized_text": "...",
  "domain": "food",
  "context": "...",
  "identifiers": []
}
```

Output:

```json
{
  "status": "exact_match",
  "confidence": "high",
  "candidates": [],
  "selected_entity_id": "uuid",
  "reasons": []
}
```

The service must not promote a low-confidence candidate to verified status.

---

# 51. Evidence Service Contract

Internal interface:

```python
class EvidenceService:
    async def get_claims(...): ...
    async def get_sources(...): ...
    async def validate_claim(...): ...
    async def assess_freshness(...): ...
```

Evidence logic must remain independent from AI explanation code.

---

# 52. Explanation Service Contract

Input:

```json
{
  "entity": {},
  "verified_claims": [],
  "role": {},
  "sources": [],
  "confidence": {},
  "limitations": []
}
```

Output:

```json
{
  "status": "grounded",
  "sections": {
    "what_is_it": "...",
    "why_is_it_here": "...",
    "chemistry": "...",
    "uncertainty": "..."
  },
  "claim_ids": [],
  "source_ids": [],
  "model": "...",
  "prompt_version": "..."
}
```

The service must reject or downgrade unsupported explanations.

---

# 53. Prompt Injection Protection

Product labels are untrusted input.

An ingredient label could contain text that looks like instructions.

Example:

```text
"IGNORE PREVIOUS INSTRUCTIONS..."
```

The API must treat label/OCR text as **data, not instructions**.

Rules:
- Delimit untrusted label content.
- Never directly concatenate untrusted text into a system prompt.
- Use structured fields for AI input where possible.
- Instruct AI that label text is untrusted data.
- Validate structured model output.
- Never let label text modify system/tool permissions.

---

# 54. AI Structured Output

When AI is used for candidate extraction or normalization, require machine-readable output.

Example:

```json
{
  "ingredients": [
    {
      "raw_text": "...",
      "normalized_candidate": "...",
      "reason": "...",
      "confidence": "medium"
    }
  ]
}
```

Backend validation must reject malformed or unexpected structures.

Do not trust arbitrary free-form model text for database writes.

---

# 55. Provider Routing with OmniRoute

OmniRoute may be used as a routing layer where practical.

Architecture:

```text
LabelLens AI service
       ↓
AIProvider interface
       ↓
OmniRoute / Gemini / other configured provider
       ↓
structured output
       ↓
validation
```

Never put OmniRoute-specific assumptions into:
- database schema
- chemistry service
- frontend data models

Provider swapping should not require a product rewrite.

---

# 56. Gemini Pro Usage

Gemini Pro may be used for:
- deep research
- OCR experiments
- candidate extraction
- dataset discovery
- explanation drafting
- independent cross-checking

Its result enters:

```text
AI candidate
```

not:

```text
verified chemistry
```

The same validation/evidence rules apply regardless of provider.

---

# 57. Hermes / Termux Boundary

Hermes Agent is a developer orchestration tool, not a production runtime dependency.

It may:
- execute commands
- run tests
- inspect logs
- coordinate repetitive terminal tasks
- invoke local developer tools

It must not become a required backend service merely because it is convenient during development.

The deployed LabelLens runtime should remain independently reproducible.

---

# 58. OpenCode and Claude Code Boundary

### OpenCode
Primary implementation agent.

It should follow:
- this API spec
- database schema
- chemistry spec
- evidence spec
- product spec

### Claude Code
Reviewer/debugger/refactor agent.

It should verify:
- contracts
- error states
- tests
- security
- type safety
- migrations
- edge cases

Neither agent may silently change API contracts.

API changes require:
1. Spec update
2. Code change
3. Tests
4. Migration if needed
5. Changelog/decision record

---

# 59. Authentication Strategy

MVP may operate without user accounts if functionality can be delivered safely.

If accounts are introduced:

```text
Next.js
  ↓
authenticated session
  ↓
FastAPI
  ↓
authorization
  ↓
Supabase/Postgres
```

User-owned resources:
- scans
- private images
- corrections
- comparisons
- history

Canonical chemistry/source data should have separate permissions.

---

# 60. Authorization Rules

A user may access a private scan only when:
- it belongs to the authenticated user
- or it is explicitly public/shareable

Canonical chemistry write operations should be server/admin-only.

Never rely only on frontend hiding for security.

---

# 61. File Upload API Rules

For label images:

### Validate
- actual MIME type
- extension
- file signature
- size
- dimensions

### Process
- strip metadata where practical
- resize/crop safely
- generate derived image
- store object path, not binary blob in Postgres

### Never
- execute uploaded files
- trust EXIF metadata
- expose storage bucket credentials
- accept arbitrary active document types for MVP

---

# 62. Rate Limiting

Rate limit at API boundaries.

High-cost endpoints:
- OCR
- full analysis
- AI explanation
- source search
- chemistry computation

Use different limits by endpoint cost.

For MVP, a simple application-level/IP-level mechanism is acceptable; upgrade only when actual scale requires it.

---

# 63. Caching

Cache safe, non-user-specific data:

```text
canonical chemical lookup
approved source metadata
role taxonomy
domain list
verified chemistry records
```

Do not cache private user analysis responses globally.

Cache key should include relevant versioning.

Example:

```text
chemical:{entity_id}:v{data_version}
```

---

# 64. Pagination

Use cursor pagination for large collections.

Preferred:

```text
?limit=20&cursor=...
```

Avoid offset pagination for growing datasets where stable cursor ordering matters.

For MVP small datasets, offset pagination may be used if implemented consistently.

---

# 65. Sorting

Every paginated endpoint must define deterministic ordering.

Example:

```text
created_at DESC, id DESC
```

This prevents duplicates/missing records between pages.

---

# 66. API Data Types

Prefer explicit types.

Example Pydantic models:

```python
class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"
```

Do not use unvalidated arbitrary strings for controlled statuses where correctness matters.

---

# 67. Nullable Scientific Fields

API models must preserve the distinction between:

```text
null
+
status
```

Example:

```json
{
  "smiles": null,
  "structure_available": false,
  "structure_status": "not_applicable"
}
```

Never replace NULL scientific values with:
- `"N/A"`
- `"-"`
- `"unknown"`
- `0`

inside typed scientific fields.

---

# 68. API Representation of Confidence

Use:

```json
{
  "identity": "high",
  "formula": "high",
  "structure": "unknown",
  "role": "medium"
}
```

Do not return a single confidence field when the underlying evidence is multidimensional.

---

# 69. API Representation of Sources

Compact source object:

```json
{
  "source_id": "uuid",
  "name": "...",
  "source_type": "scientific_database",
  "authority_level": "high",
  "url": "...",
  "last_checked_at": "timestamp"
}
```

Do not return private source notes or internal credentials.

---

# 70. API Representation of Limitations

Every analysis can include:

```json
{
  "limitations": [
    {
      "code": "UNVERIFIED_INGREDIENT",
      "message": "One ingredient could not be confidently identified."
    }
  ]
}
```

This is preferable to hiding uncertainty in generic warning text.

---

# 71. Partial Success

A product analysis should be able to complete partially.

Example:

```text
20 detected
17 matched
3 unknown
```

Return:

```text
status = partial
```

rather than failing the entire product.

However, do not report partial analysis as complete verification.

---

# 72. Retry Rules

Safe automatic retries:
- transient network failure
- temporary provider outage
- database connection reset
- queue interruption

Do not automatically retry indefinitely:
- invalid input
- unsupported file
- ambiguous identity
- evidence conflict
- invalid SMILES

Use bounded exponential backoff for transient operations.

---

# 73. Timeout Rules

Every external operation must have a timeout.

Examples:
- OCR request
- AI request
- source lookup
- chemistry calculation if remotely executed

A timeout becomes a structured state:

```text
SERVICE_UNAVAILABLE
```

Do not hang a user request indefinitely.

---

# 74. Observability

Log:
- request ID
- endpoint
- status code
- latency
- error code
- pipeline stage
- analysis ID
- provider/model version where relevant

Do not log:
- API secrets
- full private images
- unnecessary raw personal information
- full private label content by default

---

# 75. Cost Tracking

Because the project is free-first, optionally record:

```text
AI provider
model
estimated token count
latency
cost estimate
```

in `model_runs`.

The application must not depend on a precise cost value for correctness.

If an operation can be completed without AI, prefer the deterministic/local path.

---

# 76. API Contract Testing

Create contract tests for every critical endpoint.

### Scan
- valid image → 201
- invalid file → 415/422
- oversized file → 413

### OCR
- valid scan → queued/complete
- repeated request → idempotent behavior
- provider failure → structured error

### Correction
- original text preserved
- correction recorded
- re-analysis possible

### Entity matching
- exact known ingredient → verified candidate/match
- ambiguous input → ambiguous
- unknown input → no_match

### Chemistry
- valid structure → calculation
- invalid structure → validation failure
- mixture → appropriate not-applicable response

### Evidence
- verified claim → source included
- missing evidence → unknown/unverified
- conflict → conflicted

### Comparison
- two valid scans → comparison
- ambiguous ingredients → ambiguity preserved

---

# 77. End-to-End Critical Path

The single most important E2E test:

```text
POST /scans
      ↓
POST /ocr
      ↓
GET /ocr
      ↓
POST /ingredients/extract
      ↓
PATCH observation
      ↓
POST normalize
      ↓
POST match
      ↓
POST analyze
      ↓
GET analysis
      ↓
GET analysis item
      ↓
GET chemistry
      ↓
GET evidence
      ↓
POST comparison
      ↓
GET comparison
```

The frontend must be able to execute this path without manual database edits.

---

# 78. API Acceptance Criteria

The API specification is accepted when:

1. Frontend/backend contracts are explicit.
2. Every critical endpoint has request/response definitions.
3. Errors are structured.
4. Validation is explicit.
5. OCR remains observational.
6. User corrections are auditable.
7. Entity candidates cannot silently become verified.
8. Chemistry is deterministic where applicable.
9. AI providers are abstracted.
10. Evidence is returned separately from explanations.
11. Confidence is multidimensional.
12. Product comparison preserves uncertainty.
13. Historical scans are not silently mutated.
14. Private and canonical data have separate access rules.
15. File uploads are constrained.
16. High-cost endpoints can be rate-limited.
17. Retry/idempotency behavior is defined.
18. Critical endpoint tests exist.
19. API versioning is defined.
20. The API can run without a paid model/service being mandatory.

---

# 79. Suggested FastAPI Project Structure

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
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
│   │   ├── common.py
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
│   │   ├── ocr/
│   │   ├── ai/
│   │   └── chemistry/
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

Use a simpler structure if the MVP can remain clean without all modules. Do not create empty abstraction layers merely for appearance.

---

# 80. Frontend API Client Strategy

Next.js should use a typed client layer:

```text
frontend/
└── src/
    ├── lib/
    │   └── api/
    │       ├── client.ts
    │       ├── scans.ts
    │       ├── ingredients.ts
    │       ├── analyses.ts
    │       └── comparisons.ts
    └── types/
        └── api.ts
```

Do not scatter raw `fetch()` calls across UI components.

Prefer one error-normalization layer.

---

# 81. Frontend State Strategy

Separate:

### Server state
- scans
- analysis
- ingredients
- sources
- comparisons

### Local UI state
- selected ingredient
- camera state
- editing OCR
- modal state
- filters

Avoid duplicating canonical API data into many independent local states.

---

# 82. Streaming / Real-Time

MVP does not require WebSockets.

A simple approach:

```text
POST job
 ↓
poll status
 ↓
GET result
```

Use polling initially because it is simple and free-first.

Consider Server-Sent Events or WebSockets later only if real user experience demonstrates a need.

---

# 83. Background Jobs

Long-running operations may eventually use a queue.

MVP options:
- simple background task
- database status polling
- lightweight worker

Do not introduce Redis, Celery, Kafka, or another infrastructure layer unless the workload requires it.

The smallest reliable architecture wins.

---

# 84. API Security Checklist

Before deployment verify:

```text
□ No client-side secrets
□ Supabase service role server-only
□ Upload limits
□ File validation
□ Request validation
□ Rate limits
□ CORS restricted
□ Security headers
□ Prompt-injection defenses
□ Authorization checks
□ RLS policies
□ Error redaction
□ Safe logs
□ Dependency updates
```

---

# 85. CORS

Allow only known frontend origins in production.

Do not use:

```text
allow_origins=["*"]
```

for a production authenticated application unless there is a deliberate reason and compatible security model.

---

# 86. Data Consistency

When analyzing a scan:

```text
analysis_run
      ↓
analysis_items
      ↓
observations / matches / claims
```

Use database transactions for logically atomic updates.

If a stage fails, the API should report the stage state rather than leaving a record that appears fully verified.

---

# 87. API and Database Boundary

Do not make API responses mirror every database column.

Database:

```text
chemical_entities
chemical_properties
claims
claim_sources
```

API:

```text
ingredient
chemistry
evidence
confidence
limitations
```

The service layer performs the mapping.

This lets the database evolve without unnecessarily breaking the frontend.

---

# 88. API and AI Boundary

Never expose a generic endpoint such as:

```text
POST /api/chat
```

as the main product architecture.

Prefer task-specific APIs:

```text
POST /normalize
POST /match
GET /chemistry
GET /evidence
GET /explanation
```

This makes AI an implementation component rather than the product itself.

---

# 89. API and Chemistry Boundary

Never create:

```text
POST /api/generate-chemical-info
```

where the model can invent chemistry.

Instead:

```text
GET canonical entity
      ↓
chemistry service
      ↓
verified structure
      ↓
deterministic computation
```

AI may explain the result afterward.

---

# 90. API and Evidence Boundary

Never create an endpoint that marks arbitrary text as a verified scientific claim.

Every verification operation must reference:
- claim
- source
- decision
- confidence/status
- reviewer or verification process

---

# 91. API Version Compatibility

When evolving an endpoint:

### Non-breaking
Allowed:
- adding optional response fields
- adding optional request fields
- adding new enum values only when clients tolerate them

### Breaking
Requires version change:
- removing fields
- changing data type
- changing semantics
- changing required behavior

Document API changes in `CHANGELOG.md`.

---

# 92. Free-First Runtime

Preferred runtime path:

```text
Next.js
   ↓
FastAPI
   ↓
Supabase
   ↓
RDKit/local deterministic code
   ↓
Free/public approved data sources
```

AI is used only when it adds real value.

Possible zero-cost fallbacks:
- local OCR where practical
- deterministic text normalization
- local chemical lookup cache
- local RDKit calculations
- manually curated golden dataset

Do not require a paid AI call for every scanned ingredient.

---

# 93. Provider Failure Behavior

If an AI/OCR provider fails:

The app should still be useful where possible.

Example:

```text
OCR failed
 ↓
Ask user to paste/edit ingredient text
 ↓
Continue normalization/matching
```

Example:

```text
Explanation generation failed
 ↓
Show structured role + chemistry + evidence
 ↓
User still receives useful result
```

AI should improve the product, not become its single point of failure.

---

# 94. Offline / Degraded Mode

Future option:

If the network is unavailable:
- allow local manual ingredient entry
- allow local cached chemistry search
- allow local deterministic descriptors where structure is already cached

Do not promise full scan capability offline until actually implemented and tested.

---

# 95. API Documentation

FastAPI should generate OpenAPI documentation from typed schemas.

Keep descriptions useful:
- what the endpoint does
- expected inputs
- error conditions
- scientific limitations

Do not expose internal-only admin endpoints as public API without appropriate controls.

---

# 96. API Test Fixture Requirements

Maintain fixtures for:

```text
valid label
poor-quality label
OCR typo label
ambiguous ingredient
unknown ingredient
verified chemical
mixture
polymer
trade name
conflicting evidence
missing source
valid SMILES
invalid SMILES
two comparable products
two products with ambiguous overlap
```

The API tests must verify scientific behavior, not only HTTP status codes.

---

# 97. Definition of Done — API

An API feature is complete only when:

```text
Spec
 ↓
Schema
 ↓
Implementation
 ↓
Validation
 ↓
Unit tests
 ↓
Integration/contract tests
 ↓
Error states
 ↓
Security review
 ↓
Documentation
 ↓
Verified frontend use
```

No endpoint is “done” because it returns JSON in one successful test.

---

# 98. Development Order

Build the API in vertical slices.

### Slice 1 — Health + database
```text
health
DB connection
basic domains/sources
```

### Slice 2 — Scan
```text
create scan
upload validation
scan retrieval
```

### Slice 3 — OCR
```text
OCR adapter
OCR run
OCR result
```

### Slice 4 — Ingredient editing
```text
ingredient observations
user correction
normalization
```

### Slice 5 — Entity matching
```text
candidate lookup
match status
chemical entity retrieval
```

### Slice 6 — Chemistry
```text
structure validation
descriptors
chemistry view
```

### Slice 7 — Evidence
```text
claims
sources
provenance
confidence
```

### Slice 8 — Analysis
```text
complete pipeline
summary
ingredient-level results
```

### Slice 9 — Compare
```text
comparison
shared/unique/ambiguous
```

### Slice 10 — Grounded explanation
```text
verified data → AI explanation
```

Do not start with the most complex AI feature.

---

# 99. Final API Principle

> **The LabelLens API should make the correct path easy and the hallucinated path difficult: observations stay observations, candidates stay candidates, verified chemistry stays evidence-backed, computations stay reproducible, and AI stays an explanation layer rather than an authority.**

---

# 100. Stage-11 Implemented Boundary (2026-10-05)

Implemented and tested (no scans/products/OCR yet; those sections remain future):

```text
POST /api/v1/observations                    create (raw verbatim, 201)
GET  /api/v1/observations/{id}               retrieve + tree
POST /api/v1/observations/{id}/analyze       resolve + verify + persist
GET  /api/v1/observations/{id}/candidates    resolution view
GET  /api/v1/observations/{id}/resolution    same view (spec-name alias)
GET  /api/v1/observations/{id}/verification  decision + claims + evidence + history
GET  /api/v1/claims/{id}                      claim + evidence links
GET  /api/v1/reviews/pending                  bounded pagination (default 20, max 100)
GET  /api/v1/reviews/{id}                     review + event history
POST /api/v1/reviews/{id}/claim               reviewer from authentication
POST /api/v1/reviews/{id}/decision             validated, re-verified via V1-V7
```

Authentication: `Authorization: Bearer <token>` -> typed principal
(subject/role); development uses an explicit static map
(`DEV_API_TOKENS`). Supabase JWT verification was deferred at this
stage and is implemented in §101. Reviewer identity is derived
as `human:{subject}`; request bodies cannot assert identity.
Approval scope is identity-only (schema-enforced, 422 otherwise).
Errors follow the §6 envelope with spec §7 codes; request IDs are
echoed (`X-Request-ID`). No PUT/DELETE routes exist; events are
read-only. Default production registry is empty (all candidates
unresolved until a verified registry is registered).

Canonical-entity prerequisite: `analyze` and `decision` fail with
422 `ENTITY_NOT_FOUND` when the decision names an entity that is not
present in `chemical_entities`. Registering entities is a service-role
import with no route (the API never creates chemistry).

---

# 101. Stage-12 Implemented Boundary (2026-10-05)

No route was added or removed in Stage 12. The implemented changes
are authentication strength, entity registration, and rate limiting on
existing routes. Full analysis in
`STAGE_12_PRODUCTION_READINESS.md`.

## 101.1 Authentication (was "documented future" in §100)

```text
Authorization: Bearer <supabase access token (JWT)>
```

Production identity is real Supabase JWT verification
(`app/api/supabase_jwt.py`), replacing the static token map behind the
same `TokenVerifier` interface:

- signature, `alg` (bound to the key), `kid`, `iss`, `aud`, `exp`,
  `nbf`, `iat` and `sub` are verified; there is no decode-only path;
- keys come from the project JWKS document
  (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`), cached with a
  bounded TTL and refresh floor that also bounds failed fetches;
- asymmetric algorithms only (`ES256`, `RS256`); a symmetric (HS256)
  project fails closed;
- tokens whose `role` claim is a database role (`service_role`,
  `anon`, ...) are rejected, so the backend credential cannot
  authenticate as a user;
- reviewer authority comes only from `SUPABASE_REVIEWER_SUBJECTS`;
  token claims are never consulted for authorization;
- every failure category returns the identical §6/§7 response
  `401 UNAUTHORIZED` / `authentication required`; the internal reason
  is logged, never returned;
- `ENVIRONMENT=production` with no Supabase configuration, or with
  `DEV_API_TOKENS` set, refuses to build the application (503 at
  startup), never a silent fallback.

Development may still use `DEV_API_TOKENS` (`token:subject:role`);
when Supabase verification is configured it takes precedence.

## 101.2 Canonical entity registration

```text
DATABASE_URL=postgresql+asyncpg://... ENTITY_IMPORT_CONFIRM=service-role \
    python -m app.cli.import_canonical_entities \
    [--snapshot PATH] [--expect-snapshot-version canonical_v1]
```

- administrative CLI only; **no HTTP route** registers an entity
  (§100's `ENTITY_NOT_FOUND` prerequisite is unchanged and now has a
  real producer);
- approved records only (`verification_status = verified`, approved
  entity/representation types, complete provenance), no chemistry is
  computed or inferred;
- whole-artifact validation before any write; all-or-nothing
  transaction; deterministic JSON report of rejections; idempotent
  re-runs (`ON CONFLICT DO NOTHING`, stable entity ids);
- provenance is stored in `chemical_entities.metadata`;
- the resolver registry is projected from those rows at startup; a
  failed load leaves it empty (all candidates unresolved). A re-run
  requires an application restart to become visible.

## 101.3 Rate limiting (429 / 503)

Limited operations, keyed on the authenticated principal:

```text
POST /api/v1/observations                    observations.create   30/60s
POST /api/v1/observations/{id}/analyze       observations.analyze  20/60s
POST /api/v1/reviews/{id}/decision           reviews.decision      20/60s
```

All other routes are unlimited. Budgets are configuration
(`RATE_LIMIT_OBSERVATION_CREATE`, `RATE_LIMIT_ANALYZE`,
`RATE_LIMIT_REVIEW_DECISION`, `RATE_LIMIT_ENABLED`); no route contains
a hard-coded limit.

Refusal (§7 `RATE_LIMITED`, §8 `429`), with §9 request correlation:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
```

```json
{"error": {"code": "RATE_LIMITED", "message": "too many requests",
           "details": {"retry_after_seconds": 60,
                       "action": "observations.create"}},
 "meta": {"request_id": "…", "api_version": "v1"}}
```

`details.action` names the limited operation and `retry_after_seconds`
mirrors the `Retry-After` header; no bucket internals, subjects, or
counters are disclosed. When the limiter backend fails, the write is
refused with §8 `503` and §7 `RATE_LIMITER_UNAVAILABLE` (fail closed)
rather than admitted.

The identity used for bucketing comes from the verified token; no
header or body field can influence it. The shipped limiter is
in-process and therefore per replica — a shared backend is the
documented next step.
