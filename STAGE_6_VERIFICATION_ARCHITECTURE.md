# LabelLens — Stage-6 Verification Architecture

**Status:** Architecture frozen for Stage-7 implementation  
**Date:** 2026-10-05  
**Branch:** `feat/label-pipeline-foundation`  
**Scope:** ARCHITECTURE ONLY. No verification code, records, migrations,
API changes, or external calls are made in this stage.

Accepted foundation: Stage-2 parser (v1.0.0) → Stage-4 normalizer (v1.0.0)
→ Stage-5 resolver (v1.0.0, statuses
`exact_match | candidate | ambiguous | unresolved`, synthetic fixtures
only). Working tree was clean before this document; it stays code-free.

---

## 1. Executive decision

**Verification authority (answers §26.1–§26.3): Option C — local canonical
snapshot + versioned source ingestion + optional live refresh.**

- The **local canonical snapshot** is the verification authority at
  request time. A `verified` state means: "this record passed the frozen
  gate (§4) against snapshot version N, whose every field carries source
  provenance." It does not mean "the live internet agrees right now."
- **Versioned ingestion** is the only path new truth enters the snapshot:
  source payload → adapter normalization → gate evaluation → new snapshot
  version → import. No silent overwrites, no direct external-to-canonical
  writes.
- **Live refresh** is evidence gathering, not truth replacement. An
  official-database adapter may supply fresh field evidence; the evidence
  evaluator re-runs the gate, and the outcome is a new versioned decision
  (`verified` reaffirmed, `provisional`, `conflicted`, or `obsolete` for
  the old record) — never an in-place mutation.

**Rejected:** A (snapshot-only forever — goes stale on regulatory/dynamic
facts), B (live-API-only — non-reproducible, rate-limited, unusable
offline, untestable deterministically). Provider terms/limits that could
affect adapter tuning (PubChem rate limits, ChEBI API versioning, NIST
redistribution rules per `SOURCE_REGISTRY.md`) are marked
**to-verify-against-current-official-docs** at Stage-7 build time; no
limits are invented here.

**What qualifies as verified:** a candidate identity **plus** all gate
conditions V1–V7 (§4) evaluated by the frozen rules version, with
per-field evidence attached (§6–§7). Anything less is `provisional`,
`conflicted`, `unverified`, or `unknown` — never `verified`.

**What remains provisional:** single-source identities, identifier-only
matches without name agreement, OCR-near candidates regardless of score,
any field with exactly one weak source, any record past its freshness
recheck point pending re-evaluation.

---

## 2. Verification state machine

### State ownership

| Owner | States |
|---|---|
| Stage-5 resolution | `candidate` (working hypothesis incl. `exact_match`/`ambiguous`/`unresolved` outcomes) |
| Stage-6 verification | `provisional`, `verified`, `conflicted`, `unverified`, `unknown`, `obsolete` |

Resolution statuses are inputs, never overwritten: a `Resolution` keeps
its `exact_match | candidate | ambiguous | unresolved` outcome permanently
as the hypothesis record; verification writes a separate decision.

### Transition table (append-only; every transition emits a verification event)

| CURRENT STATE | EVENT | NEXT STATE | NOTE |
|---|---|---|---|
| `candidate` | gate V1–V7 all pass | `verified` | creates versioned entity + field claims |
| `candidate` | gate partially passes | `provisional` | usable with visible qualification |
| `candidate` | no adequate source | `unverified` | evidence insufficient, not disproven |
| `candidate` | nothing resolvable | `unknown` | terminal until new evidence arrives |
| `candidate` | sources disagree on identity | `conflicted` | both sides preserved |
| `provisional` | remaining evidence arrives | `verified` | full gate re-run, new version |
| `provisional` | evidence contradicts | `conflicted` | — |
| `provisional` | evidence absent after recheck | `unverified` | downgrade, history kept |
| `verified` | contradicting source evidence | `conflicted` | old record kept, flagged |
| `verified` | superseded (new snapshot/source version) | `obsolete` | replaced-by link, never deleted |
| `verified` | freshness recheck passes | `verified` | new `last_checked`, same version + 1 check event |
| `verified` | freshness recheck inconclusive | `provisional` | visible downgrade until resolved |
| `conflicted` | new decisive evidence | `verified` | conflict record retained in history |
| `conflicted` | evidence still split | `conflicted` | — |
| `unverified`/`unknown` | new evidence arrives | re-enter gate | same table as `candidate` |
| `obsolete` | — | (terminal) | historical; never reactivated, only superseded-by |

**Irreversible:** `obsolete` (history only). **Revisable:** all others, but
only forward through new events — previous states are never edited, only
superseded. A later invalidation therefore never rewrites history: the old
`verified` record becomes `obsolete`/`conflicted` with its provenance
intact, which is what makes old analyses auditable after rules change.

**`conflicted` triggers:** two appropriate sources assert incompatible
values for the same field/entity/context. **Not conflicts:** different
salts/forms (separate entities), different jurisdictions/dates (scoped
claims), different fields (field-level only).

**`obsolete` triggers:** snapshot version superseded the record, or the
source issued a corrected/withdrawn record. Obsolete records keep serving
historical analyses with a visible marker.

---

## 3. Entity/claim/source model

Three record kinds, never merged into a text blob:

```text
Resolution (Stage-5 hypothesis, immutable input)
   ↓ verification decision
ChemicalEntity  — identity ONLY:
  entity_id (UUID, stable), preferred_name, entity_type,
  representation_type, verification_status, verification_version,
  first_verified_at, last_verified_at, limitations[]
   ↓ has_field_claim (one row PER FIELD)
Claim — one verifiable fact:
  claim_id, entity_id, field (identity | formula | smiles |
  molecular_weight | identifier:<type> | role:<domain> |
  product_contains | regulatory:<jurisdiction>),
  value, verification_status, confidence, provenance_type,
  valid_from/valid_until, verification_version
   ↓ supported_by (many-to-many, contradiction preserved)
Source — registry entry + retrieval:
  source_id (stable registry ID, e.g. PUBCHEM), record locator,
  retrieved_at, source_version/date, license note
```

This directly yields the required mixed state:

```text
Identity  → verified   (Claim A, 2 agreeing sources)
Formula   → verified   (Claim B, authoritative DB)
Structure → unverified (Claim C, no appropriate source)
Role      → unknown    (Claim D, no domain evidence yet)
```

because each field is an independent claim row with its own status,
confidence, and sources. A verified entity NEVER implies verified fields.

---

## 4. Verification gate definition (frozen conditions V1–V7)

All must pass for `verified`. Any single failure routes per §2
(partial → `provisional`, disagreement → `conflicted`,
absence → `unverified`/`unknown`).

| # | Condition | Concrete check |
|---|---|---|
| V1 | Admissible candidate | Stage-5 status `exact_match` (single), or `ambiguous` resolved by explicit human selection recorded as a verification event. `candidate` (OCR-near) and `unresolved` are inadmissible, regardless of score. |
| V2 | Authoritative source located | ≥1 record from a registry Class-A/B source appropriate to the claim type (`SOURCE_REGISTRY.md` claim mapping); source ID, version/date, retrieval timestamp captured. |
| V3 | Identity agreement | Source record agrees on preferred name (exact, post-normalization) **and** ≥1 independent corroboration: a validated identifier (V4) or a second agreeing source. Name-alone matches stay `provisional` (cf. `DATA_PIPELINE.md` Stage-5 gate). |
| V4 | Identifier validation | Each stored identifier validated by format: CAS checksum (mod-10), numeric PubChem CID, `CHEBI:` prefix + numeric, `InChI=1…` prefix, 27-char InChIKey shape. Format-valid ≠ identity proof (V3 still required). Mismatched identifiers across sources → `conflicted`. |
| V5 | Entity-type validation | Assigned `representation_type` must permit the stored fields: `mixture | natural_complex | formulation | trade_name | unknown` MUST NOT carry SMILES/formula/molecular weight; `polymer | material` carry only applicable fields. Type mismatch blocks verification. |
| V6 | Source appropriateness | Source class must cover the claim: identity/chemistry from A/B chemical DBs; roles from domain sources; regulatory only from the matching jurisdiction's current source; product-presence only from label/manufacturer observation. Wrong-class sources are ignored as evidence (kept as discovery notes at most). |
| V7 | Context checks | Domain, jurisdiction, and date recorded where the claim is context-sensitive; stale-dynamic claims (past recheck point, §9) cannot newly verify until refreshed. |

Gate rules are versioned (`verification_version`, e.g. `v6.1`); every
decision records which rules version ran, so old results stay auditable
after rule changes and can be regenerated by re-running the frozen rules
against stored inputs (§10 provenance answers).

---

## 5. Source hierarchy (from `SOURCE_REGISTRY.md`, no new providers)

| Class | Verification role |
|---|---|
| A — official DB / regulator (PubChem, ChEBI, Codex GSFA, FSSAI, FDA, EU DBs, CosIng for nomenclature) | Identity + chemistry evidence; regulatory only within own jurisdiction |
| B — high-quality scientific reference | Corroborating identity/chemistry; mechanism context |
| C — product/manufacturer label | Product-presence evidence ONLY; never chemical identity |
| D — secondary reference | Supporting context; never sole basis for `verified` |
| E — discovery (blogs, forums, AI output, snippets) | Never verification evidence; candidate hints only |

Source priority for one claim: correct entity/context → claim-appropriate
class → currentness → directness. Registry metadata required per source:
stable `source_id`, adapter name + version, claim types covered, license /
redistribution / caching stance, freshness class, rate-limit policy
(to-verify live at build), last-checked. Source IDs must be stable strings
(`PUBCHEM`, `CHEBI`, …); versions are dates/numbers on retrievals, never
part of the ID.

---

## 6. Adapter architecture (provider-independent)

Core verification logic depends only on this ABC; no vendor SDK leaks past
`backend/app/providers/`:

```python
class VerificationSource(ABC):
    source_id: str          # stable registry ID
    adapter_version: str
    claim_types: list[str]  # claim types it may evidence
    freshness_class: str

    def lookup_identity(self, candidate) -> list[SourceRecord]: ...
    def fetch_field(self, record_ref, field) -> FieldEvidence | None: ...
```

- `SourceRecord`: source-local ID, observed name/identifiers/fields,
  source version/date, retrieval timestamp, license note, raw-hash
  (fields only — raw payloads are NOT persisted).
- Three implementations planned for Stage 7: `SnapshotAdapter` (local
  canonical snapshot; deterministic; the default authority),
  `OfficialDbAdapter` (PubChem/ChEBI over cached, rate-limited HTTP;
  evidence/refresh only), `ManualAdapter` (human review queue; decisions
  recorded as verification events with reviewer identity).
- `VerificationOrchestrator`: candidate → fan-out to adapters →
  `EvidenceEvaluator` (applies V1–V7 + hierarchy) → decision
  (`verified | provisional | conflicted | unverified | unknown`) with
  per-field claims. Adding a source = new adapter + registry entry; zero
  core-logic changes.

---

## 7. Local canonical snapshot strategy

- Format: versioned seed artifact (e.g. `snapshots/canonical_v< N >.json`),
  each record = entity identity + field values + per-field source refs
  (source ID, locator, version/date, license).
- Ingestion is a versioned import (migration-style, reviewed): snapshot N
  → validate V1–V7 offline → write entity + claim rows tagged
  `verification_version` + snapshot version. Updates only via N+1; no
  in-place truth edits.
- The snapshot gives deterministic tests, reproducible results, offline
  behavior, instant reads, and zero per-request cost. Live adapters give
  refresh/contradiction signals. Initial content: a small hand-verified
  subset (candidate: the current demo-critical identities), each field
  traced to an A/B source — the golden CSV stays `needs_verification`
  until this process promotes individual rows, never wholesale.

---

## 8. Conflict handling (seven cases → states)

| Case | Resulting state |
|---|---|
| 1. Two appropriate sources agree on identity | `verified` (both cited) |
| 2. Sources disagree on an identifier (e.g. CAS) | `conflicted` on the identifier claim; identity claim keeps its own status if otherwise gated |
| 3. Sources describe different salts/forms | Two entities (or explicit salt/form variants), linked `related`; NOT a conflict |
| 4. Source record outdated (newer version exists) | Old claim → `obsolete` (replaced-by); re-run gate on new record |
| 5. Authoritative but different context (jurisdiction/date/domain) | Scoped claims coexist; NOT a conflict |
| 6. Identity agreed, one field disputed | Field-level `conflicted` only; other fields unaffected |
| 7. Candidate name has multiple valid chemical meanings | Stays `ambiguous` at resolution; verification inadmissible (V1) until human disambiguation |

Never silently select a value. Conflicted fields are excluded from
downstream chemistry/role/explanation inputs until resolved.

---

## 9. Freshness model

Per-claim timestamps: `first_verified_at`, `last_verified_at`,
`last_checked_at`, `source_version`, `freshness_class`,
`verification_version`. Classes:

- **Stable** (identity, validated identifiers, structure refs): recheck on
  contradictory evidence or rules change only. Age alone never
  invalidates.
- **Moderate** (names/synonyms, classifications): periodic recheck
  (candidate: 180 days) or on snapshot update touching the record.
- **Dynamic** (regulatory status, product presence, formulations):
  recheck per use-case (candidate: 30 days); expired → `provisional`
  with `stale_pending_recheck`, never served as current-`verified`.

Re-verification = re-run the frozen gate with fresh evidence → new
decision version appended; history preserved.

---

## 10. Provenance model (reproducibility answers)

Every decision stores: exact candidate input (IDs + texts + registry
version), observed source values (field-level, with source versions and
retrieval times), gate rules version, adapter versions, decision +
timestamp. Regeneration: re-run rules version on stored inputs → identical
decision. Audit after rule changes: old decisions cite their rules
version; a migration report can list decisions affected by a rule diff.
Caches (if any) key on
`(candidate_ref, source_id, source_version, rules_version)` and store the
full provenance above — a cache hit is a reproducible decision replay,
never hidden truth.

---

## 11. Confidence model

Qualitative states `HIGH | MEDIUM | LOW | UNKNOWN | CONFLICTED`, tracked
per dimension, never merged:

- `identity_confidence`: gate strength (V3 corroboration count + source
  class). `verified` requires HIGH.
- `evidence_confidence`: source class × freshness per claim.
- `normalization_confidence` (Stage 4, inherited read-only),
  future `structure_confidence`, `formula_confidence`,
  `property_confidence`, `role_confidence`: each from its own claim set.
- Internal numeric ranking may exist inside the evaluator; it is
  undocumented externally, never serialized as probability, never shown
  as `98.7%`.

---

## 12. Product-specific evidence boundary

Two claim families, separate evidence, separate lifecycles:

- `ChemicalEntity exists` — evidenced by A/B sources (§5). Stable.
- `Product P contains entity E` — evidenced ONLY by the label
  observation chain (scan → OCR run → observation ID → user-correction
  events). Dynamic (formulations change); never inherits chemical
  confidence.

The label image proves what was observed, not chemistry. Chemistry detail
screens must show both: entity facts (with source evidence) and
presence facts (with observation evidence).

---

## 13. Failure modes

| Failure | Behavior |
|---|---|
| Source unavailable / timeout | `provisional` (if prior verified record + within freshness) else `unverified`; bounded retries with backoff, then stop |
| Rate limited | Queue + backoff; serve snapshot state marked with `last_checked`; never degrade to invention |
| Invalid source response | Discard payload, keep hash for audit, `unverified` for affected fields |
| Entity absent from sources | `unknown` (not `unverified` — nothing to verify against) |
| Identifier mismatch | `conflicted` on the field |
| Malformed candidate input | Reject at boundary; no decision record beyond a validation event |
| Unsupported entity type for a field | Field claim `unverified` with `not_applicable` reason; entity may still verify |
| Stale source | `provisional` + `stale_pending_recheck` |
| Partial source record | Verify only evidenced fields; rest `unknown` |

External availability never justifies invented data: the degraded states
above are the complete failure vocabulary.

---

## 14. Security boundary

Adapters consume untrusted input (OCR/user text as lookup keys; external
payloads as data). Rules: static schemas for all source responses with
size/depth bounds; reject oversized payloads before parsing; no `eval`,
no dynamic imports keyed on input, no SQL string construction (ORM-bound
parameters only); no prompt construction from external content anywhere
in this pipeline (no LLM in verification at all); persist extracted
fields + payload hash, never raw payloads (PII/license hygiene); adapter
credentials server-side only, never in the snapshot artifact.

---

## 15. Testing architecture (designed, not written)

| Layer | Purpose | Key cases |
|---|---|---|
| Unit | Gate logic in isolation (mocked adapters) | each V-condition pass/fail; format validators (CAS checksum etc.) |
| Contract | Adapter ABC compliance | all adapters satisfy `VerificationSource`; timeout/rate-limit behavior |
| Fixture | Frozen snapshot + recorded payloads | candidate→verified/provisional/conflicted/unknown; salt-vs-form split; mixture verified-without-SMILES; trade name stays unverified |
| Integration | Orchestrator + in-memory DB | end-to-end decision with provenance rows written |
| Regression | Golden promotion set | previously-verified records re-verify identically under same rules version |
| Conflict | Disagreement matrix | §8 cases 1–7 → exact states |
| Failure | Degraded operation | §13 table rows; no invention under any failure |
| Provenance | Audit replay | decision regenerates byte-identically from stored inputs |

---

## 16. API implications (proposed, not implemented)

No new endpoints required. Existing contracts already separate the
concerns (`POST …/match`, `GET /ingredients/{id}`,
`GET /ingredients/{id}/evidence`, `GET /claims/{id}`,
`POST /claims/{id}/verify`):

- `GET /ingredients/{chemical_entity_id}`: add a `verification` block
  (`status`, `verification_version`, `last_checked_at`, per-field
  summary) — additive, backward compatible.
- `GET …/evidence`, `GET /claims/{id}`: already claim-oriented; add
  `freshness_class` / `valid_until` fields when served (additive).
- Status vocabularies gain `provisional | conflicted | obsolete` where
  enums are documented — additive values only; no renames.
- Internal adapters/orchestrator stay server-side; no public surface.

---

## 17. Database implications

- **Already supported:** `chemical_entities` (identity + status +
  version timestamps), `claims` + `claim_sources` (field-level evidence),
  `entity_matches` (hypothesis link), `sources` (registry mirror),
  `verification_events` (transition log). No schema contradiction found.
- **Needs clarification (docs, not schema):** convention that one
  `claims` row = one field (identity/formula/structure/identifier/role/
  presence) with `verification_status` + `confidence` per row.
- **Missing (Stage-7+ scope):** snapshot-version record (aligns with the
  specified V2 `source_snapshots` table — adopt it, don't invent a new
  one); a `verification_runs` log (or reuse `model_runs`-style run
  records for orchestrator decisions).
- **No migration in this stage.** Schema changes, if any, land with
  Stage-7 implementation + migration files per `DEVELOPMENT_GUIDE.md`.

---

## 18. Open risks

1. Snapshot seeding labor: hand-verifying the first records against A/B
   sources is slow expert work; wholesale golden-CSV promotion is
   explicitly forbidden, so coverage grows record-by-record.
2. Live-adapter terms (rate limits, caching/licensing constraints) are
   unverified until checked against current official docs at build time.
3. Ambiguous-candidate queue needs a human-review path (`ManualAdapter`)
   before `ambiguous` inputs can ever verify — otherwise they accumulate.
4. Dynamic claims (regulatory) can go stale faster than recheck cadence;
   the `provisional`-on-expiry downgrade must be enforced by a scheduled
   check, which is itself future scope.
5. Representation-type edge cases (complex salts, hydrates, polymers
   with partial structure) will stress V5; the type table needs worked
   examples during Stage 7.

---

## 19. Stage-7 implementation contract

Stage 7 implements ONLY the above, in this order, stopping at the
persistence boundary defined here (no chemistry computation, roles, or
explanations):

1. `backend/app/services/verification/` package: `gate.py` (V1–V7 as
   pure functions over dataclasses, rules version constant),
   `orchestrator.py`, `adapters/base.py` (`VerificationSource` ABC),
   `adapters/snapshot.py` (reads versioned seed artifact), `models.py`
   (ChemicalEntity/Claim/Source decision records, JSON-serializable).
   `ManualAdapter` stub returning `provisional` + review-queue entry.
   Live `OfficialDbAdapter` deferred to Stage 8 unless trivially
   cache-safe; its contract is frozen here regardless.
2. `snapshots/canonical_v1.json`: ≤10 hand-verified records with full
   per-field provenance (format + review checklist in the snapshot
   README). Golden CSV untouched.
3. Tests per §15 unit/contract/fixture/conflict/failure/provenance
   layers; all Stage 2/4/5 suites stay green; flake8 + compileall clean.
4. No migrations, no endpoints, no RDKit, no AI. Acceptance: the §15
   fixture matrix passes deterministically offline; every `verified`
   test record traces to snapshot provenance; every §13 failure input
   yields the specified degraded state and nothing else.

---

## Appendix — §26 ten answers, one line each

1. Authority: versioned local canonical snapshot; live sources are evidence, not truth.
2. Canonical record: snapshot JSON record → entity + per-field claim rows with provenance.
3. Verified: candidate + gate V1–V7 all pass under frozen rules, evidence attached.
4. Provisional: partial evidence, single weak source, OCR-near, or stale-pending-recheck.
5. Conflicts: `conflicted` field/entity states with both sides preserved; never auto-resolved.
6. Sources versioned: stable IDs; per-retrieval version/date; snapshot versions; rules versions.
7. Claims separated: one claim row per field; entity verification implies no field.
8. Re-verification: freshness classes + scheduled recheck → new versioned decision, history kept.
9. Local vs external: local decides; external refreshes; manual breaks ties.
10. Stage 7 builds: gate + orchestrator + ABC + snapshot adapter + v1 seed + full test layers — nothing more.
