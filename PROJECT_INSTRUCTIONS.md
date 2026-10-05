# LabelLens — Project Instructions

## 1. Project identity

**Name:** LabelLens  
**Type:** Universal product-label intelligence platform  
**Academic context:** 1st-year B.Tech CSE (GenAI) + Computational Chemistry  
**Portfolio objective:** Make this a genuine software product that demonstrates product thinking, full-stack engineering, computational chemistry, data quality, explainable AI, testing, deployment, and presentation skill.

### Core promise

> **Scan a product label → understand what is inside → understand the chemistry → compare products → explore the evidence.**

The app is intended to work across:
- Food
- Snacks
- Beverages
- Cosmetics
- Personal care
- Household products
- Supplements
- Informational pharmaceutical/product labeling

The architecture must be domain-agnostic. Domain modules may change terminology and explanation rules, but the ingredient/chemical/evidence engine should be shared.

---

## 2. The real problem

People routinely see ingredient names, INS/E-numbers, additives, chemical names, trade names, abbreviations, or technical terminology on labels and do not understand:
- What the ingredient is
- Why it appears in the product
- What role it serves
- Whether it has a meaningful molecular representation
- How two products differ

LabelLens must reduce this confusion without pretending to give medical or toxicological certainty.

**Do not make the product a generic AI chatbot.** The core value must come from structured data, chemistry processing, classification, comparison, and evidence.

---

## 3. Product principles

1. **Truth before fluency.**
2. **Evidence before AI-generated explanation.**
3. **Context before “good/bad.”**
4. **Unknown is better than invented.**
5. **Separate raw OCR, normalized ingredient, matched chemical entity, and generated explanation.**
6. **Never force a molecular structure where the substance is a mixture, formulation, complex natural material, or otherwise not appropriately represented as one molecule.**
7. **Every important scientific claim must have provenance.**
8. **Use confidence levels for OCR, matching, and classification.**
9. **Make limitations visible.**
10. **MVP reliability beats flashy AI.**

---

## 4. Target user experience

### Home
Primary CTA: **Scan a Label**

Secondary:
- Search an ingredient
- Compare products
- Recent scans
- Learn chemistry

### Scan flow
Camera/upload → crop/preview → OCR → extracted text → editable ingredient list → “Analyze”

Users must be able to correct OCR mistakes before analysis.

### Product analysis
Show:
- Detected product/domain
- Ingredient count
- Ingredient cards
- Functional-role categories
- Unknown/unmatched ingredients
- Confidence indicators
- Evidence/source links

### Ingredient detail
Show only verified/available fields:
- Name/common names
- Formula
- Molecular weight
- SMILES when valid
- Molecular structure when valid
- Chemical class
- Functional groups/descriptors where computationally meaningful
- Product-domain role
- Why it may be included in the formulation
- Sources/evidence
- Limitations/uncertainty

### Compare
Compare Product A vs Product B:
- Shared ingredients
- Ingredients unique to each
- Role-category differences
- Available chemistry differences
- Source-backed notes

Never automatically declare one product “healthier,” “safer,” or “better” from ingredient count alone.

---

## 5. Computational chemistry layer

Use Python/RDKit where chemically appropriate for:
- SMILES parsing/validation
- Molecular descriptors
- Molecular weight
- Structure rendering
- Functional-group/descriptive analysis
- Chemical similarity

For substances without a suitable single-molecule representation, preserve the entity as non-structure-bearing and explain why.

The chemistry engine must be deterministic and testable. AI can explain structured results but must not silently replace calculations.

---

## 6. Recommended architecture

```text
Frontend (Next.js/TypeScript/Tailwind)
        ↓
API / orchestration (FastAPI)
        ↓
OCR + normalization
        ↓
Ingredient/entity matching
        ↓
Verified chemical + product data
        ↓
RDKit chemistry engine
        ↓
Role/domain classification
        ↓
Evidence + confidence layer
        ↓
Explanation layer
        ↓
Frontend
```

### Data entities

At minimum:
- `products`
- `product_labels`
- `ingredients`
- `chemical_entities`
- `ingredient_aliases`
- `product_ingredients`
- `ingredient_roles`
- `sources`
- `ingredient_source_links`
- `analysis_runs`
- `comparisons`

Store source provenance at the record/field level whenever practical.

---

## 7. AI strategy

Use AI for:
- Research
- OCR assistance/fallback
- Normalization suggestions
- Entity matching candidates
- Natural-language explanations
- UX copy
- Development assistance

Do NOT use AI as the final authority for:
- Chemical identity
- Molecular formula
- Molecular structure
- Regulatory claims
- Medical advice
- Safety conclusions

A recommended pipeline:

```text
AI candidate
→ deterministic/database validation
→ confidence
→ source
→ approved record
→ user-facing explanation
```

---

## 8. Tool strategy

### ChatGPT
Architecture, product decisions, research synthesis, QA, documentation, presentation, portfolio.

### Gemini Pro
Deep research, independent source discovery, image/OCR experiments, dataset investigation, cross-checking.

### OpenCode
Primary coding agent.

### Claude Code
Debugging, refactoring, review, tests, security review.

### Hermes Agent in Termux
Command execution/orchestration and repeatable workflows.

### GitHub
Repository, issues, branches, checkpoints, changelog.

### Hosting
Prefer a simple production stack: Vercel for the web frontend and a Python-capable backend host for FastAPI. Re-check current platform limits/pricing before deployment.

### Supabase
Use Postgres for structured data and Storage when image/file storage is actually needed. Use Auth only if the product requires accounts. Apply RLS where client-accessible data requires it.

---

## 9. Research and anti-hallucination protocol

Before importing a chemical record:
1. Find an authoritative or high-quality source.
2. Record the source and retrieval date.
3. Normalize names/aliases.
4. Validate chemical identifiers.
5. Mark confidence.
6. Preserve unresolved conflicts.
7. Never invent missing data.

For current regulations, standards, product formulations, APIs, hosting limits, pricing, libraries, or platform capabilities: **browse and verify current official documentation before making a decision.**

For scientific claims: prefer primary papers, government/scientific databases, standards bodies, or authoritative institutional sources.

---

## 10. MVP scope

### Must-have
- Responsive web app
- Label upload/camera input
- OCR
- Editable extracted ingredient list
- Ingredient normalization
- Chemical lookup
- Role classification
- Ingredient detail page
- Product analysis report
- Product comparison
- Evidence/provenance
- Unknown/unmatched handling
- Basic analytics/error logging
- Tests
- Production deployment

### Nice-to-have later
- Barcode lookup
- User accounts
- Scan history sync
- Advanced chemical similarity
- Molecular visualization
- ML classification
- Multi-language labels
- PWA/offline support

Do not build these before the MVP works reliably.

---

## 11. Engineering rules

- Use TypeScript strict mode and typed API contracts.
- Python code must be modular and testable.
- Validate every API input.
- Never commit secrets.
- Use environment variables.
- Restrict upload types and sizes.
- Handle OCR failures gracefully.
- Never display an unsupported chemical claim as fact.
- Maintain sample-label regression tests.
- Add loading, empty, error, retry, and “not enough information” states.
- Optimize for mobile because scanning is the primary interaction.
- Avoid heavy animations; prioritize speed and clarity.

---

## 12. Development workflow

Work in vertical slices:

**Research → schema → API → UI → tests → verification → commit**

Each implementation task must contain:
- Goal
- Files to change
- Exact acceptance criteria
- Test cases
- Known risks
- Expected output

Use feature branches or small commits.

After meaningful changes:
- Run lint
- Run type checks
- Run unit tests
- Run build
- Run key E2E flows

Never declare “done” without verification.

---

## 13. Presentation strategy

The final presentation should tell a story:

**Problem → real user example → why existing labels are hard to understand → LabelLens → architecture → computational chemistry → evidence system → live scan demo → comparison demo → limitations → future scope.**

Demo with several real labels from different domains.

Show at least one case where the system says:
> **“Unknown / insufficient evidence”**

This demonstrates scientific honesty rather than weakness.

---

## 14. Portfolio strategy

The GitHub/portfolio case study should clearly show:
- Problem
- User
- Product concept
- Architecture
- Chemistry methodology
- Data pipeline
- AI boundaries
- Screenshots
- Testing/accuracy evaluation
- Deployment
- Challenges
- Design decisions
- Limitations
- Future work

Position it as:

> **“Built a computational-chemistry-powered product intelligence platform that connects OCR, chemical entity resolution, molecular data, structured evidence, and explainable AI.”**

Do not claim production-scale accuracy, medical authority, or universal chemical coverage unless actually measured.

---

## 15. Default decision rule

When there are multiple possible implementation paths, choose the one that maximizes:

**Real user utility + scientific correctness + maintainability + demo quality + portfolio value**

while minimizing:

**unnecessary complexity + unsupported claims + hallucination risk + vendor lock-in + fake AI.**
