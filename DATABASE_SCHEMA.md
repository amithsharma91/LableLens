# LabelLens — Database Schema

**Document:** DATABASE_SCHEMA.md  
**Project:** LabelLens  
**Version:** 1.0  
**Database:** PostgreSQL via Supabase  
**Purpose:** Define the persistent data model, relationships, integrity rules, indexes, provenance, versioning, and security boundaries for LabelLens.

---

# 1. Database Objective

The database must preserve the complete journey from a real label to a verified chemical explanation.

```text
Product / Label
      ↓
Scan
      ↓
OCR observation
      ↓
Ingredient observation
      ↓
Normalization
      ↓
Entity candidates
      ↓
Chemical entity
      ↓
Verified facts
      ↓
Domain role
      ↓
Evidence / claims
      ↓
Analysis
      ↓
Explanation
```

The database must never collapse these stages into a single `ingredients` text field.

The central architectural rule is:

> **Raw observations, normalized data, verified scientific facts, contextual roles, computed values, and AI-generated explanations are different data classes and must remain distinguishable.**

---

# 2. Design Principles

1. **PostgreSQL is the source of structured application truth.**
2. **Scientific facts are provenance-aware.**
3. **Every important fact can be connected to a claim/source.**
4. **OCR output is not verified chemistry.**
5. **AI output is not a primary data source.**
6. **Unknown values use NULL/status fields, never fabricated placeholders.**
7. **Core scientific fields are normalized into columns; flexible metadata may use JSONB.**
8. **Historical scan observations should remain immutable/auditable.**
9. **Current canonical chemical records may evolve with versioned verification.**
10. **MVP schema should be small enough to maintain but extensible to more domains.**

---

# 3. Logical Architecture

```text
                           ┌───────────────┐
                           │    sources    │
                           └──────┬────────┘
                                  │
                                  ▼
┌──────────┐       ┌──────────────────────────┐
│ products │──────▶│       product_scans      │
└────┬─────┘       └────────────┬─────────────┘
     │                           │
     │                           ▼
     │                ┌──────────────────────┐
     │                │ ingredient_observ.   │
     │                └──────────┬───────────┘
     │                           │
     │                           ▼
     │                ┌──────────────────────┐
     │                │ ingredient_candidates│
     │                └──────────┬───────────┘
     │                           │
     │                           ▼
     │                ┌──────────────────────┐
     │                │ entity_matches       │
     │                └──────────┬───────────┘
     │                           │
     │                           ▼
     │                ┌──────────────────────┐
     │                │ chemical_entities    │
     │                └──────────┬───────────┘
     │                           │
     │             ┌─────────────┼──────────────┐
     │             ▼             ▼              ▼
     │        structures     properties      roles
     │                           │              │
     │                           └──────┬───────┘
     │                                  ▼
     │                             claims
     │                                  │
     │                                  ▼
     │                             claim_sources
     │                                  │
     ▼                                  ▼
analysis_runs ───────────────────▶ evidence
     │
     ▼
analysis_items
     │
     ▼
comparisons
```

---

# 4. Identifier Strategy

All primary keys should use UUIDs.

Recommended PostgreSQL type:

```sql
uuid
```

Generate IDs database-side where practical.

Benefits:
- safe for distributed agents/services
- avoids sequential public IDs
- easier offline/import workflows
- supports future service separation

Public URLs should use short application identifiers if needed; do not expose internal sequential IDs.

---

# 5. Common Column Conventions

Use consistent columns:

```text
id
created_at
updated_at
```

Timestamp type:

```sql
timestamptz
```

Do not store important timestamps as text.

For records that are verified or externally sourced, also use explicit timestamps such as:

```text
first_verified_at
last_verified_at
retrieved_at
published_at
```

---

# 6. ENUM / Controlled Vocabulary Strategy

For small stable states, PostgreSQL enums are acceptable.

For rapidly evolving taxonomies, use lookup tables.

Recommended database-level states:

### Match status
```text
exact_match
strong_match
probable_match
ambiguous
no_match
invalid_input
```

### Verification status
```text
verified
supported
computed
provisional
candidate
unverified
conflicted
unknown
obsolete
```

### Representation type
```text
single_molecule
salt
polymer
material
mixture
natural_complex
formulation
trade_name
unknown
```

### Source type
```text
regulatory
government
scientific_database
primary_literature
review
manufacturer
institutional
secondary
discovery
```

### Data provenance type
```text
label_observation
ocr
user_entered
user_corrected
source_reported
computed
ai_candidate
manual_review
```

Do not overuse enums for values likely to change by domain.

---

# 7. TABLE: products

Represents a product identity known to the application.

```text
products
--------
id UUID PK
brand_name TEXT
product_name TEXT NOT NULL
product_type TEXT
domain_id UUID NULL
country_code TEXT NULL
barcode TEXT NULL
manufacturer TEXT NULL
description TEXT NULL
canonical_status TEXT
metadata JSONB
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Rules

- Product name is required when a persistent product record is created.
- Product identity must not be inferred solely from a barcode.
- Barcode is optional.
- Country/jurisdiction may matter for label interpretation.
- `metadata` is for non-core fields, not a substitute for normalized scientific data.

### Indexes

```text
products(barcode)
products(domain_id)
products(brand_name, product_name)
```

---

# 8. TABLE: product_labels

Represents a specific label/version observed for a product.

This is important because formulations and labels can change.

```text
product_labels
--------------
id UUID PK
product_id UUID NOT NULL FK → products.id
label_version TEXT NULL
market_country TEXT NULL
label_date DATE NULL
source_type TEXT
source_url TEXT NULL
image_storage_path TEXT NULL
raw_label_text TEXT NULL
label_hash TEXT NULL
status TEXT
metadata JSONB
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Important distinction

```text
product
   ≠
specific product label/version
```

A historical scan should remain linked to the label version actually observed.

---

# 9. TABLE: product_scans

Represents an individual user scan/analysis event.

```text
product_scans
-------------
id UUID PK
product_id UUID NULL FK → products.id
product_label_id UUID NULL FK → product_labels.id
user_id UUID NULL
image_storage_path TEXT NULL
input_method TEXT NOT NULL
raw_image_hash TEXT NULL
ocr_engine TEXT NULL
ocr_model_version TEXT NULL
ocr_confidence NUMERIC NULL
scan_status TEXT
privacy_status TEXT
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Input methods

```text
camera
upload
manual_text
import
```

### Rules

A scan is an observation event.

It should not automatically mutate canonical chemical entities.

---

# 10. TABLE: ocr_runs

Stores OCR attempts independently from scans.

```text
ocr_runs
--------
id UUID PK
scan_id UUID NOT NULL FK → product_scans.id
engine TEXT
model_version TEXT
raw_text TEXT
structured_output JSONB
overall_confidence NUMERIC NULL
status TEXT
error_code TEXT NULL
created_at TIMESTAMPTZ
```

Multiple OCR runs may exist for one scan.

This supports:
- model comparison
- retries
- debugging
- regression tests

---

# 11. TABLE: ingredient_observations

Represents what the label appears to contain.

```text
ingredient_observations
-----------------------
id UUID PK
scan_id UUID NOT NULL FK → product_scans.id
sequence_number INTEGER NOT NULL
raw_text TEXT NOT NULL
display_text TEXT NULL
source_type TEXT NOT NULL
ocr_run_id UUID NULL FK → ocr_runs.id
ocr_confidence NUMERIC NULL
user_corrected BOOLEAN NOT NULL DEFAULT FALSE
original_text TEXT NULL
correction_reason TEXT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Example

```text
raw_text:
"Sodiurn Benzoate"

display_text:
"Sodium Benzoate"

source_type:
user_corrected

user_corrected:
true
```

The original observation must remain recoverable.

---

# 12. TABLE: ingredient_normalizations

Stores normalized forms separately from raw observations.

```text
ingredient_normalizations
-------------------------
id UUID PK
observation_id UUID NOT NULL FK → ingredient_observations.id
normalized_text TEXT NOT NULL
normalization_method TEXT NOT NULL
normalizer_version TEXT NULL
confidence NUMERIC NULL
status TEXT NOT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Normalization methods

```text
rule
dictionary
database_alias
model_candidate
manual
hybrid
```

A normalization is not automatically a chemical identity.

---

# 13. TABLE: ingredient_candidates

Stores possible entities proposed for a normalized ingredient.

```text
ingredient_candidates
---------------------
id UUID PK
normalization_id UUID NOT NULL FK → ingredient_normalizations.id
chemical_entity_id UUID NULL FK → chemical_entities.id
candidate_name TEXT NOT NULL
match_status TEXT NOT NULL
candidate_score NUMERIC NULL
match_reasons JSONB
source_id UUID NULL FK → sources.id
created_at TIMESTAMPTZ
```

### Rules

- Candidate scores are ranking aids, not calibrated probabilities.
- Candidates remain candidates until verification criteria are satisfied.
- Multiple candidates are allowed for an ambiguous input.

---

# 14. TABLE: entity_matches

Stores the selected resolution decision.

```text
entity_matches
--------------
id UUID PK
normalization_id UUID NOT NULL FK → ingredient_normalizations.id
chemical_entity_id UUID NULL FK → chemical_entities.id
match_status TEXT NOT NULL
identity_confidence TEXT NOT NULL
selected_by TEXT
selected_at TIMESTAMPTZ
reason_code TEXT NULL
review_status TEXT NULL
review_notes TEXT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Selected-by values

```text
deterministic
source_match
manual_review
user_confirmed
hybrid
```

An unresolved observation can have:

```text
chemical_entity_id = NULL
match_status = no_match / ambiguous / invalid_input
```

Do not insert a fake entity.

---

# 15. TABLE: chemical_entities

Canonical chemistry entity.

```text
chemical_entities
-----------------
id UUID PK
preferred_name TEXT NOT NULL
entity_type TEXT NOT NULL
representation_type TEXT NOT NULL
status TEXT NOT NULL

formula TEXT NULL
molecular_weight NUMERIC NULL
molecular_weight_unit TEXT NULL

cas_number TEXT NULL
pubchem_cid BIGINT NULL
chebi_id TEXT NULL
inchi TEXT NULL
inchikey TEXT NULL

smiles TEXT NULL
canonical_smiles TEXT NULL
isomeric_smiles TEXT NULL

chemical_class TEXT NULL
superclass TEXT NULL

structure_status TEXT
structure_source_id UUID NULL FK → sources.id

metadata JSONB

first_verified_at TIMESTAMPTZ NULL
last_verified_at TIMESTAMPTZ NULL

created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Critical rules

- This table contains canonical entities, not raw labels.
- `smiles` may be NULL.
- `formula` may be NULL.
- `molecular_weight` may be NULL.
- `representation_type` determines whether a structure is appropriate.
- A valid SMILES string is not proof that the label refers to that molecule.

---

# 16. TABLE: ingredient_aliases

Maps names to canonical entities.

```text
ingredient_aliases
------------------
id UUID PK
chemical_entity_id UUID NOT NULL FK → chemical_entities.id
alias TEXT NOT NULL
alias_type TEXT NOT NULL
language_code TEXT NULL
region_code TEXT NULL
source_id UUID NULL FK → sources.id
verified BOOLEAN NOT NULL DEFAULT FALSE
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Alias types

```text
label_name
common_name
systematic_name
synonym
abbreviation
additive_number
trade_name
regional_variant
translation
historical_name
```

Unique constraint should prevent duplicate alias/entity pairs.

---

# 17. TABLE: chemical_identifiers

Use this optional normalized table when the project grows.

```text
chemical_identifiers
--------------------
id UUID PK
chemical_entity_id UUID NOT NULL FK → chemical_entities.id
identifier_type TEXT NOT NULL
identifier_value TEXT NOT NULL
source_id UUID NULL FK → sources.id
verification_status TEXT NOT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

This is preferable to adding every future identifier as a new column.

For MVP, frequently used identifiers can remain in `chemical_entities` while this table is introduced later.

---

# 18. TABLE: chemical_structures

Recommended V2 structure table.

```text
chemical_structures
-------------------
id UUID PK
chemical_entity_id UUID NOT NULL FK → chemical_entities.id
representation_type TEXT NOT NULL
smiles TEXT NULL
inchi TEXT NULL
molfile TEXT NULL
standardization_method TEXT NULL
software_name TEXT NULL
software_version TEXT NULL
validation_status TEXT NOT NULL
source_id UUID NULL FK → sources.id
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

This supports multiple validated representations without overwriting historical values.

For MVP, structure fields may remain in `chemical_entities`.

---

# 19. TABLE: chemical_properties

Stores field-level chemical property records.

```text
chemical_properties
-------------------
id UUID PK
chemical_entity_id UUID NOT NULL FK → chemical_entities.id
property_name TEXT NOT NULL
property_value_numeric NUMERIC NULL
property_value_text TEXT NULL
unit TEXT NULL
provenance_type TEXT NOT NULL
source_id UUID NULL FK → sources.id
method TEXT NULL
software_name TEXT NULL
software_version TEXT NULL
input_representation TEXT NULL
verification_status TEXT NOT NULL
measured_at TIMESTAMPTZ NULL
calculated_at TIMESTAMPTZ NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Examples

```text
molecular_weight
exact_mass
TPSA
H_bond_donors
H_bond_acceptors
rotatable_bonds
logP
density
melting_point
```

Only properties appropriate to the entity should be stored.

---

# 20. TABLE: chemical_descriptors

Optional normalized shortcut for frequently used RDKit descriptors.

```text
chemical_descriptors
--------------------
id UUID PK
chemical_entity_id UUID NOT NULL FK → chemical_entities.id
descriptor_name TEXT NOT NULL
value_numeric NUMERIC NULL
unit TEXT NULL
software_name TEXT NOT NULL
software_version TEXT NOT NULL
input_structure_id UUID NULL
calculation_hash TEXT NULL
created_at TIMESTAMPTZ
```

### Rule

A descriptor is stored as `computed`, not as experimental evidence.

---

# 21. TABLE: domains

Supported product domains.

```text
domains
-------
id UUID PK
code TEXT UNIQUE NOT NULL
name TEXT UNIQUE NOT NULL
description TEXT NULL
active BOOLEAN NOT NULL DEFAULT TRUE
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Initial examples:

```text
food
snacks
beverage
cosmetics
personal_care
household
supplement
pharma
other
```

---

# 22. TABLE: roles

Domain-specific ingredient roles.

```text
roles
-----
id UUID PK
domain_id UUID NOT NULL FK → domains.id
code TEXT NOT NULL
name TEXT NOT NULL
description TEXT NULL
taxonomy_version TEXT NOT NULL
active BOOLEAN NOT NULL DEFAULT TRUE
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Examples:

```text
Food:
preservative
sweetener
colour
acidity_regulator
antioxidant
emulsifier
stabilizer
thickener
flavouring

Cosmetic:
surfactant
humectant
emollient
preservative
solvent
fragrance
pH_adjuster

Pharma:
active_ingredient
excipient
binder
filler
coating_agent
preservative
solvent
```

These are taxonomy values, not chemical identity properties.

---

# 23. TABLE: entity_roles

Connects chemical/entity records to domain-specific roles.

```text
entity_roles
------------
id UUID PK
chemical_entity_id UUID NOT NULL FK → chemical_entities.id
domain_id UUID NOT NULL FK → domains.id
role_id UUID NOT NULL FK → roles.id
status TEXT NOT NULL
confidence TEXT NOT NULL
source_id UUID NULL FK → sources.id
context_notes TEXT NULL
taxonomy_version TEXT NOT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Important

The same chemical may have different roles across domains.

Therefore:

```text
chemical_entity
      +
domain
      +
role
```

is the actual contextual relationship.

---

# 24. TABLE: sources

Canonical source registry.

```text
sources
-------
id UUID PK
name TEXT NOT NULL
publisher TEXT NULL
source_type TEXT NOT NULL
url TEXT NULL
identifier TEXT NULL
jurisdiction TEXT NULL
language_code TEXT NULL

authority_level TEXT NOT NULL
license TEXT NULL
redistribution_allowed BOOLEAN NULL
caching_allowed BOOLEAN NULL

publication_date DATE NULL
retrieved_at TIMESTAMPTZ NULL
last_checked_at TIMESTAMPTZ NULL
freshness_class TEXT NULL

status TEXT NOT NULL
notes TEXT NULL

created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

This table is aligned with `SOURCE_REGISTRY.md`.

---

# 25. TABLE: claims

Claims are the core evidence unit.

```text
claims
------
id UUID PK

chemical_entity_id UUID NULL FK → chemical_entities.id
product_id UUID NULL FK → products.id
product_label_id UUID NULL FK → product_labels.id
entity_role_id UUID NULL FK → entity_roles.id

claim_type TEXT NOT NULL
field_name TEXT NULL

claim_value_text TEXT NULL
claim_value_numeric NUMERIC NULL
claim_value_json JSONB NULL
unit TEXT NULL

provenance_type TEXT NOT NULL
verification_status TEXT NOT NULL
confidence TEXT NOT NULL

valid_from TIMESTAMPTZ NULL
valid_until TIMESTAMPTZ NULL

created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Claim examples

```text
chemical_identity
formula
molecular_weight
smiles
product_contains_ingredient
ingredient_role
regulatory_status
experimental_property
computed_descriptor
```

A claim must point to the correct subject.

---

# 26. TABLE: claim_sources

Many-to-many relation between claims and sources.

```text
claim_sources
-------------
claim_id UUID NOT NULL FK → claims.id
source_id UUID NOT NULL FK → sources.id

support_type TEXT NOT NULL
support_strength TEXT NOT NULL
source_locator TEXT NULL
source_value TEXT NULL
review_status TEXT NULL
review_notes TEXT NULL

created_at TIMESTAMPTZ

PRIMARY KEY (claim_id, source_id)
```

### Support types

```text
direct
contextual
secondary
discovery
contradictory
```

A contradictory source should not be deleted; it is useful for conflict handling.

---

# 27. TABLE: verification_events

Audit trail for evidence decisions.

```text
verification_events
-------------------
id UUID PK
claim_id UUID NOT NULL FK → claims.id
previous_status TEXT NULL
new_status TEXT NOT NULL
previous_confidence TEXT NULL
new_confidence TEXT NULL
review_method TEXT NOT NULL
reviewer_type TEXT NOT NULL
reason TEXT NULL
source_id UUID NULL FK → sources.id
created_at TIMESTAMPTZ
```

### Reviewer types

```text
system
human
researcher
admin
```

AI alone should not be treated as a final human reviewer.

---

# 28. TABLE: user_corrections

Tracks user corrections separately.

```text
user_corrections
----------------
id UUID PK
scan_id UUID NOT NULL FK → product_scans.id
observation_id UUID NULL FK → ingredient_observations.id
field_name TEXT NOT NULL
old_value TEXT NULL
new_value TEXT NULL
correction_type TEXT NOT NULL
created_at TIMESTAMPTZ
```

This enables:
- correction analytics
- OCR improvement
- regression dataset creation

A user correction can improve the observation but does not automatically verify chemistry.

---

# 29. TABLE: analysis_runs

Represents a complete analysis execution.

```text
analysis_runs
-------------
id UUID PK
scan_id UUID NOT NULL FK → product_scans.id
pipeline_version TEXT NOT NULL
ocr_version TEXT NULL
normalizer_version TEXT NULL
matcher_version TEXT NULL
role_classifier_version TEXT NULL
chemistry_engine_version TEXT NULL
explanation_model TEXT NULL
status TEXT NOT NULL
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ NULL
error_code TEXT NULL
metadata JSONB
created_at TIMESTAMPTZ
```

This makes analysis reproducible.

---

# 30. TABLE: analysis_items

Represents the result of analyzing each ingredient observation.

```text
analysis_items
--------------
id UUID PK
analysis_run_id UUID NOT NULL FK → analysis_runs.id
observation_id UUID NOT NULL FK → ingredient_observations.id
normalization_id UUID NULL FK → ingredient_normalizations.id
entity_match_id UUID NULL FK → entity_matches.id

role_id UUID NULL FK → roles.id

identity_status TEXT NOT NULL
role_status TEXT NULL
display_confidence TEXT NOT NULL

explanation_status TEXT NULL
explanation_text TEXT NULL
explanation_grounding JSONB NULL

created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Rule

`explanation_text` is derived output, not canonical chemistry data.

---

# 31. TABLE: comparisons

Represents a user comparison between two analyzed products.

```text
comparisons
-----------
id UUID PK
left_scan_id UUID NOT NULL FK → product_scans.id
right_scan_id UUID NOT NULL FK → product_scans.id
comparison_version TEXT NOT NULL
status TEXT NOT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

---

# 32. TABLE: comparison_items

Stores ingredient-level comparison results.

```text
comparison_items
----------------
id UUID PK
comparison_id UUID NOT NULL FK → comparisons.id
left_observation_id UUID NULL FK → ingredient_observations.id
right_observation_id UUID NULL FK → ingredient_observations.id
chemical_entity_id UUID NULL FK → chemical_entities.id

comparison_type TEXT NOT NULL
match_confidence TEXT NULL
notes TEXT NULL
created_at TIMESTAMPTZ
```

Comparison types:

```text
shared
left_only
right_only
ambiguous
chemically_related
```

Do not treat “chemically related” as identical.

---

# 33. TABLE: audit_log

General application audit trail.

```text
audit_log
---------
id UUID PK
actor_type TEXT NOT NULL
actor_id UUID NULL
entity_type TEXT NOT NULL
entity_id UUID NOT NULL
action TEXT NOT NULL
old_data JSONB NULL
new_data JSONB NULL
reason TEXT NULL
created_at TIMESTAMPTZ
```

Use for important mutations, not every read.

---

# 34. Optional TABLE: model_runs

Useful when AI is used extensively.

```text
model_runs
----------
id UUID PK
run_type TEXT NOT NULL
provider TEXT NOT NULL
model_name TEXT NOT NULL
model_version TEXT NULL
prompt_version TEXT NULL
input_hash TEXT NULL
output_hash TEXT NULL
status TEXT NOT NULL
tokens_in INTEGER NULL
tokens_out INTEGER NULL
latency_ms INTEGER NULL
cost_estimate NUMERIC NULL
created_at TIMESTAMPTZ
```

This supports:
- AI evaluation
- prompt regression
- cost tracking
- provider comparison

Do not store sensitive user content unnecessarily.

---

# 35. Optional TABLE: source_snapshots

For reproducibility where licensing permits.

```text
source_snapshots
---------------
id UUID PK
source_id UUID NOT NULL FK → sources.id
content_hash TEXT NOT NULL
snapshot_reference TEXT NULL
captured_at TIMESTAMPTZ
storage_path TEXT NULL
retention_status TEXT
```

Only use this where source terms permit storage.

---

# 36. Core Relationships

```text
products
  1 ─── N product_labels

product_labels
  1 ─── N product_scans

product_scans
  1 ─── N ocr_runs

product_scans
  1 ─── N ingredient_observations

ingredient_observations
  1 ─── N ingredient_normalizations

ingredient_normalizations
  1 ─── N ingredient_candidates

ingredient_normalizations
  1 ─── N entity_matches

entity_matches
  N ─── 1 chemical_entities

chemical_entities
  1 ─── N ingredient_aliases

chemical_entities
  1 ─── N chemical_properties

chemical_entities
  N ─── N domains/roles through entity_roles

claims
  N ─── N sources through claim_sources

analysis_runs
  1 ─── N analysis_items

comparisons
  1 ─── N comparison_items
```

---

# 37. Critical Integrity Constraints

### Prevent duplicate aliases

Unique:

```text
chemical_entity_id + normalized(alias)
```

### Prevent duplicate roles

Unique:

```text
chemical_entity_id + domain_id + role_id + taxonomy_version
```

### Prevent duplicate source relationships

Primary key:

```text
claim_id + source_id
```

### Prevent impossible analysis references

An `analysis_item` must refer to an ingredient observation belonging to the same scan as the analysis run.

This may require:
- application validation
- database triggers
- composite foreign keys

Prefer database enforcement where practical.

---

# 38. NULL Strategy

Use NULL when a value is genuinely unavailable.

Examples:

```text
smiles = NULL
cas_number = NULL
molecular_weight = NULL
```

Do NOT use:

```text
"unknown"
"N/A"
"-"
"0"
"not applicable"
```

inside scientific value columns.

Instead use a dedicated status:

```text
verification_status
representation_type
```

Example:

```text
smiles = NULL
representation_type = mixture
structure_status = not_applicable
```

---

# 39. Scientific Status vs Database Presence

A non-NULL field does not automatically mean verified.

Bad assumption:

```text
smiles IS NOT NULL
        ↓
verified
```

Correct:

```text
smiles exists
      +
structure_status
      +
claim/evidence
      +
verification status
```

The schema must support this distinction.

---

# 40. Candidate Data Should Be Isolated

AI/model candidates should not overwrite canonical tables.

Preferred:

```text
candidate
   ↓
candidate table
   ↓
verification
   ↓
canonical entity/claim
```

Never:

```text
AI output
   ↓
UPDATE chemical_entities
```

without validation.

---

# 41. Versioning Strategy

At minimum version:

```text
pipeline_version
normalizer_version
matcher_version
role_taxonomy_version
chemistry_engine_version
source version/date
explanation prompt version
```

When a material scientific algorithm changes, new analysis runs should be distinguishable from historical runs.

Do not silently rewrite historical scan results.

---

# 42. Product History Strategy

Product formulas may change.

Therefore:

```text
Product
   ├── Label version A
   │      └── Scan 1
   ├── Label version B
   │      └── Scan 2
   └── Label version C
          └── Scan 3
```

A scan should preserve what the user actually observed.

The current canonical `products` record should not erase historical label observations.

---

# 43. Evidence Storage Rules

The database should allow the following:

```text
ChemicalEntity
   ↓
Claim: formula
   ↓
Source A

ChemicalEntity
   ↓
Claim: role in food context
   ↓
Source B

ChemicalEntity
   ↓
Claim: descriptor
   ↓
Computed with RDKit
```

Different fields can therefore have different evidence and status.

---

# 44. AI Explanation Storage

Never store only:

```text
ingredient.explanation = "..."
```

Instead store:

```text
analysis_items
    explanation_text
    explanation_status
    explanation_grounding
```

`explanation_grounding` should reference:
- claim IDs used
- evidence/source IDs
- prompt version
- model used
- generation timestamp
- limitations

The canonical scientific data remains independent of the AI wording.

---

# 45. Free-First Database Architecture

For early development:

```text
Supabase Postgres
      +
small verified chemistry dataset
      +
external source adapters
      +
local caching where licensing allows
```

Avoid designing the database around a paid third-party API.

External lookup code must live behind an adapter/service layer.

Example:

```text
ChemicalDataProvider
 ├── provider_one
 ├── provider_two
 └── local_cache
```

The database should not care which provider supplied a verified fact.

---

# 46. Recommended Indexes

Create indexes for high-frequency operations.

### Products

```text
barcode
domain_id
brand_name
product_name
```

### Ingredient observations

```text
scan_id
scan_id + sequence_number
```

### Normalizations

```text
normalized_text
observation_id
```

### Candidates

```text
normalization_id
chemical_entity_id
match_status
```

### Chemical entities

```text
preferred_name
inchikey
cas_number
pubchem_cid
```

### Aliases

```text
alias
chemical_entity_id
```

### Claims

```text
chemical_entity_id
claim_type
field_name
verification_status
```

### Claim sources

```text
source_id
```

### Analysis

```text
scan_id
analysis_run_id
observation_id
```

Do not create indexes blindly. Validate with query plans as the dataset grows.

---

# 47. Search Strategy

For human ingredient search:

### MVP
- Exact normalized name
- Prefix search
- Alias search
- Identifier search

### Later
- PostgreSQL full-text search
- Trigram similarity
- Chemical similarity/substructure through a separate chemistry service if appropriate

Text similarity should not be treated as chemical identity verification.

---

# 48. RLS / Supabase Security Model

If user accounts are introduced:

### User-owned data

```text
product_scans
user_corrections
comparisons
private scan images
```

must be restricted by authenticated user ownership.

### Public/canonical data

Potentially public:
- verified chemical entities
- approved source metadata
- public role taxonomy
- public claims

But write access must be limited.

### Service role

Server-side service credentials must never be exposed to the browser.

Use server/API boundaries for:
- source ingestion
- canonical data writes
- verification
- privileged operations

---

# 49. Storage Strategy

Do not put large label images directly into PostgreSQL.

Use object storage for:
- uploaded images
- cropped label images
- optional OCR artifacts

Store only references in the database:

```text
image_storage_path
image_hash
mime_type
size_bytes
```

Raw images should have a retention policy.

---

# 50. Privacy Strategy

Default principle:

> **Store the minimum data needed for the feature.**

Recommended:
- Do not store images permanently unless necessary.
- Hash images for duplicate detection where useful.
- Remove EXIF metadata when possible.
- Do not move user-private data into public datasets.
- Separate private scan records from canonical public chemistry data.

---

# 51. Data Import Strategy

For importing chemistry data:

```text
External source
   ↓
raw import/staging
   ↓
normalization
   ↓
validation
   ↓
deduplication
   ↓
source attachment
   ↓
canonical entity
```

Do not bulk-write third-party datasets directly into production canonical tables.

---

# 52. Staging Tables

When importing large datasets, use staging tables such as:

```text
staging_chemical_entities
staging_aliases
staging_properties
staging_sources
```

Perform:
- schema checks
- duplicate detection
- identifier validation
- source validation
- transformation
- sampling/manual review

before promotion.

---

# 53. Migration Strategy

Database changes must use versioned migrations.

Example:

```text
001_initial_schema.sql
002_add_source_registry.sql
003_add_claim_provenance.sql
004_add_chemical_properties.sql
```

Never manually modify production schema without recording the change.

Every migration should be:
- deterministic
- reviewable
- reversible when practical
- tested against a clean database

---

# 54. Seed Data

MVP seed data should include:

### Domains
All initial domains.

### Roles
A reviewed initial taxonomy.

### Sources
Only approved source registry entries.

### Chemistry
A small manually verified golden dataset.

Do not seed hundreds/thousands of AI-generated chemical records.

---

# 55. Golden Dataset Tables

The 100-entity golden chemistry dataset can use the same production schema.

Required quality:

```text
identity verified
aliases reviewed
structure validated if applicable
formula verified if applicable
molecular data sourced
roles sourced
source provenance stored
confidence assigned
```

The test dataset should be versioned outside production data.

---

# 56. Test Data Separation

Never mix regression fixtures with user production records.

Suggested project files:

```text
/tests/fixtures/labels/
/tests/fixtures/chemistry/
/tests/fixtures/expected/
```

Database seed/test environment should be separate from production.

---

# 57. Transaction Boundaries

An analysis request may touch:

```text
analysis_runs
analysis_items
normalizations
matches
claims
```

Use transactions where multiple writes represent one logical state transition.

Example:

```text
START TRANSACTION
  create analysis_run
  create/update analysis_items
  write verified references
COMMIT
```

If validation fails, do not leave a partially “verified” state.

---

# 58. Idempotency

Repeated requests should not create duplicate canonical data.

Use hashes/keys such as:

```text
label_hash
input_hash
chemical identifier
normalized alias
calculation_hash
```

For expensive processing, store run IDs and status.

---

# 59. Failure State Model

Every pipeline stage should have explicit statuses.

Example:

```text
scan:
uploaded
processing
failed
complete

ocr:
queued
running
complete
failed

matching:
queued
running
partial
complete
failed

analysis:
queued
running
partial
complete
failed
```

Partial analysis is allowed when some ingredients are unresolved.

---

# 60. Data Freshness

For externally sourced claims store:

```text
retrieved_at
last_checked_at
freshness_class
```

Dynamic claims should be revalidated more aggressively than stable chemical identity.

Do not delete old evidence when a newer source appears.

---

# 61. Historical Truth

A scan record represents:

> **What LabelLens observed and analyzed at that time.**

Therefore historical analysis results should be immutable or revisioned.

If the same ingredient is later corrected, do not silently change the historical analysis record.

Create a new analysis version if needed.

---

# 62. Explainability Data Flow

```text
analysis_item
      ↓
claim IDs
      ↓
claim_sources
      ↓
sources
      ↓
AI explanation
```

The UI can therefore show:

> “This explanation is based on these verified facts.”

---

# 63. API Boundary

The frontend should never directly mutate canonical chemistry data.

Preferred:

```text
Browser
  ↓
Next.js/API
  ↓
FastAPI
  ↓
database service
```

Only trusted server-side services may:
- create verified chemical records
- approve claims
- change verification states
- ingest external data

---

# 64. Recommended MVP Table Set

Do NOT implement every table on Day 1.

Start with:

```text
domains
roles
products
product_labels
product_scans
ocr_runs
ingredient_observations
ingredient_normalizations
ingredient_candidates
entity_matches
chemical_entities
ingredient_aliases
chemical_properties
entity_roles
sources
claims
claim_sources
analysis_runs
analysis_items
comparisons
comparison_items
user_corrections
verification_events
```

Add later:

```text
chemical_identifiers
chemical_structures
chemical_descriptors
model_runs
source_snapshots
audit_log
staging_*
```

---

# 65. MVP Minimal Relationship

For the first vertical slice, the absolute minimum is:

```text
product_scans
     ↓
ingredient_observations
     ↓
ingredient_normalizations
     ↓
entity_matches
     ↓
chemical_entities
     ↓
entity_roles
     ↓
claims
     ↓
claim_sources
```

This is enough to demonstrate the core scientific data flow.

---

# 66. Example End-to-End Record

A user scans a label.

### Product

```text
products
id = P1
name = Example Snack
domain = food
```

### Observation

```text
ingredient_observations
raw_text = "Sodiurn Benzoate"
```

### Normalization

```text
ingredient_normalizations
normalized_text = "Sodium Benzoate"
status = verified_candidate
```

### Candidate

```text
ingredient_candidates
candidate = Sodium Benzoate entity
match_status = strong_match
```

### Match

```text
entity_matches
chemical_entity_id = CE1
match_status = exact_match
```

### Chemical entity

```text
chemical_entities
preferred_name = Sodium benzoate
formula = sourced_value
smiles = sourced_value
```

### Role

```text
entity_roles
domain = food
role = preservative
```

### Evidence

```text
claims
claim_type = ingredient_role
verification_status = supported
```

### Source

```text
claim_sources
source = approved authoritative source
```

### Analysis

```text
analysis_items
identity_status = verified
role_status = supported
```

### Explanation

Generated only from those verified/supportable records.

---

# 67. Query Patterns

Common queries should be predictable.

### Find ingredient by normalized alias

```text
ingredient_aliases.alias
        ↓
chemical_entity_id
```

### Find product ingredients

```text
product_scans
 → ingredient_observations
 → normalizations
 → matches
 → chemical_entities
```

### Find evidence

```text
claims
 → claim_sources
 → sources
```

### Compare products

```text
left scan ingredient entities
        ↕
right scan ingredient entities
```

---

# 68. Data Retention

Suggested default:

### Temporary
- Raw upload
- Intermediate OCR artifacts
- failed model outputs

### Long-term
- verified chemical data
- approved sources
- claims
- audit/provenance
- anonymized benchmark results

Actual retention must follow product privacy decisions and applicable requirements.

---

# 69. Database Anti-Hallucination Constraints

The schema should make bad behavior difficult.

### Do not allow
- Verified claim without a claim subject.
- Verified chemistry with no appropriate verification metadata.
- AI-generated candidate written directly into canonical verified state.
- Structure for a mixture unless explicitly appropriate and supported.
- Product role stored as a property of the chemical entity itself.
- Historical scan mutation without a recorded event.

Where practical, enforce these with:
- CHECK constraints
- foreign keys
- triggers
- server-side validation

---

# 70. Suggested CHECK Constraints

Examples:

```sql
CHECK (
  molecular_weight IS NULL
  OR molecular_weight > 0
)
```

```sql
CHECK (
  status <> 'verified'
  OR last_verified_at IS NOT NULL
)
```

```sql
CHECK (
  provenance_type <> 'computed'
  OR method IS NOT NULL
)
```

```sql
CHECK (
  representation_type NOT IN ('mixture', 'natural_complex', 'formulation')
  OR smiles IS NULL
  OR structure_status IN ('not_applicable', 'unavailable')
)
```

The exact constraint logic must be tested before production because complex chemical cases may require exceptions.

---

# 71. Security Rules

Never store:
- API keys
- model provider secrets
- database service-role keys
- private credentials

inside database records.

Use environment secrets on trusted server infrastructure.

Do not log sensitive upload contents into application logs by default.

---

# 72. Performance Rules

Do not retrieve huge nested graphs for every screen.

### Ingredient page

Fetch:
```text
chemical entity
+ selected properties
+ current roles
+ relevant claims
+ relevant sources
```

### Product analysis

Fetch:
```text
product
+ analysis items
+ compact evidence summaries
```

Load detailed evidence on demand.

---

# 73. API-Oriented View Model

The database schema should not dictate frontend JSON directly.

FastAPI should expose stable view models such as:

```json
{
  "ingredient": {
    "display_name": "...",
    "normalized_name": "...",
    "match_status": "verified"
  },
  "chemistry": {
    "formula": "...",
    "molecular_weight": null,
    "structure_available": false
  },
  "role": {
    "name": "...",
    "confidence": "high"
  },
  "evidence": [...],
  "limitations": [...]
}
```

The API layer transforms relational records into product-friendly responses.

---

# 74. Data Access Layers

Recommended backend structure:

```text
FastAPI
  ↓
services/
  ├── scan_service
  ├── ingredient_service
  ├── chemistry_service
  ├── evidence_service
  ├── comparison_service
  └── explanation_service
        ↓
repositories/
  ├── product_repository
  ├── chemical_repository
  ├── claim_repository
  └── source_repository
        ↓
PostgreSQL
```

This prevents business logic from being scattered through route handlers.

---

# 75. Migration Ownership

OpenCode and Claude Code may modify schemas, but:

> **No agent may introduce a schema change without updating this document and creating a migration.**

A schema change should include:

```text
Reason
Affected tables
Migration
Backward compatibility
Tests
Rollback plan
```

Record the decision in `DECISIONS.md`.

---

# 76. Database Acceptance Criteria

The database design passes MVP review when:

1. Raw OCR remains separate from normalized ingredients.
2. Normalized ingredients remain separate from chemical entities.
3. Candidate matches cannot silently become verified.
4. Chemical entities support non-molecular entities.
5. Formula/structure/property fields may be NULL.
6. Product roles are contextual.
7. Claims and sources are separate.
8. Claim-level provenance is supported.
9. Confidence is field/claim-aware.
10. Computed data records its method.
11. Historical scans are auditable.
12. Product label versions can be separated.
13. User corrections are preserved.
14. Analysis runs are versioned.
15. AI explanations are derived outputs, not canonical facts.
16. Comparison results are reproducible.
17. Public/canonical data is separated from user-private data.
18. RLS/security boundaries can be implemented.
19. The design works on a free-first Supabase/Postgres setup.
20. The schema is implementable without introducing unnecessary infrastructure.

---

# 77. Implementation Priority

Build in this order:

```text
PHASE 1
domains
roles
sources
chemical_entities
ingredient_aliases

PHASE 2
products
product_labels
product_scans
ocr_runs
ingredient_observations

PHASE 3
ingredient_normalizations
ingredient_candidates
entity_matches

PHASE 4
entity_roles
claims
claim_sources
chemical_properties

PHASE 5
analysis_runs
analysis_items

PHASE 6
comparisons
comparison_items
user_corrections
verification_events
```

Then evaluate whether V2 tables are actually needed.

---

# 77b. Stage-10 Additions (additive, 2026-10-05)

Implemented in `003_verification_review.sql`; specified by the
verification/human-review architecture where the schema was silent:

```text
verification_decisions
----------------------
id UUID PK (deterministic, app-supplied)
entity_match_id UUID NULL FK → entity_matches.id
candidate_key TEXT NOT NULL
status TEXT NOT NULL (verified/provisional/conflicted/unverified/unknown/obsolete)
identity_confidence TEXT NOT NULL
rules_version TEXT NOT NULL
snapshot_version TEXT NOT NULL
evidence_context_hash TEXT NOT NULL
reason TEXT NULL
warnings JSONB NULL
gate_results JSONB NULL
created_at TIMESTAMPTZ
```

```text
reviews
-------
id TEXT PK (deterministic REV-####)
candidate_key TEXT NOT NULL
raw_text / normalized_text / identifier
resolution JSONB NOT NULL
verification_status TEXT NOT NULL
evidence_context JSONB NOT NULL
evidence_hash TEXT NOT NULL
priority INTEGER NOT NULL
status TEXT NOT NULL (queued/in_review/approved/rejected/needs_more_evidence/closed_unknown)
reviewer TEXT NULL
created_at / updated_at TIMESTAMPTZ
```

```text
review_events
-------------
id TEXT PK (deterministic REV-####:###)
review_id TEXT NOT NULL FK → reviews.id
event_type TEXT NOT NULL (ReviewCreated/ReviewClaimed/ReviewDecisionRecorded/ReverificationTriggered/VerificationResultRecorded)
actor TEXT NOT NULL
reason TEXT NOT NULL
previous_state TEXT NULL
new_state TEXT NOT NULL
evidence_context_hash TEXT NOT NULL
rules_version TEXT NOT NULL
snapshot_version TEXT NOT NULL
created_at TIMESTAMPTZ (no updated_at: immutable, trigger-enforced)
```

Documented extensions: `claims` gains nullable
`source_version/freshness_class/last_checked_at`;
`claim_sources` gains nullable
`provider/source_version/retrieved_at/response_hash`;
`sources.name` gains UNIQUE (idempotent seeding). Deferred FKs
(`claims.product_id/product_label_id/entity_role_id`,
`observations.scan_id/ocr_run_id`) stay plain UUIDs until their
target tables land.

---

# 78. Final Database Principle

> **The LabelLens database must preserve what was observed, what was normalized, what was matched, what was verified, what was computed, what was inferred, who/what supports it, and what remains unknown—without collapsing those states into one convenient but untrustworthy record.**

---

# 77c. Stage-12 Additions: Canonical Entity Registration (2026-10-05)

**No migration and no new table.** Stage 12 changed how
`chemical_entities` and `ingredient_aliases` get populated, not what
they hold. The columns the import needs already existed in
`001_initial_schema.sql`; they are simply now written by a
service-role path instead of by hand.

## 77c.1 Provenance storage

`chemical_entities.metadata JSONB` is the provenance document for a
registered canonical entity. There is deliberately no separate
provenance table: the data is per-entity, semi-structured, and read
with the entity.

```json
{
  "snapshot_version": "canonical_v1",
  "rules_version": "1.0.0",
  "verification_status": "verified",
  "verified_at": "2026-10-05",
  "imported_by": "canonical-registration-import",
  "provenance": {
    "source_id": "PUBCHEM",
    "record_locator": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/...",
    "retrieved_at": "2026-10-05",
    "source_class": "A",
    "license_note": "…",
    "source_version": "…"
  },
  "identifiers": [
    {"id_type": "pubchem_cid", "value": "311", "provenance_note": "…"},
    {"id_type": "inchikey", "value": "KRKNYBCHXYNGOX-UHFFFAOYSA-N"}
  ]
}
```

- `first_verified_at` / `last_verified_at TIMESTAMPTZ` record when the
  entity was approved. Both are set on import.
- Values are transcribed verbatim from the approved artifact. No
  descriptor, weight, or structure is computed here; a field absent
  from the source stays `NULL`.
- `snapshot_version` plus `rules_version` answer "which approved
  artifact, under which frozen rules, was this entity allowed in?" —
  the same pair `verification_decisions` carries.

## 77c.2 Registration invariants

- **Approved records only.** `status = 'verified'`; `entity_type` and
  `representation_type` come from the approved vocabulary (a salt
  stays `salt`, a mixture stays a mixture; `chemical_class` is not
  derived).
- **Stable identity.** A UUID id is kept verbatim; any other stable id
  maps to `uuid5("canonical-entity:<id>")`. Alias ids are `uuid5`
  derived. Re-running an import cannot create a second identity.
- **Idempotent writes.** Inserts use `ON CONFLICT DO NOTHING` (entity
  by `id`, alias by `(chemical_entity_id, alias)`), so a repeat run
  reports records as already present and writes nothing new.
- **All-or-nothing.** Entity and alias writes share one transaction.
  Validation of the whole artifact completes before any write; a
  rejected write propagates, so a failed run leaves no partial state.
- **Aliases carry no source.** `ingredient_aliases.source_id` stays
  `NULL` and `verified = true`: an alias imported from an approved
  record is not an independently sourced fact.
- **No product, scan, or role data** is written or read by the
  import. `products`, `product_scans`, and the deferred FK targets stay
  as they are.

## 77c.3 The import path is not a route

`app/cli/import_canonical_entities.py` is the only writer. It requires
direct service-role database credentials and an explicit
`ENTITY_IMPORT_CONFIRM=service-role` interlock; there is no HTTP route,
admin endpoint, or request body that can create an entity. The API
continues to reject a decision naming an unregistered entity with 422
`ENTITY_NOT_FOUND` before any write, so `claims.chemical_entity_id`
remains referentially valid by construction.

## 77c.4 Registry projection

The resolver's registry is a read-only projection of these rows,
built at application startup:

```text
chemical_entities + ingredient_aliases  ->  InMemoryRegistry
```

- `RegistryEntry.ref` is registry-local (`CANON-<12 hex>`), never the
  entity UUID — `entity_matches.chemical_entity_id` therefore stays
  `NULL` for a resolver match (Stage-5 invariant: a match is not an
  entity identity).
- Identifiers come from `metadata.identifiers`; `entity_class` comes
  from `representation_type`.
- A failed load leaves the registry empty (all candidates unresolved)
  rather than partially populated.
- Re-running the import reaches the resolver only after an application
  restart; there is no reload endpoint.

## 77c.5 Row-level security — still open

`chemical_entities` and `ingredient_aliases` are **not** covered by
the Stage-10 RLS rollout: they are canonical reference data, readable
only with service-role credentials from this service. Enabling RLS on
them is a Stage-13 candidate and is recorded here as a known gap, not
an oversight.

---

# 77d. Stage-18 Ownership Classification (2026-10-05)

Migration 006 adds nullable `owner_subject` (authenticated
subject, never a token) to the user-derived analysis tables.
Service writes always set it from the data owner; legacy NULL
rows keep prior readability and match no subject.

| Class | Tables | Rule |
|---|---|---|
| User-owned | `ocr_runs`, `ocr_corrections` (NOT NULL), `ingredient_observations`, `ingredient_normalizations`, `ingredient_candidates`, `entity_matches`, `verification_decisions`, `reviews` | owner-or-NULL SELECT for `authenticated`; writes service-role only |
| Shared canonical | `chemical_entities`, `ingredient_aliases`, `sources`, `domains`, `roles` | unchanged design; never owner-scoped |
| Shared by content | `claims`, `claim_sources`, `verification_events` | unchanged; claim identity is deterministic shared chemistry, never forked per user |
| Global audit | `review_events` | unchanged; reachable via owned-or-reviewer review reads; no raw label text inside |

Reviewer reads bypass the owner filter through the API only
(allowlisted role); direct database access stays owner-scoped.
Full matrix: `STAGE_18_DATA_ISOLATION_AND_PROVIDER_VALIDATION.md`.
