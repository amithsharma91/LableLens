# LabelLens — Evidence and Confidence Specification

**Document:** EVIDENCE_AND_CONFIDENCE_SPEC.md  
**Project:** LabelLens  
**Version:** 1.0  
**Purpose:** Define how LabelLens verifies, ranks, stores, exposes, and updates evidence and confidence for OCR, ingredient identity, chemistry, product roles, explanations, and comparisons.

---

## 1. Objective

LabelLens must be trustworthy without pretending to be omniscient.

The central rule is:

> **Every important claim must have an identifiable evidence path, a meaningful confidence state, and a clear distinction between observed, verified, computed, inferred, and unknown information.**

Evidence and confidence are not cosmetic UI features. They are part of the application architecture.

---

# 2. Trust Architecture

The system should use this pipeline:

```text
Observation
   ↓
Extraction
   ↓
Normalization
   ↓
Candidate
   ↓
Verification
   ↓
Claim
   ↓
Evidence
   ↓
Confidence
   ↓
Explanation
```

Example:

```text
Image says:
"Sodiurn benzoate"
        ↓
OCR observation
        ↓
normalized candidate:
"Sodium benzoate"
        ↓
chemical database match
        ↓
verified entity
        ↓
formula claim
        ↓
authoritative source
        ↓
high confidence
        ↓
user explanation
```

A fluent AI response is never allowed to skip this chain.

---

# 3. Claim-Level Evidence

LabelLens must treat each important factual statement as a separate claim.

Examples:

```text
Claim A:
The ingredient is sodium benzoate.

Claim B:
Its molecular formula is X.

Claim C:
Its molecular structure is represented by Y.

Claim D:
In this product domain, it serves a preservative role.

Claim E:
This particular product label contains it.
```

These claims may have different evidence and confidence.

Example:

```text
Identity        → verified
Formula         → verified
Structure       → verified
Product role    → supported
Product-specific interpretation → uncertain
```

Do not allow one strong claim to automatically upgrade unrelated claims.

---

# 4. Evidence Object

A source should be stored separately from the claim it supports.

Recommended conceptual model:

```yaml
source_id:
source_name:
source_type:
publisher:
url:
identifier:
retrieved_at:
publication_date:
last_checked:
version:
license_notes:
jurisdiction:
language:
access_status:
```

A claim-source relationship should contain:

```yaml
claim_id:
source_id:
field:
source_value:
support_type:
support_strength:
review_status:
reviewer:
reviewed_at:
notes:
```

This prevents the database from becoming one large untraceable text blob.

---

# 5. Source Hierarchy

Source priority depends on the claim type.

### Tier 1 — Highest preference

- Government agencies
- Regulatory authorities
- Official scientific databases
- Standards organizations
- Primary peer-reviewed research when appropriate
- Official product/manufacturer labeling for label-specific facts

### Tier 2

- Reputable institutional resources
- High-quality scientific reviews
- Established reference databases

### Tier 3

- Secondary educational resources
- Reputable technical summaries

### Tier 4 — Discovery only unless independently verified

- Blogs
- Forums
- Social posts
- AI-generated pages
- Unverified databases
- Search-result snippets

A low-tier source can help find a candidate, but it should not automatically become final evidence.

---

# 6. Claim-Type to Source-Type Mapping

Different claims require different evidence.

| Claim type | Preferred evidence |
|---|---|
| Product contains ingredient | Actual product label / manufacturer documentation |
| Chemical identity | Authoritative chemical database / authoritative reference |
| Formula | Authoritative chemical database / primary reference |
| Molecular structure | Authoritative chemical database / validated source |
| Molecular descriptor | Deterministic computation from verified structure |
| Experimental property | Primary literature / authoritative database |
| Chemical mechanism | Peer-reviewed literature / authoritative reference |
| Product-domain role | Applicable regulatory/technical source + formulation context |
| Current regulation | Current regulator / official government source |
| Current product formulation | Current product label/manufacturer |
| Medical labeling information | Official regulatory/label source |
| AI explanation | Derived from verified supporting claims; AI itself is not evidence |

---

# 7. Evidence Status

Every important claim should have a status.

Recommended statuses:

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

### Definitions

**verified**  
Evidence is sufficiently strong and appropriate for the claim.

**supported**  
Reliable evidence exists, but the claim is contextual or not directly equivalent to a strict verified identity.

**computed**  
The system derived the value deterministically from verified input.

**provisional**  
Evidence is promising but requires additional verification.

**candidate**  
A possible match or interpretation; not confirmed.

**unverified**  
Information exists but has not met the project's verification gate.

**conflicted**  
Relevant sources disagree.

**unknown**  
Insufficient evidence exists to make the claim.

**obsolete**  
The claim was previously valid/supported but should no longer be treated as current.

---

# 8. Evidence Does Not Mean Truth

A source existing does not make a claim true.

Verification requires:

```text
Claim
 +
Correct entity
 +
Correct context
 +
Appropriate source
 +
Current enough evidence
 +
Successful validation
```

Example:

A website may state:

> “Ingredient X is a preservative.”

That is not automatically enough.

The system must determine:
- Which exact entity?
- Which product domain?
- Does the source support that role?
- Is the source applicable to the required jurisdiction/context?
- Is the information current enough?

---

# 9. Verification Gates

A record should pass through gates.

```text
INPUT
  ↓
Source found?
  ├─ NO → unknown/candidate
  └─ YES
       ↓
Identity resolved?
  ├─ NO → ambiguous/candidate
  └─ YES
       ↓
Source appropriate for claim?
  ├─ NO → provisional/unverified
  └─ YES
       ↓
Value validated?
  ├─ NO → unverified/conflicted
  └─ YES
       ↓
Context applicable?
  ├─ NO → unsupported
  └─ YES
       ↓
VERIFIED / SUPPORTED / COMPUTED
```

No shortcut should turn an unverified candidate into a verified fact.

---

# 10. Confidence Is Multi-Dimensional

Do not create one generic confidence value.

At minimum, track:

```yaml
ocr_confidence
extraction_confidence
normalization_confidence
identity_confidence
structure_confidence
formula_confidence
property_confidence
role_confidence
evidence_confidence
explanation_support_confidence
```

These represent different questions.

Example:

```text
OCR confidence:       low
Identity confidence:  high
Formula confidence:   high
Role confidence:      medium
```

This can happen when the image is poor but the corrected user input creates an exact known match.

---

# 11. Confidence Model

For MVP, use interpretable qualitative states rather than pretending to have scientifically calibrated probabilities.

Recommended:

```text
HIGH
MEDIUM
LOW
UNKNOWN
CONFLICTED
```

Optional numeric internal scores may be used for ranking candidates, but:

- They must not be displayed as calibrated probabilities unless validated.
- Their formula must be documented.
- They must not imply scientific certainty.
- They must not replace human/source verification.

Avoid displaying:

> 98.74% chemical correctness

unless the project has actually measured and calibrated that metric.

---

# 12. Confidence Inputs

Possible signals for identity resolution:

```text
exact identifier match
exact normalized name match
trusted alias match
additive-code match
domain/context agreement
source agreement
structure agreement
salt/form agreement
OCR quality
manual user correction
```

Possible confidence degradation signals:

```text
OCR corruption
ambiguous naming
multiple possible entities
trade name
mixture
incomplete label
conflicting sources
outdated source
missing source
regional ambiguity
```

The exact weighting must be validated using the regression dataset.

---

# 13. Manual User Correction

Manual correction is a high-value signal but not automatic proof.

Example:

```text
OCR:
"Sodiurn Benzoate"

User correction:
"Sodium Benzoate"
```

This improves the extracted input.

It does not alone establish:
- chemical formula
- structure
- regulatory status
- safety
- product role

Those still require verification.

Store:

```yaml
source_of_text: ocr | user_entered | user_corrected | manual
edited_by_user: true/false
edited_at:
original_value:
final_value:
```

---

# 14. OCR Confidence

OCR confidence concerns what the image appears to contain.

It is not chemical confidence.

Recommended states:

```text
clear
readable
uncertain
poor
unusable
```

The OCR result must preserve:
- raw recognized text
- bounding regions when available
- OCR engine/model
- OCR timestamp
- OCR confidence if supplied
- preprocessing method if used

OCR uncertainty should be visible before analysis.

---

# 15. Ingredient Extraction Confidence

The system must distinguish:

### OCR text
What the model saw.

### Ingredient extraction
What the system believes is an ingredient.

Example:

```text
Raw text:
"Ingredients: water, sugar, citric acid, flavour..."

Extracted:
[
  "water",
  "sugar",
  "citric acid",
  "flavour"
]
```

Extraction can be wrong even if OCR is correct.

Therefore the two confidence values remain separate.

---

# 16. Entity-Matching Confidence

Candidate matching should return:

```yaml
candidate_entity_id:
match_status:
match_reasons:
identity_confidence:
evidence:
alternatives:
```

Suggested match statuses:

```text
exact_match
strong_match
probable_match
ambiguous
no_match
invalid_input
```

### Exact match

Use only when evidence strongly supports identity.

### Strong/probable

Useful for candidate suggestions but should be visibly qualified until verification requirements are met.

### Ambiguous

Show multiple candidates or request user clarification when appropriate.

### No match

Keep unknown.

---

# 17. Evidence Freshness

Not every claim has the same freshness requirement.

### Highly dynamic
- Regulations
- Product formulation
- Product availability
- Current manufacturer information
- API documentation
- Pricing
- Platform limits

These require current verification.

### Moderately dynamic
- Scientific database metadata
- Institutional reference pages
- Some classification information

Re-check periodically.

### Relatively stable
- Fundamental molecular identity
- Basic molecular formula
- Stable identifiers

These still need provenance but may not require the same re-check frequency.

Store:

```text
first_verified
last_verified
last_checked
source_version
freshness_class
```

Do not interpret “old” as automatically false; interpret it according to claim type.

---

# 18. Regulatory Evidence

Regulatory claims are jurisdiction- and time-sensitive.

LabelLens must store, where relevant:

```yaml
jurisdiction:
regulator:
regulatory_category:
status:
effective_date:
source:
last_verified:
```

Never display:

> “Approved everywhere”

from a single regulatory source.

Do not generalize one country's regulatory status to another country without evidence.

---

# 19. Product-Specific Evidence

An ingredient may be chemically verified but not proven to occur in a specific product.

There are separate claims:

```text
Entity X exists
        ≠
Product Y contains Entity X
```

Product-specific presence should be supported by:
- current label image
- official product label
- manufacturer documentation
- another appropriate source

The actual scanned image is evidence for the label observation, not automatically evidence for every chemical property attributed to the ingredient.

---

# 20. AI-Generated Content

AI-generated text is an interpretation layer.

Every explanation should have a grounding relationship:

```text
Explanation
   ↓ derived_from
Verified claims
   ↓ supported_by
Evidence
```

AI must not create unsupported claims.

### Explanation prompt contract

The model should receive:
- verified facts
- product domain
- role
- evidence summaries
- confidence states
- limitations

The prompt should explicitly require:

> Use only supplied verified/supportable information. If a required fact is missing, say that it is unknown or not established. Do not invent identifiers, structures, properties, regulatory status, or medical conclusions.

---

# 21. Explanation Confidence

Explanation confidence means:

> “How well is the generated explanation supported by the available structured evidence?”

It does NOT mean:

> “How confident is the AI model?”

The explanation layer should be considered well grounded only when:
- required source claims exist
- requested fields are verified/supportable
- no unsupported leap is required
- limitations are preserved

If evidence is weak, produce a narrower explanation.

---

# 22. Derived / Computed Claims

Computed chemistry results must have a calculation provenance chain.

Example:

```yaml
claim:
  name: molecular_descriptor
input:
  canonical_smiles:
method:
  software: RDKit
  version:
calculation:
  descriptor:
value:
unit:
calculated_at:
status: computed
```

A computed result is reproducible from the specified input and method.

It is not experimental evidence unless an experiment independently supports it.

---

# 23. Literature Evidence

For research-backed scientific claims, store:

```text
title
authors
journal
publication date
DOI/identifier
source URL
claim supported
relevant excerpt/section reference where practical
```

Do not copy large copyrighted passages into the database.

Store concise notes and identifiers instead.

---

# 24. Source Notes

Source notes should be factual and compact.

Bad:

> “This amazing source proves this chemical is definitely safe.”

Good:

> “Source reports the substance's identity and listed function in the specified context.”

Do not inject conclusions that the source itself does not make.

---

# 25. Conflict Resolution

When two relevant sources disagree:

### Step 1
Check whether they are actually discussing the same entity/context.

### Step 2
Check:
- different salts/forms
- different jurisdictions
- different dates
- different product versions
- different measurement methods
- different terminology

### Step 3
Apply the source hierarchy appropriate to the claim.

### Step 4
If unresolved:

```text
status = conflicted
```

### UI example

> **Sources differ on this field.**  
> We are not using the value as a verified fact.

Do not silently select a convenient number.

---

# 26. Missing Evidence

Missing evidence is a first-class state.

Use:

```text
not_found
not_available
not_applicable
not_verified
insufficient_context
```

These must not all be treated identically.

Example:

**Not applicable:** A molecular weight is not appropriate for a complex mixture.

**Not verified:** A molecular weight might exist, but LabelLens has not verified it.

**Not found:** The system searched its approved sources and did not find sufficient evidence.

---

# 27. Unknown Handling

Unknown must be explicit.

Good:

> **Chemical identity not verified**

> **Role not confidently established**

> **No suitable molecular structure available**

> **Current regulatory status not verified for this region**

Bad:

> “Probably safe.”

> “Likely harmless.”

> “This appears to be X” presented as fact.

Unknown states are part of the intended user experience.

---

# 28. Evidence Coverage

For a product analysis, calculate coverage independently.

Possible metrics:

```text
ingredient_match_coverage
chemical_fact_coverage
role_coverage
source_coverage
```

Example:

```text
20 ingredients detected

18 normalized
15 confidently matched
12 have verified chemistry records
14 have role evidence
3 remain unresolved
```

Do not call this a “95% accurate product analysis” unless it is backed by a defined benchmark.

---

# 29. Product-Level Confidence

Avoid one single product score when it hides important differences.

A product report may instead show:

```text
OCR:
Good

Ingredient matching:
Mostly verified

Chemistry coverage:
High

Role coverage:
Moderate

Unknown ingredients:
3
```

This is more honest and useful than:

> “Overall confidence: 91%”

---

# 30. Comparison Evidence Rules

When comparing products:

### Shared ingredient
Need support that both labels contain the ingredient.

### Unique ingredient
Need support that it appears in one analyzed label and not the other within the available captured/verified ingredient list.

### Role difference
Need domain-appropriate role evidence.

### Chemistry difference
Need comparable entities and verified/computed chemistry.

### Regulatory difference
Need current jurisdiction-specific evidence.

Comparison must preserve uncertainty.

---

# 31. Provenance UI

Every key factual card should allow a user to see:

```text
Source
Evidence type
Verification status
Last checked
```

Possible UI:

> **Formula**  
> Verified  
> Source: [database]  
> Last checked: [date]

For computed data:

> **TPSA**  
> Computed with RDKit  
> Input: verified structure  
> Calculation version: [version]

For uncertain data:

> **Role**  
> Medium confidence  
> Evidence: [source]  
> Context-dependent

---

# 32. Audit Trail

Important changes should be traceable.

Example:

```yaml
record_id:
field:
old_value:
new_value:
change_type:
changed_by:
changed_at:
reason:
source:
```

Change types:

```text
created
verified
corrected
replaced
deprecated
reclassified
source_updated
manually_reviewed
```

This enables debugging and scientific auditability.

---

# 33. Human Review

Not everything requires human review.

Use review queues for:

```text
ambiguous matches
conflicting sources
high-value demo ingredients
new chemical classes
new domain roles
regulatory claims
low-confidence OCR with high downstream impact
```

Manual review should be recorded.

```yaml
review_status:
reviewer:
review_reason:
reviewed_at:
decision:
```

---

# 34. Source Registry

All approved source systems should be registered.

Conceptually:

```yaml
source_id:
name:
source_type:
claims_supported:
jurisdictions:
authority_level:
api_available:
access_method:
license:
redistribution_allowed:
cache_allowed:
freshness_class:
notes:
```

This source registry will be maintained in:

`SOURCE_REGISTRY.md`

No new external source should become a trusted source silently.

---

# 35. Free-First Source Strategy

Because the project targets zero/near-zero cost:

1. Prefer free authoritative sources.
2. Prefer public/open APIs where usage rights allow.
3. Prefer local verified datasets for repeated lookups.
4. Cache only where licensing permits.
5. Avoid paid databases for the MVP unless no practical alternative exists.
6. Isolate source adapters so providers can be replaced.
7. Verify API limits and terms before production dependence.

Free does not mean unverified.

---

# 36. External AI Research

Gemini Pro, ChatGPT, Claude Code, OpenCode, Hermes, OmniRoute, or any other AI system can discover:
- candidate sources
- candidate identifiers
- candidate mappings
- candidate explanations
- possible conflicts

But their outputs must be treated as:

```text
research candidate
```

until independently verified.

Example:

```text
Gemini says:
Candidate = X

LabelLens:
candidate_entity = X
status = candidate

↓

authoritative lookup succeeds

↓

status = verified
```

Never:

```text
Gemini says X
↓
database writes X as truth
```

---

# 37. Search Snippets and AI Summaries

Search-result snippets, AI summaries, and generated summaries are discovery aids.

They should not be treated as final evidence when the underlying source can be accessed.

Preferred:

```text
Search result
   ↓
Open original source
   ↓
Evaluate source
   ↓
Capture claim
```

---

# 38. Evidence Collection Process

For a new ingredient:

```text
1. Capture exact label string
2. Normalize
3. Search approved source registry
4. Generate candidate entities
5. Confirm identity
6. Collect field-level facts
7. Validate identifiers/structure
8. Assign domain roles separately
9. Attach sources
10. Assign status/confidence
11. Store audit metadata
12. Only then generate explanation
```

---

# 39. Evidence Quality Checklist

Before marking a field verified:

### Identity
- Is this the same entity?
- Are aliases handled?
- Is the form/salt/isomer correct?

### Source
- Is the source authoritative enough?
- Does it directly support the claim?
- Is it current enough?

### Context
- Does the claim apply to this domain?
- Does jurisdiction matter?
- Is the claim product-specific or general?

### Calculation
- If computed, is the input verified?
- Is the software/method recorded?

### Uncertainty
- Is there conflicting evidence?
- Is the claim broader than the source?

If any critical answer is no, downgrade or leave unknown.

---

# 40. Confidence Propagation

Do not allow upstream uncertainty to disappear.

Conceptually:

```text
OCR LOW
   ↓
Extraction LOW
   ↓
Candidate MEDIUM
   ↓
User correction
   ↓
Identity HIGH
```

A user correction can improve the text identity path.

But a strong chemical database result must not erase the fact that the original OCR was uncertain.

Store both histories.

---

# 41. Evidence and Safety Claims

Safety-related statements require heightened scrutiny.

LabelLens should prefer factual phrasing such as:
- “The source reports…”
- “This ingredient is used as…”
- “This property is reported/computed…”

Avoid unsupported statements such as:
- “Completely safe”
- “Toxic”
- “Harmless”
- “Dangerous”
- “Healthy”
- “Unhealthy”

Especially avoid generalizing laboratory findings, exposure-specific data, or regulatory classifications into individualized conclusions.

---

# 42. Medical/Pharma Evidence Boundary

For pharmaceutical products, the system may explain:
- labeled active ingredients
- labeled excipients
- chemical identities
- formulation roles
- official label information

It must not infer individualized clinical recommendations.

Any output involving treatment, dosing, medicine changes, or patient-specific decisions must be outside the LabelLens product scope.

---

# 43. Evidence Storage Strategy

Use normalized relational storage.

Recommended conceptual tables:

```text
sources
claims
claim_sources
verification_events
review_events
entity_fields
analysis_runs
```

Avoid embedding all source information only inside free-form JSON.

JSON may be used for flexible metadata, but important fields should remain queryable.

---

# 44. Research Snapshot vs Current Truth

LabelLens should distinguish:

```text
current_verified
historical_verified
candidate
obsolete
unknown
```

This matters when labels or regulations change.

Example:

```text
Product scan from 2025
    ≠
Current product formula in 2026
```

A historical scan should preserve what was actually observed at that time.

---

# 45. Privacy and Evidence

A user-uploaded label image may itself contain:
- personal annotations
- receipts
- names
- addresses
- barcodes
- unrelated personal information

Upload processing should minimize retained personal data.

Recommended:
- process locally where practical
- crop/ignore irrelevant regions
- avoid storing raw images by default unless needed
- define retention/deletion behavior
- never place private user data into public chemical datasets

---

# 46. Evidence Regression Tests

Create tests for:

### Correct evidence
A verified source leads to a verified claim.

### Weak evidence
A weak source cannot promote an unverified claim to verified.

### Conflict
Conflicting sources produce `conflicted`.

### Missing source
No source produces `unknown`/`unverified`.

### Expired/dynamic information
A stale regulatory claim triggers re-verification requirements.

### Computed claim
A descriptor records software/method/input provenance.

### AI hallucination
An explanation containing unsupported claims fails validation or review.

---

# 47. Explanation Verification Tests

AI-generated explanations should be checked against structured facts.

Potential deterministic checks:

```text
Does formula mentioned in text equal verified formula?
Does name match canonical entity?
Does role match approved role?
Does structure claim exist?
Does source exist?
Does the answer invent an absent field?
```

The first version can use simple extraction/rule checks rather than a second expensive AI call.

---

# 48. Evidence-First Response Policy

The product should follow these rules:

### High evidence
Give a direct explanation.

### Medium evidence
Give a qualified explanation.

### Low evidence
Give a limited candidate-oriented explanation.

### Conflict
Explain the conflict.

### Unknown
Say what is unknown and why.

### Not applicable
Explain why that data type does not apply.

This policy should be consistent across all domains.

---

# 49. Data Quality Dashboard

For development/admin use, provide metrics such as:

```text
Verified chemical entities
Candidate entities
Unknown entities
Conflicted claims
Claims missing sources
Records awaiting review
OCR failure rate
Entity false-match rate
Role coverage
Source freshness
```

This helps identify where the system is weak.

---

# 50. Definition of “Verified”

A claim may be called **verified** only when:

1. The correct entity is identified.
2. The evidence source is appropriate for the claim.
3. The source supports the exact field/claim.
4. Context and jurisdiction are handled where relevant.
5. Any required validation/calculation passes.
6. Conflicts are resolved or explicitly absent.
7. Provenance is stored.
8. The verification state is recorded.

If these conditions are not met, use a weaker state.

---

# 51. Definition of “Grounded AI Explanation”

An explanation is considered grounded only when:

```text
Explanation
   ↓
references only allowed structured facts
   ↓
all material factual claims have evidence
   ↓
uncertainty is preserved
   ↓
no unsupported recommendations are introduced
```

A polished explanation that violates these conditions is a failed explanation.

---

# 52. Acceptance Criteria

The evidence/confidence layer passes MVP acceptance when:

1. Every important chemical fact can be traced to a source or deterministic computation.
2. Source and claim are separate records.
3. Confidence is field-specific.
4. OCR confidence is separate from chemical identity confidence.
5. Manual correction is stored as a separate event.
6. Candidate and verified states cannot be silently conflated.
7. Mixtures/complex materials can remain non-molecular.
8. Computed descriptors record their method and input.
9. Conflicts are explicit.
10. Dynamic claims have freshness metadata.
11. Regulatory claims are jurisdiction-aware.
12. Product-specific presence is distinct from general chemical identity.
13. AI explanations are grounded in structured evidence.
14. Unsupported generated claims can be detected/rejected.
15. Unknown remains a valid final state.
16. Audit history exists for important record changes.
17. Source licensing/usage status can be recorded.
18. The system can be tested with a known gold-standard dataset.

---

# 53. Priority Order When Trade-offs Occur

When speed and trust conflict, use:

```text
1. Scientific correctness
2. Evidence quality
3. Explicit uncertainty
4. User comprehension
5. Product completeness
6. Automation
7. Visual polish
```

A narrower verified answer is better than a broader hallucinated answer.

---

# 54. Final Principle

> **LabelLens should never ask the user to trust the AI. It should help the user see why the system believes something, how strong the evidence is, what was computed, and what remains unknown.**

This is the trust contract for the entire product.
