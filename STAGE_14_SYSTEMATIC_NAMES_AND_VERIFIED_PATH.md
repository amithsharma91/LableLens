# Stage 14 — Systematic Names, Identifier Fixture, Verified-Path Verdict

Date: 2026-10-05
Scope: four workstreams — independent review of the four Stage-13
fixtures, a syntactic fix for the systematic-name normalization gap,
one genuinely sourced identifier-bearing fixture, and an honest
verdict on the real-label VERIFIED path.

Verification rules V1–V7 are **unchanged**. No new route, no new
table, no new migration, no new provider, no RDKit, no AI, no
frontend, no role classification.

---

## 1. Workstream 1 — independent review of RL-13-01…04

Every fixture was re-checked against its fetched source record:

1. `source_reference` explicit (source id, class, description, URL,
   retrieval date, licence note where applicable) — yes, all four.
2. Source type correctly represented — DailyMed SPLs are class A
   for product presence; OFF OCR and INCIDecoder/retailer
   transcriptions are class C/secondary — yes.
3. Transcription traceable — all four raw texts verified
   byte-identical to their sources programmatically; ordering
   preserved (expected sequences rejoin to the raw text).
4. Correction separate from immutable raw — RL-13-02's correction
   cites both SPL readings; nothing else carries a correction.
5. Ordering preserved — sequences 0..n verified per fixture.
6. Actives/inactives scope correct — both SPL fixtures name the
   excluded actives in their scope notes.
7. Secondary marking — RL-13-01 (OCR) and RL-13-03
   (user-uploaded transcription) stay secondary/draft.
8. No unsupported manufacturer claim — fixtures assert only what
   the source prints.
9. No inferred chemistry — function-names, generics, and codes are
   never mapped to substances outside the registry.

Each fixture now carries an `independent_review` block (reviewer,
date, method, status, note, `chemistry_inferred: false`). RL-13-02
and RL-13-04 are `confirmed_official_source`; RL-13-01 and RL-13-03
are `confirmed_source_fidelity` / `confirmed_page_fidelity_secondary`.
`review_status` stays `draft` everywhere: a second human review is
still pending, and nothing was promoted.

## 2. Workstream 2 — systematic-name normalization fix

Defect path, confirmed by tracing (parser first, normalizer second):

1. `_split_top_level` split `propane-1,2,3-triol` on its locant
   commas into three segments — commas were treated as separators
   unconditionally.
2. `_TRAILING_ID_RE` (`^(head)(tag: INS|E + digits)$`, case
   insensitive, no boundary requirement) read the trailing `e-1` of
   `propane-1` as additive code E1 with name `propan` (likewise
   `Rinse 471` → E471). The normalizer then rendered `propan E 1`.

Fix (parser only, syntactic, no chemistry knowledge):

- A comma splits only when it is NOT directly between two digits
  with no whitespace (`1,2` is a numeric run — locants, decimals —
  not an item separator). Spaced commas and all semicolons still
  separate exactly as before.
- A trailing additive-code tag must start at a token boundary
  (`(?<![A-Za-z])`), so word-final `e` + digits is never a code
  while `Stabilizer INS471`, `Acid E 330`, and `X-E211` still match.

Result: `propane-1,2,3-triol`, `butane-1,4-diol`,
`2-methylpropane`, and `2-hydroxypropane-1,2,3-tricarboxylic acid`
parse to single nodes with intact names, no hallucinated
identifiers, and normalize byte-identically (lowercased). The fix
additionally unlocks the registered systematic-name aliases:
`propane-1,2,3-triol` now resolves `exact_alias` to glycerol and
`2-hydroxypropane-…` to citric acid; unregistered systematic names
(`butane-1,4-diol`) stay unresolved. OCR whitespace around hyphens
is preserved literally. Ten new unit tests pin locants,
hyphenation, the `Rinse 471` guard, nesting, real-code detection
and spacing, and unchanged Stage-13 segmentation. Full suite:
no regressions.

Deliberately out of scope: leading codes (`E330 Citric Acid`),
CI codes in trailing position (never supported), and the
pre-existing confidence downgrade that marks every node
`uncertain_parse_low` when any unbalanced-bracket limitation
exists — all recorded as known limitations.

## 3. Workstream 3 — identifier-bearing fixture RL-14-01

Frooti Mango Drink 1L (Parle Agro), Ingredients section of the
Quality Foods Online retailer page (SKU DR-23, UK Indian grocer),
transcribed verbatim including the page's own unbalanced
parenthesis (preserved literally, never repaired):

> Water, Mango Pulp (19%), Sugar, Acidity Regulator (INS 330),
> Permitted Class II Preservatives (INS 211, INS 224, INS 202),
> Antioxidant (INS 300), Contains Permitted Synthetic Food Colour
> (INS 110) and Added Flavor (Nature-Identical Flavoring Substances
> (Mango).

Marked secondary/draft (retailer transcription, not the
manufacturer or the physical pack); the FSSAI-style
function-plus-code wording is consistent with a genuine Indian
label. Seven top-level nodes; multi-code groups persist their INS
children in the parse tree only.

## 4. Workstream 4 — verified-path verdict: NOT MET, by design

`Acidity Regulator (INS 330)` resolves `exact_match` to
`CANON-2671a263ff76` (citric acid) — exact identifier resolution,
proven and persisted — but the decision is honestly **unverified**:
V3 FAIL (the function-name agrees with no record) and V4 FAIL
(identifier must belong to a name-agreeing record). The frozen
gate demands name+identifier dual agreement on one record
(ADR-020), and the review loop cannot waive it either: human
confirmation of a bare name yields provisional/MEDIUM at best,
because VERIFIED requires all seven gates PASS including V4.

No quotable English name+code co-printing (e.g. `Citric Acid
(E330)`) was found: EU/US/AU/IN labelling formats print a name OR
a code, never both (Brazil prints both, but in Portuguese, which
cannot agree with the English registry — and double-counting
PubChem against its own transcript as "two sources" was rejected
as verification theater). The verified path therefore remains
proven only on synthetic Stage-11/12 inputs. This is reported,
not masked: the regression asserts the unverified outcome, and
`verified` stays 0.

## 5. Metrics (deterministic, 5 labels)

```text
labels=5 ingredients=57 normalized=57
match: exact=5 alias=0 candidate=2 ambiguous=0 unresolved=50
verify: verified=0 provisional=4 unverified=1 conflicted=0 unknown=52
false_positives=0 unknown=52 coverage=0.5714 mismatches=0
```

## 6. Verification performed

- `pytest app/tests`: **442 passed, 44 skipped** offline;
  **486 passed** live (471 Stage-13 + 15 new, 0 failed).
- `flake8 app --max-line-length=88`: clean.
  `python -m compileall -q app`: clean. `git diff --check`: clean.
- `python -m app.cli.run_label_regression`: `REGRESSION PASSED`
  (5 labels, 0 mismatches, exit 0).
- New tests: 10 systematic-name unit + 4 regression (RL-14-01
  slice, identifier-without-verification, nested INS tree,
  typo preservation) + 1 live identifier test.

## 7. Boundaries held

V1–V7 unchanged. No RDKit. No AI. No frontend. No role
classification. No new chemistry providers. No public
entity-import endpoint. No fabricated chemistry. No placeholder
fixture promoted to truth. No PubChem/transcript double-counting.
No structures forced onto mixtures, colors, flavors, generics,
or function-names.
