# LabelLens — Product Specification

**Document:** PRODUCT_SPEC.md  
**Project:** LabelLens  
**Version:** 1.0 — Product Definition / MVP Freeze  
**Owner:** Amith  
**Project Type:** Computational Chemistry + Full-Stack Software + Explainable AI  
**Budget Principle:** Build and operate with a zero-budget/free-first strategy wherever technically and legally practical.

## 1. Product Definition

**One-line description:** LabelLens turns real-world product labels into understandable chemical information.

**Product promise:**  
> Scan a label → identify ingredients → understand their roles and chemistry → inspect evidence → compare products.

**LabelLens is:** a universal product-label intelligence and computational-chemistry application for understanding ingredient lists across multiple product domains.

**LabelLens is NOT:** a generic chatbot; a medical diagnosis/treatment system; an automatic “safe/unsafe” or “good/bad chemical” judge; a replacement for regulators, doctors, pharmacists, toxicologists, chemists, or laboratory testing; a guarantee that every ingredient can be identified; or a system allowed to invent chemistry when evidence is missing.

## 2. Problem

People encounter technical ingredient names, additive numbers, abbreviations, salts, mixtures, botanical ingredients, active ingredients, excipients, fragrances, polymers, and other formulation components every day.

Labels can be scientifically meaningful but difficult to understand:

1. What is this ingredient?
2. Why is it present?
3. What role does it serve?
4. Is there a valid chemical identity?
5. Does a molecular structure make sense for it?
6. What chemistry explains its role?
7. How does this product differ from another?
8. Where did this information come from?

LabelLens addresses this information gap without turning uncertain chemistry into false certainty.

## 3. Product Vision

Build the simplest reliable product-label intelligence layer that can work across domains.

```text
Real product
    ↓
Label image / manual text
    ↓
OCR + user correction
    ↓
Ingredient extraction
    ↓
Ingredient normalization
    ↓
Chemical/entity resolution
    ↓
Verified chemical/product data
    ↓
Role + domain classification
    ↓
Computational chemistry where valid
    ↓
Evidence + confidence
    ↓
Simple explanation
    ↓
Comparison / exploration
```

## 4. Target Users

**Primary:** students, young adults/Gen-Z consumers, people who regularly check labels, curious users learning practical chemistry, and consumers comparing similar products.

**Secondary:** teachers/educators, chemistry/project students, and product/research teams needing preliminary ingredient intelligence.

**Academic objective:** demonstrate OCR, NLP, entity resolution, structured chemical data, computational chemistry, evidence handling, explainable AI, full-stack engineering, testing, and measurable performance.

## 5. Supported Domains

### Initial MVP
1. Food
2. Snacks
3. Beverages
4. Cosmetics
5. Personal care
6. Household products

### Expansion
7. Supplements
8. Informational pharmaceutical labeling
9. Other consumer products with ingredient/component labels

The core ingredient/chemical/evidence engine is shared. Domain modules define terminology, role taxonomy, interpretation, evidence sources, and UI emphasis.

## 6. Core User Jobs

- **Understand a label:** “What do these ingredient names mean?”
- **Understand purpose:** “Why is this ingredient here?”
- **Explore chemistry:** “What are its formula, structure, properties, or descriptors?”
- **Compare products:** “What is shared and what is different?”
- **Investigate an ingredient:** “I saw this name; what is it?”
- **Learn practical chemistry:** “Explain the chemistry behind something I encounter.”

## 7. Core Product Experience

### Home
Primary CTA: **Scan a Label**

Secondary:
- Search Ingredient
- Compare Products
- Recent Scans
- Learn

Mobile-first because scanning is the primary interaction.

### Scan Flow
```text
Camera OR image upload
      ↓
Preview / crop
      ↓
OCR
      ↓
Extracted text
      ↓
Editable ingredient list
      ↓
User confirms / corrects
      ↓
Analyze
```

**Critical:** OCR output must never silently become verified ingredient data.

### Product Analysis
Show:
- Product/domain classification
- Ingredient count
- Ingredient cards
- Functional-role categories
- Matched vs unmatched ingredients
- Confidence
- Evidence/source availability
- “Why is this here?”

Unknown example:
> Not confidently identified. The label text was detected, but no sufficiently reliable chemical/entity match was found.

Do not guess.

### Ingredient Detail
Show only supported fields:
- Preferred name
- Common names / aliases
- Formula
- Molecular weight
- CAS where valid
- SMILES/InChI where valid
- Structure where valid
- Chemical class
- Functional groups/descriptors where meaningful
- Domain roles
- Why it may be used
- Evidence/source records
- Confidence
- Representation type
- Limitations

Representation states may include:
- Single molecule
- Salt / defined entity
- Polymer/material
- Mixture
- Natural complex material
- Formulation
- Unknown

Never generate a molecular structure merely because the UI expects one.

### “Why Is This Here?”
For a matched ingredient, explain:
1. What is it?
2. Why may it be present?
3. What chemistry is relevant?
4. What evidence supports the statement?
5. What is uncertain/context-dependent?

### Compare
For Product A vs B show:
- Shared ingredients
- Unique ingredients
- Role/category differences
- Chemistry differences only when meaningful and supported
- Evidence coverage differences

Never call a product “healthier,” “safer,” or “better” from ingredient count alone.

## 8. Ingredient Intelligence Model

Keep these layers separate:

```text
1. Raw OCR text
2. Extracted ingredient text
3. Normalized ingredient
4. Candidate entity
5. Matched chemical entity
6. Verified chemical facts
7. Product-domain role
8. Evidence/provenance
9. AI-generated explanation
```

Each stage should be inspectable during development/debugging.

## 9. Computational Chemistry Scope

### MVP
- Chemical identity lookup
- Formula
- Molecular weight
- SMILES validation where applicable
- Structure rendering where applicable
- Basic molecular descriptors where applicable
- Functional-group/descriptive information where appropriate

### Later
- Chemical similarity
- Ingredient clustering
- Descriptor-based comparisons
- Structure-based search
- ML classification/property tasks only with a valid dataset and target

Never force a molecular representation onto mixtures, trade names, complex formulations, undefined natural materials, or ambiguous OCR text.

## 10. AI Scope

AI may assist with:
- OCR
- extraction candidates
- normalization suggestions
- entity-match candidates
- research
- explanation drafting
- UX copy
- development assistance
- test generation

AI must NOT be final authority for:
- chemical identity
- formula
- molecular structure
- regulatory status
- medical guidance
- unsupported safety conclusions

Preferred pipeline:

```text
AI candidate
   ↓
validation / database lookup
   ↓
confidence assessment
   ↓
evidence attachment
   ↓
approved structured record
   ↓
user-facing explanation
```

## 11. Evidence and Trust

Important factual chemistry claims should be traceable.

Store where practical:
- Source name
- Source type
- Source URL/identifier
- Retrieval date
- Relevant fact/field
- Confidence
- Verification status

Prefer:
1. Government/regulatory authorities
2. Scientific databases
3. Primary/peer-reviewed literature
4. Official manufacturer/product labeling
5. High-quality secondary references
6. Unverified sources only as discovery leads, not final authority

For changing regulations, formulations, APIs, platform limits, pricing, or service availability, verify current official sources.

## 12. Confidence Model

Track separately:
- OCR confidence
- Extraction confidence
- Normalization confidence
- Entity-match confidence
- Role-classification confidence
- Chemical-property verification confidence
- Explanation support/confidence

Do not collapse these into one fake “AI confidence” score.

## 13. MVP Definition

The MVP is complete when a real user can:

1. Open LabelLens on a phone.
2. Upload or capture a label.
3. Receive OCR text.
4. Edit OCR mistakes.
5. Confirm ingredients.
6. Run analysis.
7. See normalized ingredients.
8. See matched vs unmatched ingredients.
9. Open ingredient chemistry.
10. See role/category.
11. See evidence/provenance.
12. Read a simple explanation.
13. Compare two analyzed products.
14. Recover gracefully from OCR, matching, network, or API errors.

## 14. MVP Out of Scope

- Medical diagnosis
- Treatment recommendations
- Dosage recommendations
- Medicine substitution/start/stop advice
- Universal toxicity prediction
- Automatic safe/unsafe verdicts
- Fully autonomous chemical research
- Forced structures for every ingredient
- ML property prediction without a validated dataset
- Massive commercial product databases before core reliability exists
- Paid infrastructure that is unnecessary for the MVP

## 15. Free-First Engineering Constraint

Build and operate at zero cost wherever practical.

Available tools/resources:
- ChatGPT
- Gemini Pro
- OmniRoute
- Hermes Agent
- Termux
- OpenCode
- Claude Code
- GitHub

Prefer free/open technologies where practical:
- Next.js
- TypeScript
- Tailwind CSS
- FastAPI
- Python
- RDKit
- open scientific data where licensing permits

Before adding any paid API/service:
1. Check whether it is actually needed.
2. Check for a free/local alternative.
3. Verify current limits/pricing from official documentation.
4. Estimate usage.
5. Avoid continuous paid inference as an architectural requirement.

Use OmniRoute for model routing where it provides practical cost/control benefits, but isolate provider-specific logic and keep the chemistry/data layer provider-independent.

## 16. Non-Functional Requirements

**Performance:** fast initial load, responsive image handling, clear OCR/analysis progress, minimal unnecessary AI/API calls, sensible caching.

**Reliability:** typed validation, deterministic chemistry calculations, graceful failures, safe retries, no silent corruption.

**Security:** no frontend secrets; validate file type/size; sanitize OCR/AI text; protect DB access; use RLS where needed; mitigate prompt injection; provide appropriate privacy/deletion controls.

**Accessibility:** readable typography, semantic controls, keyboard support, adequate contrast, clear confidence/error states.

## 17. Success Metrics

Do not call the project successful merely because the UI works.

Measure:
- OCR/ingredient extraction accuracy
- False/unknown entity-match rate
- Role-classification accuracy on reviewed examples
- Scan-to-result completion
- OCR correction burden
- Compare-flow completion
- API error rate
- performance observations
- automated test/build pass rate

Create and use a real-label benchmark.

## 18. Initial Test Dataset

Start with **30 real labels**:

- 10 food/snacks/beverages
- 5 cosmetics
- 5 personal care
- 5 household
- 5 other supported examples

Record:
- Original image
- Expected ingredient text
- Expected normalized ingredients
- Verified entity matches
- Verified roles
- Known OCR traps
- Known ambiguous cases

Scale later:

```text
30 → 50 → 100 → 250+
```

## 19. UX Philosophy

LabelLens should feel modern, fast, understandable, trustworthy, chemistry-aware, and not academic-looking.

Avoid:
- Fear-based language
- Fake precision
- Overwhelming jargon
- Huge tables by default
- Excessive animation
- “AI magic” without evidence

Use progressive disclosure:

```text
Simple answer
   ↓
Why?
   ↓
Chemistry
   ↓
Evidence
   ↓
Technical details
```

## 20. Portfolio Positioning

Present LabelLens as:

> **A computational-chemistry-powered product intelligence platform combining OCR, chemical entity resolution, molecular data, evidence provenance, domain-aware role classification, comparison, and explainable AI.**

Show:
1. Problem
2. User
3. Product
4. Architecture
5. Chemistry methodology
6. Data pipeline
7. AI boundaries
8. Accuracy/testing
9. Deployment
10. Challenges
11. Limitations
12. Future improvements

Never claim universal accuracy, complete chemical coverage, medical authority, regulatory authority, or guaranteed safety conclusions without evidence.

## 21. Presentation Demo

Ideal live flow:

```text
1. Scan a real label
2. Show OCR
3. Correct one OCR error
4. Analyze
5. Open an ingredient
6. Show chemistry/structure where valid
7. Tap “Why is this here?”
8. Open evidence
9. Compare another product
10. Show an unknown/unverified ingredient
```

The unknown case is deliberate: LabelLens demonstrates that it prefers uncertainty over hallucination.

## 22. Definition of Done

The product specification is frozen when:
- Product purpose is clear
- MVP boundaries are clear
- Domain strategy is clear
- Chemistry boundaries are clear
- AI boundaries are clear
- Evidence rules are clear
- Free-first constraint is clear
- Success metrics are defined
- Out-of-scope features are documented

Any later scope change must be an explicit documented decision.

## 23. Next Documents

1. `PRODUCT_SPEC.md` — this file
2. `CHEMISTRY_DATA_SPEC.md`
3. `EVIDENCE_AND_CONFIDENCE_SPEC.md`
4. `DATABASE_SCHEMA.md`
5. `API_SPEC.md`
6. `SOURCE_REGISTRY.md`
7. `LABEL_REGRESSION_DATASET.csv`
8. `INGREDIENT_GOLDEN_DATA.csv`
9. `ARCHITECTURE.md`
10. `TEST_STRATEGY.md`
11. `SECURITY.md`
12. `DECISIONS.md`
13. `CHANGELOG.md`
14. `CASE_STUDY.md`
15. `PRESENTATION.md`
16. `DEMO_SCRIPT.md`

**Rule:** Implementation agents must not silently redefine the product.

## Final North Star

> **LabelLens should make a product label as understandable as a good search result—while keeping chemistry, evidence, uncertainty, and scientific boundaries visible underneath.**
