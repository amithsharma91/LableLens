# LabelLens — Chemistry Data Specification

**Document:** CHEMISTRY_DATA_SPEC.md  
**Project:** LabelLens  
**Version:** 1.0  
**Purpose:** Define the scientific data model and validation rules for chemical/ingredient knowledge inside LabelLens.

---

## 1. Purpose

This document defines exactly what LabelLens may store, calculate, display, infer, or leave unknown about an ingredient or chemical entity.

The central rule is:

> **A label name is not automatically a chemical identity. A chemical identity is not automatically a verified fact. A verified fact is not automatically applicable to every product context.**

LabelLens must preserve those distinctions.

The chemistry layer must support:
- Food ingredients and additives
- Snacks and beverages
- Cosmetics and personal care ingredients
- Household ingredients
- Supplements
- Informational pharmaceutical labeling
- Other labeled consumer-product components

The same chemistry engine should support all domains while domain-specific role information remains separate.

---

# 2. Scientific Data Pipeline

Every ingredient entering the system follows this conceptual pipeline:

```text
Label text
   ↓
Raw ingredient string
   ↓
Normalization
   ↓
Candidate entity generation
   ↓
Entity resolution
   ↓
Chemical-entity validation
   ↓
Verified chemical record
   ↓
Domain-specific role
   ↓
Computational chemistry
   ↓
Evidence + confidence
   ↓
User explanation
```

No stage may silently overwrite the previous stage.

---

# 3. Core Entity Types

LabelLens must distinguish at least these entity types:

### 3.1 `chemical_entity`
A chemically defined entity for which an appropriate identity can be established.

Examples may include:
- Defined organic compounds
- Defined inorganic compounds
- Salts
- Explicitly defined stereochemical entities

### 3.2 `polymer`
A polymeric/material entity where treating the whole material as one small molecule would be misleading.

### 3.3 `mixture`
A composition containing multiple substances where a single molecular identity is inappropriate.

### 3.4 `natural_complex`
A natural-origin material whose relevant identity is not adequately represented by one defined molecule.

### 3.5 `formulation`
A named product/formulation/component grouping whose exact composition is not represented by a single chemical entity.

### 3.6 `material`
A material or substance category where composition/structure may be more useful than a single molecular graph.

### 3.7 `trade_name`
A commercial or proprietary name. It is not itself evidence of a unique chemical structure.

### 3.8 `unknown`
Insufficient evidence to establish the identity confidently.

---

# 4. Required Separation of Records

LabelLens must store these separately:

```text
Raw OCR
      ≠
Extracted ingredient text
      ≠
Normalized ingredient
      ≠
Candidate entity
      ≠
Matched chemical entity
      ≠
Verified chemical facts
      ≠
Product-domain role
      ≠
AI explanation
```

This is one of the most important anti-hallucination controls in the entire application.

Example:

```text
OCR text:
"Sodiurn Benzoate"

Normalized:
"Sodium Benzoate"

Matched entity:
"Sodium benzoate"

Verified facts:
Only fields supported by authoritative evidence

AI explanation:
Generated from verified fields
```

If the match is not sufficiently supported, do not create a verified chemical record.

---

# 5. Canonical Chemical Entity Model

A canonical chemical record should support these fields.

```yaml
entity_id:
preferred_name:
entity_type:
status:

names:
  - common_name
  - systematic_name
  - synonym
  - label_name

identifiers:
  cas:
  pubchem_cid:
  chebi_id:
  inchi:
  inchikey:

structure:
  smiles:
  canonical_smiles:
  isomeric_smiles:
  molfile:
  representation_status:

formula:
molecular_weight:

classification:
  chemical_class:
  superclass:
  functional_groups:

computed:
  descriptors:
  heavy_atom_count:
  hydrogen_bond_donors:
  hydrogen_bond_acceptors:
  rotatable_bonds:
  topological_polar_surface_area:
  exact_molecular_weight:
  other_supported_descriptors:

domain_roles:
  food:
  beverage:
  cosmetic:
  personal_care:
  household:
  supplement:
  pharma:

evidence:
  sources:
  field_claims:

confidence:
  identity:
  structure:
  formula:
  molecular_weight:
  classification:
  role:

representation_type:
limitations:
last_verified:
```

Not every field is mandatory for every entity.

**Missing is preferable to fabricated.**

---

# 6. Identity Rules

## 6.1 Preferred identity

The preferred identity should be the best-supported normalized entity name for the label context.

The system should retain:
- Original label spelling
- OCR string
- Normalized string
- Preferred entity name
- Aliases

Do not discard the original string.

---

## 6.2 Names and aliases

Aliases must be classified where possible:

```text
label_name
common_name
systematic_name
synonym
abbreviation
additive_number
trade_name
historical_name
regional_variant
translation
```

A name match alone is not sufficient to establish chemical identity when the term is ambiguous.

---

# 7. Identifier Rules

Potential identifiers include:

- CAS Registry Number
- PubChem CID
- ChEBI ID
- InChI
- InChIKey
- Other authoritative database identifiers where appropriate

### Important rule

> **An identifier is evidence for identity, not permission to invent missing fields.**

Never infer a CAS, structure, formula, or regulatory status merely because an ingredient has a similar name.

### Identifier validation

When an identifier is stored:
- Preserve exact source value.
- Record source.
- Validate syntax where possible.
- Confirm that it corresponds to the same intended entity.
- Handle salts, hydrates, stereoisomers, and mixtures carefully.

---

# 8. Structure and SMILES Rules

## 8.1 Structure is optional

A structure must exist only where a chemically meaningful molecular representation is supported.

Valid structure states:

```text
verified
computed_from_verified_representation
candidate
not_applicable
unavailable
ambiguous
invalid
```

Only `verified` or appropriately validated computed structures should appear as factual chemistry.

---

## 8.2 Never force SMILES

Do NOT generate a SMILES merely because a UI card has a SMILES field.

Avoid forced single-molecule SMILES for:
- Mixtures
- Proprietary formulations
- Broad natural products
- Undefined botanical complexes
- Ambiguous trade names
- Multi-component preparations
- Unknown ingredients
- Materials for which a single molecular graph is misleading

The UI should instead say:

> **A single molecular structure is not appropriate/verified for this ingredient.**

---

## 8.3 RDKit validation

Where RDKit is used:

```text
SMILES
 ↓
RDKit parser
 ↓
valid?
 ├─ NO → invalid / unresolved
 └─ YES
      ↓
normalized representation
      ↓
descriptor calculation
```

Never save a structure as verified simply because RDKit accepts a string.

RDKit confirms that a molecular representation is syntactically/chemically parseable under its model; it does not prove that the label ingredient actually corresponds to that molecule.

---

# 9. Salts, Hydrates and Related Forms

Chemically related forms must not be silently collapsed.

Examples of potentially distinct records:
- Parent compound
- Salt
- Hydrate/solvate
- Stereochemical form
- Isomer
- Different protonation/charge state where materially relevant

Store the actual matched form when evidence supports it.

The UI may provide a “related chemical” relationship, but must not replace the actual record with a different entity without explanation.

---

# 10. Formula Rules

A molecular formula should be stored only when it applies to the represented entity.

Distinguish:
- Formula
- Empirical formula
- Formula for a salt/defined compound
- Composition information for a mixture
- Repeat-unit notation for polymers where appropriate

Do not invent a formula for an undefined mixture.

---

# 11. Molecular Weight Rules

Keep the concepts separate:

```text
molecular weight
exact molecular mass
average molecular mass
molar mass
```

Do not silently interchange them in a scientific display.

For a defined entity, store the value with:
- numerical value
- unit
- source or calculation method
- precision policy

For mixtures/polymers where a single molecular weight is not meaningful, use an appropriate alternative or leave it unavailable.

If a value is computationally derived, mark the derivation and input representation.

---

# 12. Computational Descriptor Rules

RDKit may calculate descriptors where scientifically appropriate.

Potential descriptors include:
- molecular weight/mass-related descriptors
- heavy atom count
- H-bond donors
- H-bond acceptors
- rotatable bonds
- topological polar surface area
- ring-related counts
- selected physicochemical descriptors supported by the implementation

Every computed descriptor should store:

```yaml
descriptor_name:
value:
unit:
software:
software_version:
input_representation:
calculation_date:
```

### Critical distinction

A computed descriptor is **derived information**.

It is not automatically a literature-reported property and must not be presented as though it were a measured experimental value.

---

# 13. Experimental vs Computed vs Reported Data

Every chemical fact should have a provenance class:

```text
experimental
literature_reported
database_reported
computed
inferred
AI_candidate
unknown
```

### Display rule

`AI_candidate` or unverified inference must never be shown in the main factual panel as verified chemistry.

Computed and reported values should remain distinguishable.

---

# 14. Functional Groups

Functional-group information may be generated computationally when the underlying structure is valid.

Rules:
- Structure must be valid.
- Detection method must be deterministic/documented.
- Store the detection rule/version where possible.
- Avoid claiming functional groups for a mixture as though they belong to one molecule.

Example:

```yaml
functional_group:
  name: carboxylic_acid
  detection_method: RDKit_substructure
  status: computed
```

---

# 15. Chemical Class

Chemical class is a classification layer, not absolute truth.

Possible examples:
- Organic acid
- Alcohol
- Ester
- Amine
- Carbohydrate
- Lipid
- Polymer
- Inorganic salt
- Surfactant
- Chelating agent class
- Antioxidant class

The exact taxonomy will be finalized in the role/classification specification.

A molecule may belong to multiple useful classification levels.

---

# 16. Product-Domain Role

**Chemical identity and product role must be stored separately.**

Example:

```text
Chemical identity:
Citric acid

Food role:
Acidity regulator / acidulant context

Cosmetic role:
pH-adjusting/formulation context where supported
```

The role is not a permanent property of the molecule. It is a **product-formulation context**.

Store:

```yaml
role:
domain:
role_taxonomy_version:
evidence:
confidence:
```

Never infer a product role solely from a chemical name without contextual support.

---

# 17. “Why Is This Here?” Data Contract

The explanation engine must receive structured input such as:

```yaml
ingredient:
verified_identity:
chemical_class:
verified_properties:
domain:
role:
source_claims:
confidence:
limitations:
```

It must NOT receive permission to invent missing facts.

Expected explanation structure:

```text
What is it?
Why may it be included?
What relevant chemistry explains the role?
What evidence supports this?
What remains uncertain?
```

---

# 18. Mixtures and Complex Ingredients

Mixtures require special handling.

A mixture may have:
- Composition information
- Component list
- Concentration/range information
- Source-specific description
- No single molecular structure

Store the mixture as a mixture entity.

If known components are available, link them:

```text
mixture
 ├── component A
 ├── component B
 └── component C
```

Do not automatically substitute the most prominent component as the identity of the whole ingredient.

---

# 19. Botanical and Natural Ingredients

Natural-origin ingredients can be chemically complex.

Rules:
- Preserve the label-level identity.
- Do not assume a single “active molecule.”
- Distinguish source material from isolated constituent chemicals.
- Link known constituents only when supported.
- Avoid assigning one structure to a complex natural material.

The database should support:

```text
natural_complex
  ↓
known constituents
  ↓
evidence relationships
```

without collapsing the records.

---

# 20. Proprietary / Trade-Name Ingredients

A commercial/trade name must be treated as a label/formulation identity unless authoritative evidence establishes its chemical composition.

For example:

```text
Trade name
   ↓
manufacturer documentation
   ↓
composition evidence
```

No composition evidence:

> Identity recognized as a trade/formulation term; molecular structure not verified.

---

# 21. Pharmaceutical Labeling

Pharma support is informational.

Separate:
- Active ingredient
- Excipient
- Salt/form
- Coating/component
- Other labeled components

For medicines, LabelLens may explain **what an ingredient is and its labeled/formulation role**, but it must not:
- diagnose
- prescribe
- recommend dosage changes
- tell a user to start/stop treatment
- recommend substituting a medicine
- infer individualized treatment

---

# 22. Evidence Model

Every important field should be capable of being tied to evidence.

Example:

```yaml
claim_id:
entity_id:
field:
value:
source_id:
source_type:
source_url:
retrieved_at:
verification_status:
confidence:
notes:
```

This allows different claims about the same entity to have different confidence.

Example:

```text
Name        → high confidence
Formula     → high confidence
SMILES      → high confidence
Product role → medium confidence
Specific product application → unknown
```

Never let one strong field artificially upgrade unrelated fields.

---

# 23. Confidence Model

Confidence must be granular.

Minimum categories:

```text
identity_confidence
structure_confidence
formula_confidence
property_confidence
classification_confidence
role_confidence
evidence_confidence
```

Recommended status values:

```text
verified
high
medium
low
candidate
unverified
unknown
conflicted
```

The numerical scoring system, if later introduced, must be documented and calibrated against reviewed examples. Avoid fake precision such as `97.843% confidence` without validation.

---

# 24. Conflict Handling

When sources disagree:

```text
Source A
    ↕
conflict
    ↕
Source B
```

Do not silently choose a value.

Instead:
1. Prefer the appropriate authoritative source based on claim type.
2. Record the disagreement.
3. Preserve source provenance.
4. Escalate for manual review when necessary.
5. Show uncertainty when unresolved.

A conflict is data, not a reason to fabricate a resolution.

---

# 25. Entity Resolution Rules

Entity resolution should use multiple signals.

Potential signals:
- normalized name
- exact identifier
- recognized additive number
- alias
- domain/context
- source database match
- structure/identifier agreement

Recommended outcome states:

```text
exact_match
strong_match
probable_match
ambiguous
no_match
invalid_input
```

Never convert `ambiguous` into a verified match without sufficient evidence.

---

# 26. Additive Codes / INS / E-Numbers / Similar Label Codes

Where applicable, maintain mappings between:
- Label code
- Preferred entity name
- Alias
- Domain
- Regulatory/source context

Do not assume that a code's mere presence proves its current regulatory status in every country.

Country/region-specific regulatory claims belong in the evidence/regulatory layer.

---

# 27. Data Versioning

Chemical data can change because:
- source databases update
- labels change
- names are normalized differently
- software calculations change
- descriptor implementations change

Store:
- data version
- schema version
- source retrieval date
- calculation software/version
- record updated date
- change reason where practical

Previously verified records should remain auditable.

---

# 28. Cached Data Strategy

For cost control, verified chemical records should be cached locally in the application's database when licensing/terms permit.

Preferred flow:

```text
User query
   ↓
Local verified cache
   ↓
found?
 ├── YES → serve
 └── NO
       ↓
authoritative lookup
       ↓
validate
       ↓
store with provenance
```

Do not cache data blindly if the source terms do not permit it.

---

# 29. Free-First Data Strategy

Initial development should prioritize free or openly accessible scientific sources whose licenses/terms permit the intended use.

The system should isolate external-source adapters:

```text
ChemicalSourceAdapter
 ├── Source A
 ├── Source B
 ├── Source C
 └── local golden dataset
```

This keeps the application provider-independent and makes later source replacement easier.

The final source hierarchy is defined in `SOURCE_REGISTRY.md`.

---

# 30. Golden Chemistry Dataset

Before large-scale automation, create a manually reviewed golden dataset.

Initial target:
**100 important ingredients/entities**

For each:
- canonical identity
- aliases
- identifiers
- structure when valid
- formula
- molecular weight
- domain roles
- evidence
- representation type
- confidence

Use this dataset for:
- entity-resolution tests
- chemistry tests
- UI regression
- explanation grounding tests
- demonstrations

---

# 31. Chemistry Test Cases

The test suite must include:

### Valid structures
- simple organic molecules
- salts
- stereochemical examples
- multiple functional groups

### Invalid/ambiguous inputs
- OCR typos
- partial names
- abbreviations
- unknown trade names
- incorrect SMILES

### Non-single-molecule entities
- mixtures
- natural complexes
- polymers
- formulations

### Identifier collisions
- similar names
- parent vs salt
- isomers
- hydrate vs non-hydrate

Expected behavior must be explicit.

---

# 32. Data Quality Gates

A record may move from candidate to verified only if required checks pass.

Example:

```text
Candidate
  ↓
Name normalization
  ↓
Identifier/source validation
  ↓
Entity confirmation
  ↓
Structure validation (if applicable)
  ↓
Field-level evidence
  ↓
Confidence assigned
  ↓
Verified
```

Any failed gate should block verification or downgrade the relevant field.

---

# 33. Forbidden Behaviors

LabelLens chemistry services must never:

- Invent a CAS number.
- Invent a formula.
- Invent a SMILES string.
- Create a molecular structure for an ambiguous ingredient.
- Treat a trade name as a unique molecule without evidence.
- Treat a mixture as one molecule.
- Present a computed descriptor as an experimental measurement.
- Convert low-confidence OCR into fact silently.
- Treat a chemical role as an intrinsic property of the molecule.
- Convert correlation or association into causation.
- Generate medical advice from ingredient information.
- Use AI-generated text as the sole evidence for a scientific claim.

---

# 34. AI Grounding Contract

Every explanation request should be constrained to verified structured input.

Conceptually:

```json
{
  "entity": {...},
  "verified_fields": {...},
  "domain": "...",
  "role": "...",
  "sources": [...],
  "confidence": {...},
  "limitations": [...]
}
```

Prompt rule:

> Use only supplied verified facts and source-supported claims. If information is missing or uncertain, explicitly say so. Do not infer a structure, regulatory status, safety conclusion, medical recommendation, or product-specific claim.

The generated response should be traceable back to the supplied data.

---

# 35. UI Display Rules

### High-confidence verified
Display normally.

### Medium-confidence
Display with visible uncertainty.

### Low-confidence / candidate
Do not present as confirmed.

### Unknown
Clearly display:

> **Unknown / not verified**

### Not applicable
Display:

> **Not applicable to this type of ingredient**

### Conflicted
Display:

> **Sources disagree / review required**

The UI must never hide uncertainty just to make the interface look cleaner.

---

# 36. Definition of a Chemically Trustworthy Record

A record is “chemically trustworthy” only when:

- Identity is sufficiently supported.
- Appropriate identifiers are validated.
- Structure, if present, is appropriate to the entity type.
- Formula/molecular data are tied to that entity.
- Computed values are labeled as computed.
- Product roles are contextual and evidence-backed.
- Sources are preserved.
- Confidence is explicit.
- Missing information remains missing.

---

# 37. Example Record

Conceptual example only:

```yaml
entity_id: CHEM-EXAMPLE-001
preferred_name: Example Defined Compound
entity_type: chemical_entity

names:
  label_name:
    - Example Name

identifiers:
  cas: VERIFIED_VALUE_OR_NULL
  pubchem_cid: VERIFIED_VALUE_OR_NULL

structure:
  smiles: VERIFIED_VALUE_OR_NULL
  representation_status: verified | unavailable | not_applicable

formula: VERIFIED_VALUE_OR_NULL
molecular_weight:
  value: VERIFIED_VALUE_OR_NULL
  unit: g/mol
  provenance: source | computed

classification:
  chemical_class:
    - VERIFIED_CLASS
  functional_groups:
    - COMPUTED_OR_VERIFIED_GROUP

domain_roles:
  food:
    role: VERIFIED_ROLE_OR_NULL
    confidence: high | medium | low | unknown

confidence:
  identity: high
  structure: high
  formula: high
  molecular_weight: high
  role: medium

limitations:
  - Example limitation

sources:
  - source_id: SOURCE-001
```

**Note:** This is a schema example, not a factual chemical record.

---

# 38. Relationship Model

Use explicit relationships where needed:

```text
Ingredient
   ↓ matches
ChemicalEntity

ChemicalEntity
   ↓ has_alias
Alias

ChemicalEntity
   ↓ has_identifier
Identifier

ChemicalEntity
   ↓ has_structure
Structure

ChemicalEntity
   ↓ has_computed_descriptor
Descriptor

ChemicalEntity
   ↓ has_role_in
DomainRole

Fact
   ↓ supported_by
Source

Claim
   ↓ derived_from
VerifiedFact
```

Do not flatten all of this into a single “ingredient description” blob.

---

# 39. Version 1 Chemistry Scope

For the MVP, implement only what can be made reliable:

### Must have
- Name normalization
- Alias handling
- Entity matching
- Verified identifiers where available
- Formula
- Molecular weight
- SMILES validation where appropriate
- Structure display where appropriate
- Basic RDKit descriptors
- Functional-group/descriptive calculations where appropriate
- Domain role
- Evidence
- Confidence
- Unknown/ambiguous handling

### Later
- Advanced similarity
- Substructure search
- ML property prediction
- Ingredient clustering
- More sophisticated molecular modeling

Do not add advanced computational chemistry until the basic identity/evidence pipeline is trustworthy.

---

# 40. Acceptance Criteria

The chemistry layer passes MVP acceptance when:

1. A known simple chemical can be matched to a verified record.
2. OCR typos can remain candidates until resolved.
3. Valid SMILES are parsed and invalid SMILES are rejected.
4. A mixture is not forced into a molecular structure.
5. A trade name can remain unresolved.
6. Formula and molecular weight are not fabricated.
7. Product roles remain separate from chemical identity.
8. Computed descriptors are marked as computed.
9. Important fields carry provenance.
10. Conflicting evidence is not silently hidden.
11. Unknown ingredients remain visibly unknown.
12. AI explanations are generated only from structured evidence.
13. Test cases cover normal, ambiguous, invalid, and non-molecular entities.
14. Data can be re-verified or updated without destroying historical provenance.

---

# 41. Final Chemistry Principle

> **LabelLens is not trying to know everything. It is trying to know what it knows, prove why it knows it, calculate only what can be calculated correctly, and clearly show what it does not know.**

That principle overrides convenience, visual polish, AI fluency, and demo pressure.
