# LabelLens — Stage-9 Human Review + Controlled Verification

**Date:** 2026-10-05  
**Branch:** `feat/label-pipeline-foundation`  
**Scope:** internal review service layer. V1–V7 frozen and untouched
(`gate.py` has zero Stage-9 diffs). No endpoints, migrations, frontend,
RDKit, chemistry, or AI.

## Review lifecycle

Review status is separate from verification status:

```text
queued -> in_review -> approved | rejected
                     -> needs_more_evidence | closed_unknown
```

Deterministic review IDs (`REV-0001…`), deterministic priority
(conflicted 0, provisional 1, unknown 2, unverified 3; FIFO within a
level), deterministic event IDs (`REV-0001:001…`). No ML ranking, no
risk scores, no randomness.

Routing: conflicted/provisional always; unknown/unverified only when
resolution alternatives give the reviewer something to choose;
verified never. Unknown is a terminal outcome (`closed_unknown`),
never a forced promotion.

## Reviewer boundaries

- Reviewer identity is an explicit caller string; empty and AI
  identities (`ai`, `ai:…`, `llm:…`) are rejected. No authentication
  in this stage (model carries the actor field for later auth).
- Every decision requires a non-empty reason. `confirm_identity`
  requires an explicit selection among the resolution's candidates
  and approves `("identity",)` only -- formula, structure, weight,
  and role approvals do not exist here.
- "I know this chemical" is not evidence: confirmations still pass
  the full gate, and provider disagreements still come back
  `conflicted` even after confirmation.

## Audit events

Append-only per review: `ReviewCreated → ReviewClaimed →
ReviewDecisionRecorded → ReverificationTriggered →
VerificationResultRecorded`. Each event carries actor, reason,
previous/new state, evidence-context hash, and rules/snapshot
versions. History is never rewritten; re-verification appends new
result events beside old ones.

## Re-verification

`reverify_candidate(resolution, adapter, selection)` enforces, in order:

1. selection targets this exact candidate (key match),
2. selection names one of its candidates,
3. fresh evidence re-hashed identically (any material change rejects
   the stale selection -- re-review required),
4. the frozen gate decides with `human_disambiguation=True`, the
   selected candidate's type (or reviewer-corrected type), and the
   corrected identifier substituted into the text (or the original).

Name corrections are refused by key mismatch: a renamed candidate
must go back through normalization/resolution, not verification.

## Claim-level approval

Approvals are identity-only. A verified-via-review decision carries
identity claims plus only whatever field evidence the gate's sources
already support -- nothing the reviewer typed becomes chemistry.

## Conflict handling

Both provider records stay visible in the review's evidence context;
the reviewer sees the disagreeing fields, both sources, and the
frozen reason. Confirming one side does not erase the other: with
unchanged evidence the gate still returns `conflicted`.

## Provider readiness findings (documentation audit, 2026-10-05)

- PubChem PUG-REST: no authentication required (anonymous access
  confirmed live repeatedly); official quota number UNKNOWN --
  the docs page is JS-gated and quotas are not scraped from third
  parties per project rules. Client spacing stays conservative
  (1.0 s) and is documented as client-side only, not provider quota.
- ChEBI 2.0 REST: no authentication required (stated in official API
  docs); no quota numbers found in the retrieved docs -- UNKNOWN.
  Terms: EMBL-EBI Terms of Use (rev. 2024-02-05): open science, no
  additional restrictions beyond data owners, attribution expected,
  terms may change.
- NCBI (PubChem host): US-government public resource; full license
  text review deferred to the deployment stage.
- Response semantics for both providers verified empirically
  (success shapes, 404 bodies, field coverage) and frozen into
  mocked fixtures.

## Egress / secrets audit

Repository grep: no API keys, credentials, or tokens in source,
snapshots, or tests. Neither provider requires credentials, so no
environment variables were created. All network access remains inside
`adapters/http.py` (verified by import surface: gate, models,
evidence, and review modules import no network clients).

## Cache / review interaction

Review items freeze the evidence hash (identities + source refs +
versions; timestamps excluded). Refreshed evidence changes the hash,
which rejects stale selections at reverify time -- old approvals are
never silently reused against new evidence. Expiry still bounds
reuse independently.
