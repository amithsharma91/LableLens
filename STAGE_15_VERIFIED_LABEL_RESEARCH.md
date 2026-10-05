# Stage 15 — Verified-Label Research Report

Date: 2026-10-05
Status: **VERIFIED CANDIDATE FOUND** (Simple Linctus Sugar Free,
UK SmPC) — see §10.

This report records the search before any implementation, per the
Stage-15 mission. Rejected candidates are results, not failures.

---

## 1. Search scope

Target: a real product label printing an ingredient NAME together
with an IDENTIFIER from the canonical registry (`E330`/`INS330`,
`E211`/`INS211`, `E422`/`INS422`) in a language the frozen V3 name
rules can genuinely match (registry names are English/Latin
systematic). Searched: manufacturer ingredient pages (Coca-Cola
GB/UAE/ZA/IN, PepsiCo, Haribo US, Parle Agro, Rubicon/Torani via
retailers, Nivea/Beiersdorf via INCIDecoder), regulators and
label databases (FDA DailyMed SPLs, UK emc SmPCs, Open Food Facts
product API), retailers (Tesco, BigBasket, JioMart, Woolworths AU,
Checkers, Chemist Warehouse, Flipkart, Amazon.in snippets),
label-photo pools (Wikimedia Commons), B2B/encyclopedia pages, and
web search for exact name+code co-printings across EU/US/AU/IN/BR
label conventions.

## 2. Candidate sources considered

Coca-Cola GB Fanta/Sprite pages; Coca-Cola UAE Fanta pages;
Coca-Cola ZA Sprite page; Haribo US Goldbears + OFF Haribo
Roulette record; OFF Coca-Cola records (ES garbled OCR, US);
Listerine + NyQuil DailyMed SPLs; Nivea INCIDecoder page;
Calpol/Gaviscon/Nurofen emc SmPCs; Frooti retailer page;
Frutty/Brazilian manufacturer pages; Torani/Rubicon retailer
transcriptions; Flavor Burst B2B PDF; AVO-Werke B2B powder;
Parle Agro/Dabur/Amul/Britannia brand sites; ean-search;
upcitemdb-style lookups; Tesco/Boots/emc search pages.

## 3. Rejected candidates

| # | Candidate | Exact reason for rejection |
|---|---|---|
| 1 | Coca-Cola GB Fanta Orange (`Acids (Citric Acid, Malic Acid)`) | Names only, no identifier → provisional at best |
| 2 | Coca-Cola UAE Fanta Strawberry (`Preservative: Sodium Benzoate`) | Name only → provisional at best |
| 3 | Coca-Cola ZA Sprite (`Preservative (Sodium benzoate)`) | Name only → provisional at best |
| 4 | Haribo US Goldbears / OFF Roulette (`acidifier: citric acid`) | Name only → provisional at best |
| 5 | Listerine + NyQuil SPL inactives | US labels never print E-numbers; best outcome already provisional |
| 6 | Nivea Creme INCI | Cosmetics never print E-numbers |
| 7 | Calpol emc 260 §6.1 (`Glycerol` bare, parabens with E-numbers) | E-numbers present only on unregistered entities; glycerol has no code → provisional |
| 8 | Gaviscon emc 113 §6.1 (`Methyl parahydroxybenzoate E218` …) | Name+code pattern exists but on unregistered entities; zero registered matches |
| 9 | Nurofen Orange Singles emc 5641 §6.1 (`Citric acid`, `Glycerin` bare) | Names only → provisional/candidate |
| 10 | Frooti retailer page (`Acidity Regulator (INS 330)`, `INS 211` group) | Implemented as RL-14-01: identifier resolves exactly, but function-names agree with no record → honestly unverified under frozen V3/V4 |
| 11 | Frutty/Quinari manufacturer pages (`ácido cítrico (INS 330)`, `benzoato de sódio (INS 211)`) | Name+code co-printed, but Portuguese names cannot agree with the English registry under frozen V3; using them would require translation machinery (refused) |
| 12 | Flavor Burst B2B PDF (`E330 Citric Acid`) | Code-first ordering (unsupported, out of scope) and a B2B formulation sheet, not a consumer product label |
| 13 | AVO-Werke powder (`E 330 Citronensäure`) | Code-first German B2B ingredient; same two disqualifiers |
| 14 | Encyclopedias, Grokipedia, Wikipedia Solo, e-additive sites | Not labels; `E330 = citric acid` in a database never proves a particular pack's code |
| 15 | Retail search/discovery paths (Tesco, BigBasket, OFF search/facets, etc.) | Bot-walled, JS-only, or blocked; no quotable text obtained |
| 16 | Commons label photos | Not machine-readable here; transcribing an image I cannot verify would be fabrication |
| 17 | PubChem called twice (snapshot + live) as "two records" | Rejected as verification theater: the transcript IS PubChem; two records, one source, zero new corroboration |
| 18 | Human review confirming a bare name | Tested against the frozen gate: yields provisional/MEDIUM at best (V4 UNKNOWN blocks VERIFIED). Reviewers may not waive V3/V4 |

## 4. Why most candidates fail (structural finding)

Food-labelling formats print a name XOR a number, never both: EU/FIC
(`acid: citric acid` or `acid: E330`), US/Canada (names),
Australia/NZ (name or number), India (function + number, never the
substance name), UK pharma usually names. Brazil prints both but in
Portuguese. Name+code co-printing in quotable English text is rare
because it is redundant under every major format — which is why UK
SmPC excipient lists (which print `Name (EXXX)` for known-effect
excipients) were the productive source.

## 5. Best candidate

**Simple Linctus Sugar Free**, oral solution — UK Summary of
Product Characteristics, emc product 4928, print-friendly SmPC:

- MA holder: L.C.M. Ltd, Linthwaite Laboratories, Huddersfield
  HD7 5QH. MA number PL 12965/0050, first authorised 02/07/2010.
- Contact: Thornton & Ross Ltd. SmPC revised 06/11/2020, published
  on emc 16-Nov-2020 (page header: "Updated 16-Nov-2020").
- URL:
  `https://www.medicines.org.uk/emc/product/4928/smpc/print`
- Retrieved: 2026-10-05. Source type: official regulatory label
  database (primary for product presence; class A equivalent —
  the regulated label text itself, not a transcription).
- Language: English. Scope: §6.1 List of excipients (the label's
  own enumeration; §2 active line documented as out of scope,
  consistent with the Stage-13 SPL fixtures).

## 6. Exact label text (§6.1)

> Aniseed Flavour (contains propylene glycol) PHL-090803,
> Glycerol (E422), Liquid Maltitol (E965) (contains Sorbitol),
> Sodium Benzoate (E211), Purified water

Five top-level nodes. (The §2 active line reads `Citric acid
monohydrate (E330) 125mg per 5ml` — excluded by scope: the
hydrate-qualified name does not match any registry name, and
fixture scope is the excipient enumeration. Documented, not
hidden.)

## 7. Exact identifier/name relationship

- `Glycerol (E422)`: name `Glycerol` == registry preferred name
  `Glycerol` (case-insensitive); identifier `E422` == registry
  identifier `E422` on the SAME record (`763389d0-…`). Dual
  agreement on one record.
- `Sodium Benzoate (E211)`: name `Sodium Benzoate` == registry
  preferred name; identifier `E211` == registry identifier
  `E211` on the SAME record (`6223de87-…`). Dual agreement.
- `Aniseed Flavour … PHL-090803`, `Liquid Maltitol (E965) …`,
  `Purified water`: no registry name or identifier → unresolved.

## 8. Authoritative corroboration

- Product presence: the regulated SmPC itself (MA number,
  holder, revision date above).
- Identity evidence: PubChem class-A records via the approved
  snapshot (`canonical_v1`, rules `1.0.0`): citric-lineage record
  for glycerol (CID 753, InChIKey `PEDCQBHIVMGVHV-UHFFFAOYSA-N`,
  identifiers E422/INS422) and sodium benzoate (CID 517055,
  InChIKey `WXMKPNITSTVMEF-UHFFFAOYSA-M`, identifiers E211/INS211).
- The label establishes the name↔code relationship on the pack
  (both printed together); the registry+evidence establish what
  that relationship denotes. Neither side alone would suffice,
  and neither is asked to.

## 9. V1–V7 analysis (probed 2026-10-05, frozen gate)

`Glycerol (E422)` → exact_match → VERIFIED/HIGH:
V1 PASS (exact_match) · V2 PASS (1 record) · V3 PASS (name
agreement with corroboration — dual) · V4 PASS (identifier agrees
with source record) · V5 PASS (single_molecule) · V6 PASS ·
V7 PASS. Claims: identity, formula, inchi, inchikey,
molecular_weight, smiles — all verified/HIGH, entity-linked
(`763389d0-…`), one evidence link each.

`Sodium Benzoate (E211)` → exact_match → VERIFIED/HIGH: same
seven PASSes (V5: salt — representation preserved, not forced to
single_molecule). Same six verified claim types, entity-linked
(`6223de87-…`), evidenced.

Remaining three nodes → unresolved/unknown, entity null. No
conflict, no fabrication, no human waiver involved.

## 10. Decision: VERIFIED

Both ingredients satisfy every applicable gate from the printed
label plus registry plus authoritative evidence, through the
unchanged pipeline. Proceed to Phase C (RL-15-01) and Phase D
(persisted proof), with the three unresolved nodes asserting the
negative space.

## 11. Remaining evidence gaps

- The SmPC is the regulated text, not a photograph of the carton;
  the pack image itself was not captured (accepted: emc is the
  authoritative channel for UK label text, with MA number and
  revision date).
- `Citric acid monohydrate (E330)` in §2 is deliberately out of
  scope (hydrate-qualified name matches no registry name); a
  future canonical record for the monohydrate form would need its
  own approved registration, not a fixture-side alias.
- Secondary corroboration of the *pack* (retailer transcription)
  was not sought: the SmPC is primary and sufficient.
