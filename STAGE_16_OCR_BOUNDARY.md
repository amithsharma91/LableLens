# Stage 16 — OCR Boundary

Date: 2026-10-05
Scope: a deterministic backend boundary for image/document → OCR
result → immutable raw OCR → human correction → the existing
parser/normalizer/resolver/verification pipeline. OCR can now enter
the system without contaminating the verified data model.

Verification rules V1–V7 are **unchanged**. No new route for
chemistry, no new table for rate limits, no new provider, no RDKit,
no AI, no frontend, no role classification, no resolver ranking
change, no verification-rule change.

---

## 1. OCR contract (`app/services/ocr_provider.py`)

`OCRResult` (frozen dataclass): `document_id`, `provider`,
`raw_text`, optional `provider_version`, optional
`ocr_confidence` (number in [0, 1]; NaN/bools/out-of-range
refused), optional `page_metadata` / `source_reference` mappings.
Empty `raw_text` is representable — empty OCR is a handled failure
mode, not a validation error. No normalized identity, no entity,
no chemistry, no evidence fields exist on the record by
construction.

`OCRDocument` carries a document reference (id + optional locator),
never image bytes: no image data is stored or transmitted anywhere
in this boundary.

`OCRProvider` is a one-method async protocol
(`extract(document) -> OCRResult`). `ProviderFailure` is raised
before any write, so a failing provider leaves no partial rows.
Only `FakeOCRProvider` ships: a deterministic document-id →
canned-result map with registered failures, which re-labels
results to the actually-extracting provider. No vendor SDK is
imported; no provider secret is accepted, stored, or returned.
(`DEVELOPMENT_GUIDE.md` sketches future Tesseract/Vision env
wiring; Stage 16 deliberately does not bind to it — provider
selection stays outside the domain until a vendor is approved.)

## 2. Persistence (migration `004_ocr_boundary.sql`)

- `ocr_runs`: one immutable row per extraction (document, provider,
  version, raw text, confidence, page/source metadata, created_at).
  Reruns insert new rows; nothing updates a run.
- `ocr_corrections`: one revision per run (`UNIQUE(ocr_run_id)`,
  refused again in the service layer). Append-only like everything
  else; the API never updates or deletes.
- `ingredient_observations.ocr_run_id` / `.ocr_confidence`
  (pre-existing columns from migration 003, previously unwritten)
  now link derived observations to their run.
- RLS mirrors migration 003: service-role writes, authenticated
  SELECT, no per-user row policies — the same deferred posture as
  the Stage-10 tables (no `user_id` exists anywhere yet). The gap
  is documented here and in `SECURITY.md`, not hidden, and no
  global data model was silently introduced: reads require
  authentication on every OCR route.
- `test_migration.py` now validates migrations 003+004 together;
  all live-test reset helpers apply 004.

## 3. Correction model (`OCRService.correct_run` + observation `correct`)

Two consistent layers, same single-revision rule:

- Run level: raw OCR text immutable; the corrected full text is a
  separate row with reason and `human:{subject}` actor. A second
  correction is refused (DB unique constraint + service refusal).
- Observation level (Stage 13, reused unchanged): raw segment
  immutable, `display_text` + reason stored, fresh normalization
  row, second correction refused.
- Observing a corrected run derives NEW observations (ids keyed
  `run + corrected + sequence`) from the corrected text; the
  raw-derived observations stay intact. Both generations link to
  the run, so raw → correction → observations reconstructs fully.

## 4. Pipeline integration (`OCRService.observe` / `analyze_run`)

Effective text = corrected text when a correction exists, else raw
text → `ObservationService.create` (Stage 2/4 inside, parser
semantics untouched, no LLM, no chemistry-aware repair) → per
observation `analyze` (Stage 5 + frozen V1–V7). Empty or
ingredient-free text returns `{items: [], warnings: [...]}` —
never a crash, never an entity. Parser limitations (e.g.
unbalanced brackets) propagate as warnings.

## 5. Failure states (all tested)

Empty OCR, whitespace-only, no-ingredient text, malformed
brackets, character substitutions (`Benzoatc`, `E42Z`, `Ac1d`),
multiline lists, duplicated lines, mixed whitespace, corrupted
identifiers, unbalanced parens, retailer typos: every case
resolves to unresolved/unknown/unverified or warns. Partial
agreement is the sharpest proof the gates hold: `Sodium Benzoatc
(E211)` still yields an exact-match candidate via the intact code
but decides **unverified** — the system never fixes chemistry
itself. Correction restores exactly the pre-corruption behavior.

## 6. API (`POST|GET /api/v1/ocr/runs…`)

- `POST /ocr/runs` (201): record client-supplied OCR text, or run
  a server-side extraction via an injected named provider.
  Unknown provider → 422; provider failure → 503
  `OCR_PROVIDER_UNAVAILABLE` with nothing persisted. Shares the
  `observations.create` budget.
- `GET /ocr/runs/{id}`: run + correction + observation links.
  OCR-layer data only — no resolution, no verification, no
  chemistry in the response.
- `POST /ocr/runs/{id}/correction`: one revision; 404/422 on
  missing/repeat/empty.
- `POST /ocr/runs/{id}/analyze`: observe + analyze; warning
  outcome on empty text. Shares the `observations.analyze`
  budget. Response items carry status + identity confidence only.
- All routes require authentication; `extra="forbid"` on bodies;
  request IDs and the standard envelope throughout; no provider
  secrets or internal tokens anywhere.

## 7. Security model

- Authenticated access on all four routes (401 otherwise);
  reviewer role not required (correction is not a review
  decision); actor recorded as `human:{subject}`.
- Parameter-bound SQL only; hostile OCR text persists verbatim
  as data (injection strings stored, never executed) — covered
  by adversarial tests.
- No image bytes stored or served; document ids are opaque
  references; GET responses contain no chemistry beyond what the
  observation layer already exposes behind auth.
- Rate limits reuse the observation budgets (proven by test: 2nd
  ingest → 429 with `Retry-After`, 2nd analyze → 429).
- Gap (documented): no per-user ownership columns — any
  authenticated principal can read any run, exactly like claims
  and reviews today. Per-user scoping waits for `user_id`
  across the schema, not a per-table shortcut.

## 8. Regression evidence (real fixtures, corrupted OCR)

- Food (Frooti RL-14-01): `INS 33O` corruption → the identifier
  node goes unknown; correction restores exact-match/unverified.
- Cosmetic (Nivea RL-13-03): `Citric Ac1d` → unknown/null;
  correction restores exact-match/provisional.
- Personal care (Listerine RL-13-02): substitution + inserted
  line breaks → 9 segments preserved, corrupted node unknown,
  correction restores provisional; multiline layout changes
  nothing.
- Pharma (Simple Linctus RL-15-01): corrupted benzoate →
  unverified; correction restores **verified** for glycerol and
  benzoate (V1–V7, unchanged); unrelated nodes stay unknown;
  duplicated input verifies each copy against the same two
  entities, no third entity appears.

## 9. Verification performed

- `pytest app/tests`: **506 passed, 51 skipped** offline;
  **557 passed** live (501 Stage-15 + 56 new, 0 failed) against a
  fresh Postgres cluster (the pre-existing cluster lost its
  socket across a host restart, so tests ran on a rebuilt
  `labellens_test` — schema is migrated from scratch by every
  fixture, so results are equivalent).
- `flake8 app --max-line-length=88`: clean.
  `python -m compileall -q app`: clean. `git diff --check`: clean.
- New tests: 32 OCR unit, 12 OCR API, 5 OCR regression, 6 live
  OCR, +1 migration file-exists (56 live-delta total with the
  migration split).
- Pre-existing suites green, including the Stage-15 VERIFIED
  cases (still VERIFIED) and false positives at 0.

## 10. Known limitations

- No real OCR vendor is wired: production extraction needs an
  approved provider implementation behind the protocol; the API
  accepts client-supplied OCR text until then.
- Run-level observation listing is sequence-ordered but
  unpaginated; runs themselves have no list endpoint yet.
- `describe` returns observation links, not analyses; analysis
  requires the analyze route (deliberate layering, not an
  omission to work around).
- Single-revision corrections at both layers; correction chains
  remain refused by design.
- Per-user ownership still absent schema-wide (pre-existing).
