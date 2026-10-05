# Canonical Snapshot — Provenance & Maintenance Rules

`canonical_v1.json` is the Stage-7 verification authority: 4 records,
version `canonical_v1`, curated under gate rules `1.0.0`.

## How records were established (v1)

Each record was transcribed verbatim from a live PubChem PUG-REST
property query on 2026-10-05 (Class-A source per `SOURCE_REGISTRY.md`).
No value was inferred, computed, or completed from memory:

- `preferred_name`, `names`: PUG-REST `Title` / `IUPACName` as returned.
- `formula`, `molecular_weight`, `smiles`, `inchi`, `inchikey`:
  PUG-REST property values as returned (SMILES key holds the
  non-connectivity string PUG-REST returned for the query).
- `identifiers`: `pubchem_cid` + `inchikey` from the same property
  payload; `e_number` / `ins_number` only where a PubChem synonym on
  the same CID record states the code (E330/INS-330 on CID 311,
  E211/INS-211 on CID 517055, E422/INS-422 on CID 753). Ethanol
  carries no additive code because none was evidenced.
- Every field and identifier carries its own provenance note with
  query URL and retrieval date.

Quality over quantity: 4 genuinely-sourced records ship instead of 10
shaky ones. The golden CSV (`INGREDIENT_GOLDEN_DATA.csv`) remains
`needs_verification`; nothing was bulk-promoted from it.

## Immutability

This file is NEVER modified in place by application code. The
`SnapshotAdapter` opens it read-only. Corrections, refreshes, and
additions land in `canonical_v2` (new file), built by a future
versioned ingestion process that re-runs gate V1–V7 offline before
import. Old versions are retained for audit replay.

## Refresh policy

Stable identity fields: recheck only on contradicting evidence or
gate-rule changes. Dynamic claims are out of scope for v1 (no
regulatory/product-presence records included). `last_checked` records
the last successful re-read of the source record.
