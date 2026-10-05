# Stage 13 — Real-Label Deterministic Vertical Slice

Date: 2026-10-05
Scope: the first real-label → deterministic LabelLens pipeline end to
end, over four genuinely sourced product labels. Verification rules
V1–V7 are **unchanged** (`VERIFICATION_RULES_VERSION = "1.0.0"`). No
new route, no new table, no new migration, no parser/normalizer
behavior change.

---

## 1. Dataset reality (no false gold)

`LABEL_REGRESSION_DATASET.csv`: **30 records, 30 placeholders, 0
usable** — every row has `review_status = needs_real_label` with
empty brand, text, and expectation columns. None was populated, and
none is referenced by this stage.

`INGREDIENT_GOLDEN_DATA.csv`: **100 records, 100 candidate seeds, 0
verified** — every row has `review_status = needs_verification`
with the explicit note "Candidate seed only. Do not treat any
populated hint as verified scientific fact." None was promoted.

Both files are byte-unchanged by this stage, enforced by a test
(`test_regression_datasets_still_hold_no_verified_truth`) that fails
if anyone marks a placeholder verified to make tests pass.

The four Stage-13 fixtures live separately at
`backend/app/regression/fixtures/real_labels/RL-13-0{1,2,3,4}.json`
with `review_status = "draft"` — sourced and transcribed, not yet
independently reviewed. Draft is stated, never upgraded silently.

## 2. Selected labels (all real, all cited)

| ID | Product | Domain | Source | Retrieved |
|---|---|---|---|---|
| RL-13-01 | Coca-Cola Original Taste Soda | beverage | Open Food Facts record 049000028904 (English OCR text as stored) | 2026-10-05 |
| RL-13-02 | Listerine Cool Mint Antiseptic Mouthwash (Kenvue) | personal care | FDA DailyMed SPL setId `edb9e374-…a3da5`, v7, effective 2025-03-03, Inactive-ingredients paragraph | 2026-10-05 |
| RL-13-03 | Nivea Creme (Beiersdorf) | cosmetic | INCIDecoder product page (user-uploaded 2018-02-24; marked as secondary transcription, not manufacturer-verified) | 2026-10-05 |
| RL-13-04 | Vicks NyQuil Cold & Flu liquid (P&G) | OTC drug | FDA DailyMed SPL setId `fc9e05a5-…0d58`, v10, effective 2026-06-23, Inactive-ingredients paragraph | 2026-10-05 |

Raw texts are transcribed verbatim into the fixtures (including the
Coca-Cola OCR garbling). Scope notes record what is *not* covered:
the two SPL fixtures cover the inactive-ingredients paragraph only
(actives are named in the same SPLs and excluded by scope, not by
oversight); Nivea's nested `Eucerit` sub-ingredient stays in the
parse tree (per-node persistence below top level is deferred since
Stage 11).

## 3. Pipeline stages executed (existing code, unchanged rules)

Per label: `LabelInput` → `ObservationService.create` (parse +
persist one observation per top-level node) → `correct` (RL-13-02
only, documented case) → `analyze` per observation (normalize +
resolve + verify + persist) → fixture comparison → metrics.

## 4. Outcomes per label

- **RL-13-01 (6 ingredients):** poor OCR preserved verbatim; all 6
  unresolved/unknown; nothing verified, nothing invented.
- **RL-13-02 (9):** `sodium benzoate` exact match → provisional;
  `Alcohol (21.6%)` unresolved (generic term + percentage, never
  mapped to ethanol); `Flavor`, `Green 3`, `Benzoic Acid` (a
  different substance from sodium benzoate), and the rest unresolved.
  Documented correction `Saccharin Sodium` → `Sodium Saccharin`
  (structured SPL element name vs printed panel reading, both cited);
  raw immutable, correction separately stored, re-normalization on
  the corrected text, outcome unchanged (unknown).
- **RL-13-03 (21):** `Citric Acid` exact match → provisional;
  `Glycerin` stays an unselected candidate (common synonym of
  glycerol, absent from the approved names — not promoted);
  `Benzyl Benzoate` near-miss guard holds (no resolution);
  `Parfum` unresolved; 19 others unknown.
- **RL-13-04 (14):** `citric acid` + `sodium benzoate` exact matches
  → provisional with entity-linked claims and evidence;
  `glycerin` candidate/unknown; `alcohol`, `flavor`, FD&C colors and
  the rest unknown.

Bare registered names verify only to **provisional** (V3: a single
source cannot corroborate itself). Nothing in the slice reaches
`verified` — forcing it would require identifier-bearing label text
the sourced labels do not print. No fixture warrants `conflicted`;
none is manufactured.

## 5. Metrics (deterministic)

```text
labels=4 ingredients=50 normalized=50
match: exact=4 alias=0 candidate=2 ambiguous=0 unresolved=44
verify: verified=0 provisional=4 unverified=0 conflicted=0 unknown=46
false_positives=0 unknown=46 coverage=0.6667 mismatches=0
```

`coverage` = (verified + provisional) / resolved ingredients
(4/6). `false_positives` = unknown-expected ingredients that
received an entity (0; nonzero fails the run). Not claimed:
representativeness of any market, or "AI accuracy".

## 6. Provenance (one complete trace, RL-13-04 citric acid)

`RL-13-04` → observation `…` (sequence 1, raw `citric acid`) →
normalization `citric acid` → candidate `CANON-2671a263ff76`
(exact_normalized_name) → `chemical_entities`
`2671a263-…` (citric acid, single_molecule) → verification decision
(provisional, rules 1.0.0, snapshot canonical_v1, all seven gate
results recorded) → claim (identity, provisional, LOW,
`chemical_entity_id = 2671a263-…`) → claim_source → source
(PUBCHEM class A). Every id in the chain is real and persisted;
verified in both backends by `test_full_provenance_chain…` and the
live persisted-rows test.

## 7. What was NOT changed, and known limitations

- V1–V7, parser, normalizer, resolver, adapters, registry import:
  untouched. Two pre-existing behaviors were observed and left
  alone: systematic IUPAC-style names with numeric locants are
  mangled by the Stage-4 normalizer (`propane-1,2,3-triol` →
  `propan E 1`), so they cannot resolve; and `verification_events`
  rows are written only on claim state change, not per analysis.
  Both are recorded here as known limitations, not fixed under a
  regression stage (Stage-14 candidates).
- `conflicted` never occurs in the slice (nothing warrants it).
- Alias matches are 0: no fixture ingredient uses a registered alias
  that survives normalization.
- Fixtures are `draft`: a second human review is still pending.
- The in-memory limiter, single-process scope, RLS gaps, and all
  other Stage-12 limitations carry over unchanged.

## 8. Files added

- `backend/app/regression/label_input.py` — `LabelInput`
  (label_id, raw_text, input_method, source_reference), strict
  validation, deterministic scan/observation ids, unknown keys
  refused.
- `backend/app/regression/runner.py` — `run_label` (create →
  correct → analyze → compare → provenance).
- `backend/app/regression/metrics.py` — `summarize`/`render`.
- `backend/app/regression/fixtures/real_labels/RL-13-0{1..4}.json`
- `backend/app/cli/run_label_regression.py` — developer-only
  command, exit non-zero on mismatch, no HTTP endpoint.
- Tests: `app/tests/regression/test_real_label_regression.py`
  (19), `test_real_label_security.py` (3),
  `test_real_label_postgres.py` (5, live).

## 9. Service-layer additions (additive only)

- `ObservationService.correct`: one documented revision per
  observation; raw immutable (`original_text` set once),
  `display_text`/`user_corrected`/`correction_reason`/
  `user_corrected` source type stored; fresh normalization row for
  the corrected text; second correction refused.
- `analyze`/`get` run on `display_text or raw_text`; reads expose
  the correction fields.
- `MatchRepository.get_observation` + `record_correction`
  (protocol, memory, Postgres).
- `get_normalization_for_observation` returns the *latest* row
  (identical for the single-row case everywhere else).
- Stable ids: caller-supplied `observation_ids`, uuid5
  normalization ids over observation + content, so reruns reuse
  rows instead of duplicating them.

## 10. Verification performed

- `pytest app/tests`: **428 passed, 43 skipped** offline;
  **471 passed** live (444 Stage-12 + 27 new, 0 failed).
- `flake8 app --max-line-length=88`: clean.
  `python -m compileall -q app`: clean. `git diff --check`: clean.
- `python -m app.cli.run_label_regression`: `REGRESSION PASSED`
  (output in the Stage-13 report §20).
- Fresh-database import path untouched and still green via the
  Stage-12 live tests in the same runs.

## 11. Boundaries held

V1–V7 unchanged. No RDKit. No AI. No frontend. No role
classification. No new chemistry providers. No public
entity-import endpoint. No fabricated chemistry. No placeholder
fixture promoted to truth.
