# LabelLens — Source Registry

**Document:** SOURCE_REGISTRY.md  
**Project:** LabelLens  
**Version:** 1.0  
**Registry date:** 2026-10-04  
**Purpose:** Define which external sources LabelLens may use, what each source is appropriate for, how much authority it carries, how data may be accessed/reused, and when a source must be re-verified.

---

# 1. Source Registry Purpose

LabelLens is evidence-first.

The source registry exists so that agents, developers, and the application do not randomly choose websites for chemical claims.

The core rule is:

> **A source is trusted only for the claim types it is appropriate for, and source authority never replaces claim-level verification.**

A source may be excellent for chemical identity but unsuitable for:
- current regulatory status
- product-specific formulation
- medical interpretation
- exposure conclusions
- another jurisdiction's regulations

---

# 2. Source Classes

Use these source classes:

```text
A — Primary / authoritative
B — High-quality scientific reference
C — Product/manufacturer
D — Secondary reference
E — Discovery-only
```

### A — Primary / authoritative
Government/regulator databases, official standards/regulations, authoritative chemical databases, or primary scientific sources.

### B — High-quality scientific reference
Established scientific databases and peer-reviewed reviews.

### C — Product/manufacturer
Useful for product-specific label/formulation claims.

### D — Secondary
Useful for explanation and discovery; verify important claims elsewhere.

### E — Discovery-only
Search results, blogs, forums, social media, AI-generated pages, or unverified aggregators.

---

# 3. Status Values

Each source entry has a status:

```text
approved
conditional
discovery_only
blocked
retired
```

### approved
Suitable for its defined claim types under the stated usage rules.

### conditional
Useful, but licensing, jurisdiction, freshness, legal conditions, or source-specific limitations require additional checks.

### discovery_only
Use to discover candidates; do not use directly as final evidence.

### blocked
Do not use.

### retired
Previously registered but no longer used.

---

# 4. Source Selection Rule

When multiple sources support the same claim:

```text
1. Correct entity/context
2. Claim-specific authority
3. Currentness/freshness
4. Directness of evidence
5. Source quality
6. Provenance completeness
```

Do not choose a source merely because it is easier to parse.

---

# 5. SOURCE: PubChem

**Source ID:** `PUBCHEM`  
**Organization:** U.S. National Library of Medicine / NIH  
**Class:** A  
**Status:** approved for defined claim types; source-level licensing remains important  
**Primary use:** chemical identity and molecular information

### Official resources

```text
https://pubchem.ncbi.nlm.nih.gov/
https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
https://pubchem.ncbi.nlm.nih.gov/docs/downloads
https://pubchem.ncbi.nlm.nih.gov/docs/data-sources
https://www.ncbi.nlm.nih.gov/home/about/policies/
```

### Good for

- Chemical names
- Synonyms/aliases
- PubChem CID
- Molecular formulas
- Molecular structures
- SMILES/InChI/InChIKey where provided
- Chemical identifiers
- Chemical record cross-references
- Discovery of related chemical records

PubChem provides PUG REST programmatic access and downloadable data. Its current documentation says PubChem is free to use, but data comes from hundreds of contributors and source-specific licensing/reuse conditions can differ. Provenance is provided for contributed data. citeturn895993search1turn867466search1turn814714search9

### Not automatically good for

- Product-specific current formulation
- Jurisdiction-specific regulatory conclusion
- Individual medical advice
- Treating every contributed assertion as equally authoritative

### Licensing/reuse rule

Do not assume the entire PubChem dataset has one uniform downstream license.

For any imported field:
1. retain PubChem record/identifier;
2. retain contributor/source provenance where available;
3. inspect source-specific licensing when redistributing or bulk-ingesting;
4. prefer targeted API lookups for MVP rather than blindly copying large datasets.

NCBI states that molecular databases may have third-party contributor rights and that users must examine source-specific copyright/licensing restrictions. citeturn814714search0turn867466search1

### LabelLens use

**Preferred for:** canonical chemical candidate verification and molecular metadata.

---

# 6. SOURCE: ChEBI

**Source ID:** `CHEBI`  
**Organization:** EMBL-EBI  
**Class:** A/B  
**Status:** approved  
**Primary use:** chemical entities of biological interest, names, identifiers, ontology, structures

### Official resources

```text
https://www.ebi.ac.uk/chebi/
https://www.ebi.ac.uk/chebi/tools
https://www.ebi.ac.uk/chebi/downloads
https://www.ebi.ac.uk/chebi/about
```

ChEBI provides public REST APIs with no authentication required for its public APIs, and downloadable datasets. Its site states that ChEBI data are freely accessible, fully traceable to original sources, and available under CC BY 4.0 subject to EMBL-EBI terms. citeturn895993search9turn867466search0turn895993search4

### Good for

- Chemical entity names
- Synonyms
- ChEBI identifiers
- Definitions
- Chemical relationships
- Formula/mass fields
- SMILES/InChI/InChIKey
- Chemical ontology/classification
- Candidate entity resolution

### Important limitation

ChEBI focuses on biologically relevant chemical entities. It is not the universal source for every food additive, cosmetic ingredient, household chemical, proprietary formulation, or regulatory claim.

### LabelLens use

**Preferred for:** identity/ontology enrichment when an applicable ChEBI entity exists.

---

# 7. SOURCE: NIST Chemistry WebBook

**Source ID:** `NIST_WEBBOOK`  
**Organization:** National Institute of Standards and Technology  
**Class:** A/B  
**Status:** conditional  
**Primary use:** physical/chemical reference data for well-defined species

### Official resources

```text
https://webbook.nist.gov/chemistry/
https://webbook.nist.gov/chemistry/guide/
https://www.nist.gov/programs-projects/nist-chemistry-webbook
https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications
```

NIST Chemistry WebBook provides chemical and physical property data for chemical species and reactions, including thermochemical, spectral, and other reference information. citeturn775426search5turn775426search6

### Good for

- Thermochemical data
- Thermophysical data
- Spectral information
- Reaction information
- Reference data for well-defined chemical species

### Critical licensing rule

NIST identifies Chemistry WebBook as SRD 69. NIST states that Standard Reference Data are subject to special copyright/licensing rules and that licensed SRD products require permission/licensing for certain reproduction and storage uses. Therefore:

> **Do not bulk-copy or mirror NIST SRD data into LabelLens by default.**

Use targeted online reference/lookup workflows unless reuse/storage rights for the exact data are confirmed. citeturn775426search0turn775426search2turn775426search4

### LabelLens use

**Preferred for:** targeted scientific reference checks.

**Not preferred for:** building the MVP bulk chemical cache.

---

# 8. SOURCE: RDKit

**Source ID:** `RDKIT`  
**Organization:** RDKit open-source project  
**Class:** A for computation/software methodology  
**Status:** approved  
**Primary use:** deterministic cheminformatics

### Official resources

```text
https://rdkit.org/docs/
https://github.com/rdkit/rdkit
```

RDKit provides cheminformatics and machine-learning software, molecular operations, descriptor generation, fingerprinting, and a PostgreSQL cartridge. The current official source identifies the code as BSD licensed. citeturn896354search1turn896354search0

### Good for

- SMILES parsing/validation
- Molecular structures
- Molecular descriptors
- Fingerprints
- Similarity calculations
- Functional-group/substructure logic
- Molecule rendering
- Reproducible deterministic computation

### Critical rule

RDKit validates and computes from representations. It does **not** prove that the representation corresponds to a label ingredient.

```text
Verified identity
      +
appropriate structure
      ↓
RDKit
      ↓
computed result
```

Never:

```text
OCR text
 ↓
AI guesses SMILES
 ↓
RDKit
 ↓
"verified chemistry"
```

### LabelLens use

**Primary local chemistry engine.**

Record:
- RDKit version
- input structure
- method/descriptor
- calculation timestamp

---

# 9. SOURCE: FSSAI — India Food Standards

**Source ID:** `FSSAI_FOOD_REGS`  
**Organization:** Food Safety and Standards Authority of India  
**Class:** A  
**Status:** approved for India-specific regulatory reference  
**Primary use:** Indian food standards and food-additive requirements

### Official resources

```text
https://fssai.gov.in/
https://fssai.gov.in/standards/product-standards
https://fssai.gov.in/food-law/regulations/compendium/food-products-standards
https://fssai.gov.in/food-law/regulations/amendments/food-products-standards
```

FSSAI publishes food-product and food-additive regulations and maintains amendment records. Its current regulatory pages list the Food Products Standards and Food Additives Regulations and amendments. citeturn867466search2turn867466search4turn867466search7

### Good for

- India-specific food standards
- Food additive regulatory context
- Product-category requirements
- Current amendments
- Indian regulatory terminology

### Label-specific use

Do not use a general FSSAI rule to prove that a particular commercial product currently contains an ingredient.

Use:

```text
current product label
+
FSSAI regulatory source
```

when both are needed.

### Freshness

**High priority / dynamic.**

FSSAI's site currently lists 2026 notifications and amendments, so regulatory claims must be checked against the current official material before being displayed as current. citeturn867466search9turn867466search12

---

# 10. SOURCE: FSSAI — Labelling and Display

**Source ID:** `FSSAI_LABELING`  
**Organization:** Food Safety and Standards Authority of India  
**Class:** A  
**Status:** approved for India-specific labelling reference

### Official resources

```text
https://www.fssai.gov.in/food-law/regulations
https://www.fssai.gov.in/upload/uploadfiles/files/Comp_Labelling%20Display_Version_VII_03042025.pdf
```

FSSAI's Labelling and Display Regulations define requirements for pre-packaged food labelling; the official amendment page currently shows amendments through March 24, 2026. citeturn867466search80turn867466search12

### Good for

- Understanding Indian food label structure
- Label terminology
- Required label information
- Interpretation of ingredient-list context

### Rule

Do not treat the regulation as proof that a specific label is compliant. Compliance assessment is a separate, higher-risk feature and is outside the MVP.

---

# 11. SOURCE: Codex Alimentarius GSFA

**Source ID:** `CODEX_GSFA`  
**Organization:** FAO/WHO Codex Alimentarius Commission  
**Class:** A  
**Status:** approved for international food-additive reference  
**Primary use:** food-additive provisions and functional classes

### Official resources

```text
https://www.fao.org/fao-who-codexalimentarius/codex-texts/dbs/gsfa/en/
https://codex.fao.org/codex-texts/codex-online-databases/gsfa
```

Codex GSFA is a searchable database of adopted food-additive provisions, searchable by name, synonym, INS number, functional class, and food category. It is regularly updated as new provisions are adopted. citeturn296183search0turn296183search1

### Good for

- INS numbers
- Food additive names/synonyms
- Functional classes
- Food categories
- Conditions of use in Codex context
- International reference cross-checking

Codex itself defines functional classes such as acidity regulator, antioxidant, preservative, stabilizer, sweetener, and thickener. citeturn296183search2turn296183search4

### Critical rule

Codex is an international standards reference. It is **not a substitute for Indian, EU, US, or other national regulatory law**.

Never display:

> “Codex says this, therefore it is legal in India.”

Use jurisdiction-specific sources.

---

# 12. SOURCE: European Commission — EU Food Additives Database

**Source ID:** `EU_FOOD_ADDITIVES`  
**Organization:** European Commission  
**Class:** A  
**Status:** approved for EU food-additive regulatory reference

### Official resource

```text
https://food.ec.europa.eu/food-safety/food-improvement-agents/additives/database_en
```

The database is based on the Union list of food additives and is intended to inform about additives approved for use in food in the EU and their conditions of use. citeturn895993search0turn895993search2

### Good for

- EU additive status
- EU food categories
- Conditions of use
- EU-specific contextual research

### Rule

EU status must never be generalized to another jurisdiction.

### Freshness

Dynamic. Re-check current database/regulation for current claims.

---

# 13. SOURCE: FDA — Food Additive Status

**Source ID:** `FDA_FOOD_ADDITIVES`  
**Organization:** U.S. Food and Drug Administration  
**Class:** A  
**Status:** approved for US regulatory reference

### Official resources

```text
https://www.fda.gov/food/food-additives-petitions/food-additive-status-list
https://www.fda.gov/food/food-ingredients-packaging/determining-regulatory-status-food-ingredient
```

FDA maintains food-additive regulatory information and guidance on determining regulatory status. FDA explains that food-additive status depends on statutory/regulatory conditions and exemptions such as GRAS, among other provisions. citeturn867466search3turn867466search10

### Good for

- US food additive regulatory context
- Definitions and regulatory pathways
- US-specific ingredient status research

### Rule

Do not turn a US regulatory status into a global safety conclusion.

---

# 14. SOURCE: FDA — Food Contact Substances

**Source ID:** `FDA_FOOD_CONTACT`  
**Organization:** U.S. Food and Drug Administration  
**Class:** A  
**Status:** approved for US food-contact material reference

### Official resource

```text
https://www.fda.gov/food/packaging-food-contact-substances-fcs/inventory-food-contact-substances-listed-21-cfr
```

FDA's database includes food-contact substances listed in 21 CFR and information about intended uses and conditions of use. citeturn867466search6

### LabelLens use

Useful for future packaging/material analysis.

Do not use it as evidence that a substance is approved for every packaging use or every jurisdiction.

---

# 15. SOURCE: European Commission — CosIng

**Source ID:** `EU_COSING`  
**Organization:** European Commission  
**Class:** A for cosmetic nomenclature/informational context  
**Status:** approved with strong regulatory caution

### Official resources

```text
https://single-market-economy.ec.europa.eu/sectors/cosmetics/cosmetic-ingredient-database_en
https://single-market-economy.ec.europa.eu/sectors/cosmetics/cosmetic-ingredient-database/cosing-glossary-ingredients_en
```

CosIng contains cosmetic ingredient nomenclature and related information, including INCI names, chemical names/identifiers, ingredient functions, historical/current information, and links to SCCS opinions. citeturn895993search5turn895993search12

### Critical limitation

The European Commission explicitly states that CosIng has an informative purpose and no legal value. Appearance in the CosIng inventory does not by itself mean an ingredient is approved for cosmetic use. Regulatory status comes from the applicable Cosmetics Regulation and Annexes. citeturn895993search5turn895993search12

### LabelLens use

**Preferred for:**
- cosmetic ingredient names
- INCI/nomenclature context
- cosmetic function metadata
- discovery of relevant EU cosmetic references

**Not sufficient by itself for:**
- “approved”
- “safe”
- “legal everywhere”
- product-specific safety conclusions

---

# 16. SOURCE: CDSCO / Indian Regulatory Material

**Source ID:** `CDSCO_INDIA`  
**Organization:** Central Drugs Standard Control Organisation / Government of India  
**Class:** A  
**Status:** conditional / future implementation

### Official starting point

```text
https://www.cdsco.gov.in/
```

CDSCO publishes Indian drugs/cosmetics regulatory material. The Drugs and Cosmetics Rules include cosmetic labeling requirements, including ingredient-list provisions and restrictions on false/misleading cosmetic claims. citeturn814714search63

### LabelLens rule

Pharmaceutical/cosmetic regulatory support must remain:
- informational
- jurisdiction-specific
- current-source verified

The MVP should not attempt automated legal/compliance certification.

Before any CDSCO-derived regulatory statement is deployed, verify the latest official rule, amendment, notification, or gazette applicable to the exact claim.

---

# 17. SOURCE: Product Labels / Manufacturer Pages

**Source ID:** `PRODUCT_LABEL_PRIMARY`  
**Organization:** individual manufacturer/brand/product label  
**Class:** C  
**Status:** approved for product-specific observation when authentic/current

### Use for

- Exact product ingredient list
- Brand/product name
- Product-specific formulation information
- Serving/usage label context
- Product-specific claims

### Priority

For:

> “This product contains X”

the actual label image is often the strongest direct evidence of what was observed.

For:

> “X has property Y”

use a chemical/scientific source instead.

### Important

A manufacturer marketing page is not automatically authoritative for scientific or regulatory conclusions.

Preserve:
- URL
- access date
- label version/date if available
- captured image/hash where appropriate

---

# 18. SOURCE: Open Food Facts

**Source ID:** `OPEN_FOOD_FACTS`  
**Organization:** Open Food Facts  
**Class:** C/D  
**Status:** conditional

### Official resources

```text
https://github.com/openfoodfacts/openfoodfacts-server
https://github.com/openfoodfacts/openfoodfacts-server/tree/main/docs/api
https://world.openfoodfacts.org/
```

Open Food Facts provides an API and open product database containing product/ingredient/nutrition information. Its current API documentation identifies v3 as the recommended current API and states that the database is under the Open Database License, with product images under Creative Commons Attribution-ShareAlike; it also explicitly warns that user-contributed data may not be accurate, complete, or reliable. citeturn590857search2turn590857search1

### Good for

- Product discovery
- Barcode-to-product candidate lookup
- Ingredient-list discovery
- Benchmark/test data candidates

### Not authoritative for

- Chemical identity
- Regulatory status
- Safety conclusions
- Complete/current product accuracy

### Licensing rule

ODbL has obligations. Product images have separate licensing. Do not combine Open Food Facts data with incompatible non-free datasets in a way that creates licensing problems. Read the current reuse terms before redistribution. citeturn590857search1

### LabelLens position

Use primarily as a **candidate/product-discovery source**, then validate important chemical facts through stronger sources.

---

# 19. SOURCE: Open Beauty Facts

**Source ID:** `OPEN_BEAUTY_FACTS`  
**Organization:** Open Food Facts ecosystem  
**Class:** C/D  
**Status:** conditional

### Official starting point

```text
https://github.com/openfoodfacts/openbeautyfacts
https://world.openbeautyfacts.org/
```

Open Beauty Facts is a collaborative database of cosmetic products and ingredient/label information. Its project documentation describes it as an open cosmetic-product database. citeturn590857search5

### Good for

- Cosmetic product discovery
- Candidate ingredient lists
- Barcode/product lookup
- Test-label sourcing

### Not authoritative for

- Chemical identity by itself
- Regulatory status
- Clinical/safety conclusions

### Licensing

Verify the current data/image reuse terms before redistribution; do not assume that every associated field or image has identical licensing.

---

# 20. SOURCE: PubMed

**Source ID:** `PUBMED`  
**Organization:** U.S. National Library of Medicine / NIH  
**Class:** A/B  
**Status:** approved for scientific literature discovery

### Official resource

```text
https://pubmed.ncbi.nlm.nih.gov/
```

### Good for

- Peer-reviewed literature discovery
- Scientific mechanism research
- Primary-study identification
- Review identification
- Citation metadata

### Rule

A PubMed search result is not automatically evidence.

The system should:
```text
PubMed discovery
    ↓
open article/abstract/full text where available
    ↓
evaluate study
    ↓
extract claim
    ↓
attach evidence
```

Do not rely on title/snippet alone.

---

# 21. SOURCE: Official Scientific Papers / DOI Sources

**Source ID:** `PRIMARY_LITERATURE`  
**Class:** A/B  
**Status:** approved for relevant scientific claims

### Preferred sources

- Peer-reviewed primary papers
- Systematic reviews
- Authoritative scientific reviews
- DOI/publisher pages
- Institutional repositories where legitimately available

### Good for

- Mechanisms
- Experimental measurements
- Structure-property relationships
- Validation of computational methods
- Scientific context

### Rule

Keep:
- DOI
- publication metadata
- source URL
- study type
- claim supported

Do not copy large copyrighted passages into LabelLens.

---

# 22. SOURCE: Government / Regulatory Standards

**Source ID:** `OFFICIAL_REGULATORY`  
**Class:** A  
**Status:** approved by jurisdiction and claim

Possible regulators include:
- FSSAI
- FDA
- European Commission / applicable EU authorities
- CDSCO
- other national authorities relevant to supported regions

### Rule

Regulatory source selection must be:

```text
claim
 +
jurisdiction
 +
date
 →
appropriate authority
```

Never use “global approval” as a generic category.

---

# 23. Source Types We Should NOT Trust Directly

### Discovery-only examples

```text
Random blogs
Health influencer pages
Reddit comments
Instagram/TikTok posts
AI-generated articles
SEO “chemical danger” lists
Random chemical websites
Unverified spreadsheets
Search snippets
Unsourced product databases
```

They may help discover a candidate, but important claims must be independently verified.

---

# 24. Source-Use Matrix

| Source | Identity | Chemistry | Product label | Food regulation | Cosmetics | Pharma | Discovery |
|---|---:|---:|---:|---:|---:|---:|---:|
| PubChem | ✅ | ✅ | ❌ | ❌ | ❌ | limited | ✅ |
| ChEBI | ✅ | ✅ | ❌ | ❌ | ❌ | limited | ✅ |
| NIST WebBook | ✅/support | ✅✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| RDKit | calculation | ✅✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| FSSAI | limited | ❌ | label rules | ✅✅ | limited | limited | ✅ |
| Codex GSFA | additives | ❌ | ❌ | ✅✅ | ❌ | ❌ | ✅ |
| EU Additives DB | additives | ❌ | ❌ | ✅✅ EU | ❌ | ❌ | ✅ |
| FDA food sources | additives | ❌ | ❌ | ✅✅ US | ❌ | ❌ | ✅ |
| CosIng | cosmetic names/functions | limited | ❌ | ❌ | ✅✅ EU context | ❌ | ✅ |
| Product/manufacturer label | ❌ general | ❌ general | ✅✅ | ❌ | ✅ product-specific | limited | ✅ |
| Open Food Facts | candidate | ❌ authority | ✅ candidate | ❌ | ❌ | ❌ | ✅✅ |
| Open Beauty Facts | candidate | ❌ authority | ✅ candidate | ❌ | ✅ candidate | ❌ | ✅ |
| PubMed / literature | identity support | ✅✅ | ❌ | scientific context | scientific context | scientific context | ✅ |

This table is a routing aid, not a substitute for field-level verification.

---

# 25. Source Selection by LabelLens Claim

## “What chemical is this?”

Preferred:
```text
PubChem
ChEBI
authoritative chemical reference
```

## “What is its molecular structure?”

Preferred:
```text
PubChem
ChEBI
then RDKit validation
```

## “What is its molecular weight?”

Preferred:
```text
authoritative chemical source
then deterministic calculation where appropriate
```

## “What role does it play in food?”

Preferred:
```text
product label
+
Codex/FSSAI/FDA/EU context where relevant
```

## “What role does it play in cosmetics?”

Preferred:
```text
product label
+
CosIng/other appropriate authoritative cosmetic sources
```

## “Is this allowed in India?”

Preferred:
```text
current FSSAI/CDSCO/official Indian regulatory material
```

## “Why is it used?”

Preferred:
```text
verified identity
+
domain role evidence
+
scientific literature when mechanism needs support
```

## “Is this product safer/healthier?”

This is NOT a default LabelLens claim.

Do not generate a universal safety/health ranking from ingredients alone.

---

# 26. Source Freshness Classes

Use:

```text
STATIC
STABLE
MODERATE
DYNAMIC
HIGHLY_DYNAMIC
```

### STATIC
Stable identifiers or historical metadata.

### STABLE
Fundamental chemical identity/structure information.

### MODERATE
Scientific reference records and classification information.

### DYNAMIC
Product labels, source APIs, current ingredient databases.

### HIGHLY_DYNAMIC
Regulations, amendments, current product formulation, pricing, platform limits.

Current claims must use current-source verification according to this class.

---

# 27. Source Verification Schedule

Recommended:

### Before first use
Verify:
- URL
- authority
- access method
- licensing
- data scope

### On every dynamic lookup
Verify:
- current record/version/date

### Before release
Re-check:
- regulatory sources
- external API documentation
- licensing
- major dataset versions

### On source changes
Create:
```text
SOURCE_CHANGE event
```

and update `SOURCE_REGISTRY.md`.

---

# 28. External API Rules

For every external API store:

```yaml
source_id:
api_base:
endpoint:
version:
authentication:
rate_limit:
terms_url:
license:
cache_policy:
data_scope:
error_behavior:
last_verified:
```

Do not hardcode assumptions about:
- quotas
- endpoint versions
- authentication
- pricing
- retention

without current official documentation.

---

# 29. Rate-Limit / Access Ethics

Even free APIs must be used responsibly.

### Rules
- Respect published rate limits.
- Cache repeated safe lookups.
- Use batch/bulk access only when permitted.
- Do not hammer public servers from multiple agents.
- Use identification headers/contact information when the source requests it.
- Prefer local datasets after licensed import.

NCBI's current policies ask scripts making large series of requests to follow published usage guidelines and avoid overloading NCBI systems. citeturn814714search0

---

# 30. Licensing Matrix

| Source | Initial LabelLens stance |
|---|---|
| PubChem | Free/programmatic access; inspect contributor/source licenses before bulk redistribution |
| ChEBI | CC BY 4.0 data; preserve attribution/terms |
| NIST SRD 69 | Conditional; do not bulk mirror by default |
| RDKit | BSD-3-Clause software |
| FSSAI | Use official regulatory documents for reference; do not assume all site material has identical reuse rights |
| Codex | Use official standards/database with proper attribution; verify reuse terms for redistribution |
| EU databases | Use as official references; verify current reuse/legal notices before bulk republishing |
| FDA | Official government information; check specific page/source notices |
| CosIng | Informational database; distinguish database information from legal authorization |
| Open Food Facts | ODbL/database-specific obligations; images have separate licensing |
| Open Beauty Facts | Verify current associated data/image licenses |
| Literature | Copyright varies; store metadata/claims, not large copyrighted passages |

**Rule:** “Free to access” does not automatically mean “free to redistribute.”

---

# 31. Source Adapter Architecture

All external sources must be isolated behind adapters.

```text
SourceRegistry
      ↓
ProviderAdapter
      ↓
raw response
      ↓
parser
      ↓
normalized candidate
      ↓
validation
      ↓
claim/evidence
```

Examples:

```text
providers/
  pubchem.py
  chebi.py
  fssai.py
  codex.py
  eu_additives.py
  cosing.py
  product_sources.py
```

Do not let source-specific logic leak throughout the application.

---

# 32. Source Provenance Capture

Whenever external data is imported, record:

```text
source_id
source_record_id
source_url
retrieved_at
source_version/date
field imported
original value
normalization applied
license note
verification status
```

Do not store only:

```text
source = PubChem
```

That is insufficient for auditability.

---

# 33. Golden Source Policy

For frequently used chemistry records, LabelLens may maintain a curated local golden dataset.

Each local record must retain:

```text
canonical value
source record
source URL/identifier
verification date
review status
license notes
```

A local golden value is a **curated snapshot**, not an independent source.

---

# 34. Source Conflict Policy

When sources disagree:

```text
1. Confirm same entity
2. Confirm same form/salt/isomer
3. Confirm same jurisdiction
4. Confirm same date/version
5. Apply claim-specific authority
6. If unresolved → conflicted
```

Never silently average or choose the value that makes the UI look nicer.

---

# 35. Product Label Evidence Priority

For the statement:

> “This exact product label contains ingredient X.”

Evidence priority:

```text
1. Captured current label image
2. Official product label/document
3. Manufacturer product page
4. Trusted product database
5. User-entered text
```

User-entered text is an observation, not independent product verification.

---

# 36. Chemical Identity Evidence Priority

For the statement:

> “This label term corresponds to chemical entity X.”

Evidence priority:

```text
1. Exact authoritative identifier
2. Authoritative database exact record
3. Strong alias mapping + authoritative source
4. Domain-aware candidate matching
5. AI candidate
```

AI candidate alone never reaches verified state.

---

# 37. Scientific Mechanism Evidence

For:

> “This chemical plays role X because mechanism Y...”

Use:

```text
chemical identity evidence
+
domain role evidence
+
scientific literature if mechanistic detail is claimed
```

Do not infer mechanisms from a chemical's name alone.

---

# 38. Regulatory Claims

For:

> “This ingredient is permitted/restricted in jurisdiction X.”

Require:

```text
jurisdiction
+
exact current regulatory source
+
effective/current status
+
relevant condition/category
```

Do not convert:

```text
found in database
```

into:

```text
legally approved
```

unless the database is specifically the appropriate legal source and the exact legal condition is verified.

---

# 39. Source Confidence vs Claim Confidence

Do not assign:

```text
PubChem = 100%
```

and then inherit that value to every claim.

Instead:

```text
source authority
+
claim-specific support
+
entity match
+
context
+
freshness
```

determine claim confidence.

---

# 40. Current Source Verification Record

At registry creation on 2026-10-04, the following were verified from official/current materials:

```text
PubChem PUG REST docs:
current documentation available; updated 2026-09-15.

PubChem downloads/provenance:
current documentation updated 2026-03-26.

ChEBI:
public REST APIs and current downloadable data; data licensing described as CC BY 4.0.

RDKit:
current documentation/repository confirms open-source BSD licensing.

FSSAI:
official product-standard/regulation and amendment pages are active; current notifications include 2026 materials.

Codex GSFA:
current online database is active and updated as provisions are adopted.

EU Food Additives Database:
current official database available.

CosIng:
current European Commission cosmetic ingredient database/glossary available; explicitly informational/non-binding.

NIST Chemistry WebBook:
current SRD 69 reference available; licensing is conditional due to Standard Reference Data rules.

Open Food Facts:
current API v3 documentation available; ODbL/data/image licensing and data-quality caveats documented.
```

This registry is a snapshot. Current source documentation must be rechecked when a source is used for a changing claim. citeturn895993search1turn867466search1turn867466search0turn896354search1turn867466search9turn296183search0turn895993search0turn895993search5turn775426search8turn590857search2

---

# 41. Free-First Data Strategy

The first release should minimize paid services.

Preferred order:

```text
1. Local verified golden dataset
2. Free/open authoritative APIs
3. Targeted public reference lookups
4. Local deterministic RDKit calculations
5. AI for candidates/explanations
6. Paid data only if a measured MVP gap justifies it
```

Do not make every scan dependent on a paid AI/API call.

---

# 42. Source Use in Development

OpenCode, Claude Code, Hermes, Gemini, or another agent must never add an external source merely because it appears useful.

Adding a source requires:

```text
source candidate
 ↓
source-registry review
 ↓
authority assessment
 ↓
license assessment
 ↓
claim types defined
 ↓
freshness class
 ↓
adapter if needed
 ↓
approved/conditional status
```

Record changes in `DECISIONS.md` / `CHANGELOG.md`.

---

# 43. AI Research Source Handling

AI research output is:

```text
DISCOVERY
```

until verified.

Example:

```text
Gemini finds source
       ↓
ChatGPT/agent opens source
       ↓
source evaluated
       ↓
source registry match
       ↓
claim extracted
       ↓
evidence stored
```

Never:

```text
Gemini answer
 ↓
verified database fact
```

---

# 44. Source Red Flags

Immediately downgrade/reject a source when it:

- has no identifiable publisher
- makes absolute safety claims
- provides chemical structures without provenance
- copies content without citations
- mixes jurisdictions
- has no update information for dynamic claims
- uses “natural = safe” or “chemical = dangerous” framing
- presents AI-generated claims as scientific facts
- hides source references behind unverifiable summaries

---

# 45. Source Registry Acceptance Criteria

The source registry is complete for MVP when:

1. Every trusted source has a unique source ID.
2. Each source has defined claim types.
3. Source authority is documented.
4. Licensing/reuse stance is recorded.
5. API/access method is known where applicable.
6. Freshness class exists.
7. Jurisdiction is recorded where relevant.
8. Conditional sources have explicit restrictions.
9. Discovery-only sources cannot become primary evidence automatically.
10. External AI output is never itself final evidence.
11. Source provenance is stored at claim level.
12. Regulatory sources are jurisdiction-specific.
13. Product labels are separated from general chemistry sources.
14. Computation sources/software are separated from evidence sources.
15. The registry supports a zero/low-cost MVP.
16. Source changes can be audited.

---

# 46. Default Source Routing

When the system needs data:

```text
CHEMICAL IDENTITY
→ PubChem / ChEBI
→ alternative authoritative source if unresolved

MOLECULAR COMPUTATION
→ RDKit

PHYSICAL/THERMOCHEMICAL REFERENCE
→ NIST WebBook (targeted/conditional)

INDIA FOOD REGULATION
→ FSSAI

INTERNATIONAL FOOD ADDITIVE CONTEXT
→ Codex GSFA

EU FOOD ADDITIVE CONTEXT
→ European Commission

US FOOD ADDITIVE CONTEXT
→ FDA

EU COSMETIC NOMENCLATURE/CONTEXT
→ CosIng

PRODUCT-SPECIFIC INGREDIENT LIST
→ actual label / manufacturer source

FOOD PRODUCT DISCOVERY
→ Open Food Facts (conditional/candidate)

COSMETIC PRODUCT DISCOVERY
→ Open Beauty Facts (conditional/candidate)

SCIENTIFIC MECHANISM
→ primary literature / PubMed discovery
```

For pharmaceutical labeling, keep implementation informational and jurisdiction-specific; use current official regulatory labeling sources only after a separate source review. Do not treat a general chemical database as a substitute for an official medicine label.

---

# 47. Final Source Principle

> **LabelLens should not ask “Which website has an answer?” It should ask “Which source is appropriate for this exact claim, entity, context, jurisdiction, and date?”**

That is the source-selection rule for the entire project.
