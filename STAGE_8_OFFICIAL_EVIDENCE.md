# LabelLens — Stage-8 Official Evidence Adapters

**Date:** 2026-10-05  
**Branch:** `feat/label-pipeline-foundation`  
**Scope:** internal evidence capability. V1–V7 frozen and untouched
(`gate.py` has zero Stage-8 diffs). No endpoints, migrations, frontend,
RDKit, or AI.

## Provider boundaries

| Concern | Owner |
|---|---|
| HTTP, timeouts, retries, size bounds, rate spacing | `adapters/http.py` ONLY |
| Evidence parsing per provider | `adapters/pubchem.py`, `adapters/chebi.py` |
| Evidence model, conflicts, provider fan-out | `evidence.py` (`CombinedAdapter`) |
| Reuse bounds, offline replay | `cache.py` |
| Verification decisions | Stage-7 gate + orchestrator (unchanged rules) |

Adapters return evidence records. The gate decides. A provider can
never mark anything verified -- unknown payload keys (even a literal
`"verified": true`) are ignored by whitelisted field extraction
(regression-tested).

## Verified official endpoints

PubChem PUG-REST (docs: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest):

- `GET /rest/pug/compound/name/{name}/property/{props}/JSON`
- `GET /rest/pug/compound/cid/{n}/property/{props}/JSON`
- `GET /rest/pug/compound/cid/{n}/synonyms/JSON`
- 404 shape `{"Fault": {"Code": "PUGREST.NotFound", ...}}` (confirmed).

ChEBI 2.0 REST (docs: https://www.ebi.ac.uk/chebi/backend/api/docs/,
schema at `/chebi/backend/api/schema/`, OpenAPI 3.0.3):

- `GET /chebi/backend/api/public/es_search/?term={t}&size={n}`
  (exact-match filtered client-side; 404 `{"detail": "No compound
  matches..."}` on miss)
- `GET /chebi/backend/api/public/compound/{id}/` (synonyms, structures)
- No authentication required. No wildcards are ever sent.

## Cache semantics

`EvidenceCache` stores parsed evidence items with provider, request
identity, retrieval time, SHA-256 response hash, source version, and
TTL expiry (default 7 days; stable identity 90 days). A hit replays
evidence byte-identically -- it never upgrades, verifies, or refreshes
it. Expired entries are not served. The cache is evidence storage,
not authority.

## Offline behavior

Adapters accept `offline=True`: cache hits are served, misses yield
`provider_unavailable` notices and empty evidence (decisions degrade to
`unknown`, never invented data). All tests run fully offline via
injected fake transports; no test touches the network (a socket-blocked
lookup test guards the snapshot path; provider tests never construct
the default urllib transport).

## Freshness

Evidence carries `retrieved_at` + provider source version (PUG-REST and
ChEBI records are unversioned per record; retrieval date is recorded
instead). TTL bounds reuse. Re-verification policy itself is unchanged
Stage-6 architecture.

## Evidence vs verification distinction

`EvidenceItem` rows quote providers per field with provenance
(provider, endpoint locator, lookup key, retrieval date, response
hash). `build_source_records` namespaces records per provider
(`PUBCHEM:…`, `CHEBI:…`) with NO cross-provider entity linking --
agreement must come from field/identifier overlap, never assumed
shared identity. `detect_conflicts` flags genuine disagreements
(formula, InChIKey, molecular weight, doubly-claimed identifiers);
raw SMILES/InChI strings are excluded from auto-conflict because
equivalent structures serialize differently (only cheminformatics
could compare them -- out of scope, documented).

## Known provider limitations

- PubChem records are structure records typed `single_molecule`;
  salt-form verification still needs form-aware evidence (salts stay
  `unverified` on provider evidence alone -- tested, documented).
- ChEBI supports no code-only lookup; additive codes resolve only via
  compound-detail synonyms after an exact name hit.
- Molecular weight is compared as 2-decimal presentation strings;
  finer precision differences are out of scope.
- Official per-client quotas are NOT asserted; client spacing is
  conservative (1.0 s default) and documented as such.
- ChEBI compound payloads are large (citations, ontology); only
  whitelisted fields are extracted under size bounds.
