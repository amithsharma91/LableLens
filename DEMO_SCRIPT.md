# LabelLens — Live Demo Script

**Document:** DEMO_SCRIPT.md  
**Project:** LabelLens  
**Date:** 2026-10-04  
**Purpose:** Step-by-step presenter script for the final live demo  
**Total runtime target:** ~10–12 minutes

---

## Pre-Demo Checklist

Run through this before the presentation starts.

**Device & environment**
- [ ] Phone charged, screen brightness at max
- [ ] Mirror/cast to display confirmed and working
- [ ] App open and on the Home screen (not mid-session)
- [ ] Wi-Fi confirmed working
- [ ] Three physical labels ready: food, cosmetics/personal care, household
- [ ] Fallback ingredient text copied to clipboard (see Fallback Plan below)

**Data state**
- [ ] Product A (food label) pre-loaded or ready to scan fresh
- [ ] Product B (cosmetics/personal care label) ready for compare step
- [ ] One household label ready as domain-variety flash
- [ ] At least one ingredient in the dataset is `unknown` / unverified — confirm this beforehand

**Demo ingredients pre-verified in database (fallback set)**
- Sodium Benzoate — food preservative, single molecule, clear structure ✓
- Citric Acid — food/cosmetic, single molecule, common ✓
- Lecithin — food emulsifier, mixture, "not applicable" for structure ✓
- Fragrance/Parfum — cosmetic, trade term, mixture, `unknown` demo ✓
- Sodium Lauryl Sulfate — personal care surfactant, salt ✓

---

## Section 1 — Open and Orient (1 min)

**ACTION:** Show the Home screen of LabelLens on the cast display.

> "This is LabelLens. The core idea is simple: you point it at a product label, and it turns the ingredient list into understandable chemical information — with the evidence for every claim visible underneath."

**ACTION:** Briefly point to the four home options: Scan a Label, Search Ingredient, Compare Products, Recent Scans.

> "The primary action is scanning. Everything else flows from that."

---

## Section 2 — Scan a Real Label (1.5 min)

**ACTION:** Pick up the food label (e.g. a snack or beverage). Hold it steady and tap **Scan a Label**.

> "I'm scanning a real label — nothing pre-loaded."

**ACTION:** Let the camera preview appear. Frame the ingredients panel and capture.

> "The app sends the image through OCR. You'll see the raw recognized text in a moment."

**ACTION:** OCR result appears. Show the extracted text screen.

> "Here's what the OCR picked up. It's pretty clean, but — notice this entry here."

**ACTION:** Point to the OCR error (e.g. "Sodiurn Benzoate" misread as that, or a similar character-swap error).

> "Notice the OCR picked up a typo here — 'Sodiurn' instead of 'Sodium'. I can correct it before analysis. The system doesn't silently fix this and pretend the original image was clean."

**ACTION:** Tap the incorrect token. Edit it inline. Confirm.

> "The correction is recorded separately from the original OCR — so the audit trail stays intact."

**— BACKUP if OCR fails on this label →** go to Backup Plan A below before continuing.

---

## Section 3 — Analyze (1 min)

**ACTION:** Tap **Analyze** (or equivalent confirm/proceed button).

> "Now it runs the full pipeline — normalization, entity resolution, chemical lookup, role classification."

**ACTION:** Watch the progress indicator. Let the analysis result screen load.

> "Each ingredient goes through its own resolution path. They don't all succeed equally — and that's intentional."

**ACTION:** Show the ingredient list with confidence states visible.

> "Each ingredient shows its confidence level separately. OCR confidence, identity confidence, role confidence — these are different questions and the system tracks them independently."

---

## Section 4 — Open an Ingredient Detail (1.5 min)

**ACTION:** Tap on a well-verified single-molecule ingredient — ideally **Sodium Benzoate** or **Citric Acid**.

> "Let's open this one. It resolved to a verified entity."

**ACTION:** Show the ingredient detail card: name, formula, molecular weight, structure rendering, CAS number.

> "Formula, molecular weight, CAS, SMILES — all pulled from an authoritative source and validated."

**ACTION:** Scroll to the structure viewer. Show the 2D structure rendered.

> "The structure renders because this is a well-defined single molecule. The system only renders a structure when one actually makes sense."

**ACTION:** Now scroll back up, go back to the ingredient list, and tap on **Lecithin** (or whichever mixture ingredient is present).

> "Now compare that to this one — Lecithin. It's a mixture of phospholipids."

**ACTION:** Show the ingredient detail for Lecithin. Structure section shows 'Not applicable' or equivalent.

> "This is a mixture — no single molecular structure is appropriate, and the system correctly shows that. It doesn't invent a structure to fill the space."

---

## Section 5 — 'Why Is This Here?' (1.5 min)

**ACTION:** Go back to a well-verified ingredient. Tap **'Why is this here?'**.

> "This is the explanation layer."

**ACTION:** Let the explanation text load.

> "The explanation is grounded in structured facts — not a free-form AI answer. The system was told: use only the verified evidence we have. If something is unknown, say so."

**ACTION:** Point to the role/function section.

> "It tells you what the ingredient does in this product domain — preservative, emulsifier, surfactant, whatever applies. The role is classified per domain, because the same chemical can play a different role in food versus personal care."

---

## Section 6 — Open Evidence (1 min)

**ACTION:** Tap the evidence/source link or provenance button on the ingredient detail.

> "Here's the evidence for this claim — it comes from PubChem, FSSAI, or Codex, depending on the claim type."

**ACTION:** Show the source record: source name, evidence type, verification status, last checked date.

> "Each factual claim has a traceable source. You can see what the source is, when it was checked, and how strong the support is."

**ACTION:** Scroll to show a field with MEDIUM or lower confidence if one exists.

> "Some fields are well-verified. Others are contextual — and the system shows that distinction rather than collapsing everything into a single score."

---

## Section 7 — Compare Products (2 min)

**ACTION:** Navigate to **Compare Products**. Select the food label you just analyzed as Product A.

> "Now I'll compare this product to a second one."

**ACTION:** Scan or load the cosmetics/personal care label as Product B. Let it analyze.

> "These are different product domains — food versus personal care. The same ingredient can appear in both, but with a different role."

**ACTION:** Show the comparison view with shared ingredients highlighted and domain differences visible.

> "Shared ingredients — and ingredients unique to each. Compare Product A and B: shared ingredients here, and ingredients unique to each over here."

**ACTION:** Point to a role difference if one is visible (e.g. Citric Acid as preservative/pH adjuster in food vs. chelating agent in cosmetics).

> "Same chemical, different context, different role. The system uses domain-appropriate role evidence rather than one generic label."

**ACTION:** Briefly hold up the household label.

> "I could add a third label here — this is a household product. LabelLens covers food, cosmetics, personal care, household — the core chemistry engine is shared, the domain interpretation layer is different."

---

## Section 8 — The Unknown Case (1.5 min)

**ACTION:** From the cosmetics analysis (Product B), scroll to find **Fragrance** or **Parfum**, or any ingredient marked as `unknown` / unverified.

> "Here's the one I want to highlight."

**ACTION:** Tap on the unknown ingredient. Show its detail card — no formula, no structure, status marked explicitly as unknown or not verified.

> "This ingredient is unknown — the system doesn't guess. It doesn't generate a plausible-looking formula. It tells you honestly that it couldn't find a sufficiently reliable chemical match."

**ACTION:** Point to the status indicator.

> "'Fragrance' is a trade term. It legally covers a blend of potentially hundreds of compounds — there is no single verified chemical identity we can attach to it, and the system is correct to leave it here."

**ACTION:** Pause slightly for emphasis.

> "This is a deliberate design choice. LabelLens prefers honest uncertainty over confident hallucination. A narrower verified answer is more useful than a broader invented one."

---

## Section 9 — Close (30 sec)

**ACTION:** Navigate back to the Home screen.

> "So the full flow: scan a real label, see OCR with corrections, run analysis with per-ingredient confidence, inspect chemistry and evidence, ask why an ingredient is present, compare products, and see exactly where the system knows something versus where it doesn't."

> "The architecture behind this is OCR → normalization → entity resolution → verified chemical data → domain role classification → evidence provenance → explainable AI. The evidence layer is not a UI feature — it's part of the core data model."

**ACTION:** Hold up all three labels briefly.

> "Three domains, one engine, evidence visible throughout."

---

## Backup Plan A — OCR Fails on Scan

**Trigger:** Camera scan produces garbled text, unusable output, or app error.

**ACTION:** Stay calm. Tap back to Home.

**SAY:**
> "The OCR failed on this image — lighting conditions can affect recognition quality. I can manually paste the ingredient list and continue the analysis from that point."

**ACTION:** Navigate to manual entry / paste flow. Paste the fallback text from clipboard:

```
Ingredients: Water, Sugar, Citric Acid, Sodium Benzoate, Lecithin, Flavour
```

**ACTION:** Continue from Section 3 (Analyze) as normal. The demo proceeds identically from this point.

---

## Backup Plan B — Specific Ingredient Not in Dataset

**Trigger:** A key ingredient (e.g. Lecithin, Fragrance) is missing from the live dataset and returns `not found` when you need it for a demo beat.

**ACTION:** Switch to searching the ingredient directly.

**SAY:**
> "Let me pull this ingredient up directly via search."

**ACTION:** Navigate to **Search Ingredient**. Type the fallback ingredient name (e.g. "Lecithin" or "Fragrance").

**ACTION:** Continue the relevant section beat from the search result detail view instead of from the scan analysis. The talking points remain identical.

---

## Backup Plan C — Compare View Fails / Crashes

**Trigger:** Compare Products crashes or produces no useful output.

**ACTION:** Stay on the single-product analysis view.

**SAY:**
> "The compare view had an issue — I'll walk through the comparison conceptually here. The key point is that the same chemical can appear in a food label as a preservative and in a cosmetics formula as a pH adjuster. LabelLens uses domain-specific role evidence rather than a single generic classification."

**ACTION:** Show two separate ingredient detail screens side by side (or sequentially) to illustrate the domain-role difference.

---

## Things to Never Say During the Demo

| ❌ Don't say | ✅ Why |
|---|---|
| "This ingredient is safe / unsafe" | LabelLens does not make safety verdicts |
| "This ingredient is healthy / unhealthy" | Same — out of scope by design |
| "The AI is 95% confident" | Confidence is multi-dimensional; no single score |
| "This is definitely X" (for a candidate) | Candidates are not verified facts |
| "Here's the structure for Fragrance" | Mixture — no valid single structure |
| "Approved everywhere" | Regulatory data is jurisdiction-specific |

---

## Quick Reference — Talking Points by Beat

| Beat | Core line |
|---|---|
| OCR correction | "Notice the OCR picked up a typo here — I can correct it before analysis" |
| Per-ingredient confidence | "Each ingredient shows its confidence level separately" |
| Mixture / no structure | "This is a mixture — no single molecular structure is appropriate, and the system correctly shows that" |
| Evidence source | "Here's the evidence — it comes from PubChem / FSSAI / Codex" |
| Unknown ingredient | "This ingredient is unknown — the system doesn't guess, it tells you honestly" |
| Compare | "Compare Product A and B — shared ingredients, and ingredients unique to each" |

---

## Fallback Ingredient Reference

If the live label scan fails completely, use these ingredients for manual entry. Each is pre-verified in the dataset and covers a different demo beat.

| Ingredient | Domain | Type | Demo beat |
|---|---|---|---|
| Sodium Benzoate | Food | Salt / single entity | Clean verified structure, clear role |
| Citric Acid | Food / Cosmetic | Single molecule | Domain-role difference (food vs cosmetic) |
| Lecithin | Food | Mixture | 'Not applicable' for structure |
| Fragrance / Parfum | Cosmetic | Trade term / mixture | Unknown / unverified case |
| Sodium Lauryl Sulfate | Personal care | Salt / surfactant | Personal care domain, clear chemistry |

---

*End of DEMO_SCRIPT.md*
