"""Frozen verification gate V1-V7 (pure, deterministic).

Implements the exact gate from ``STAGE_6_VERIFICATION_ARCHITECTURE.md``
§4. Each rule returns PASS | FAIL | UNKNOWN; UNKNOWN never counts as
PASS. Rules version: ``VERIFICATION_RULES_VERSION`` -- every decision
records it so old results stay auditable after rule changes.

Critical CAS distinction (Stage-7 §6): format validity (checksum) is an
integrity check only. It never proves the number belongs to the
candidate and never verifies an entity on its own. Identity still
requires name + identifier dual agreement against source records.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from app.services.verification.models import (
    FAIL,
    PASS,
    UNKNOWN,
    RULE_V1,
    RULE_V2,
    RULE_V3,
    RULE_V4,
    RULE_V5,
    RULE_V6,
    RULE_V7,
    GateResult,
    SourceRecord,
)

__all__ = [
    "VERIFICATION_RULES_VERSION",
    "ADMISSIBLE_SOURCE_CLASSES",
    "NON_MOLECULAR_TYPES",
    "MOLECULAR_ONLY_FIELDS",
    "validate_cas_format",
    "validate_inchikey_format",
    "validate_inchi_format",
    "validate_pubchem_cid_format",
    "derive_name_key",
    "filter_admissible",
    "name_agreeing",
    "identifier_agreeing",
    "v1_admissible_candidate",
    "v2_sources_available",
    "v3_identity_agreement",
    "v4_identifiers",
    "v5_entity_type",
    "v6_source_appropriateness",
    "v7_context",
    "evaluate_gate",
]

VERIFICATION_RULES_VERSION = "1.0.0"

# Registry classes allowed to evidence identity/chemistry claims.
ADMISSIBLE_SOURCE_CLASSES = ("A", "B")

# Representation types that MUST NOT carry single-molecule fields.
NON_MOLECULAR_TYPES = frozenset(
    {
        "mixture",
        "natural_complex",
        "formulation",
        "trade_name",
        "unknown",
    }
)

# Stored field names forbidden on non-molecular representations.
MOLECULAR_ONLY_FIELDS = frozenset(
    {
        "smiles",
        "canonical_smiles",
        "isomeric_smiles",
        "connectivity_smiles",
        "inchi",
        "inchikey",
        "formula",
        "molecular_weight",
    }
)

_CAS_RE = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")
_INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
_CID_RE = re.compile(r"^[1-9][0-9]*$")
_CODE_TOKEN_RE = re.compile(r"\b(?:INS|E|CI)\s*-?\s*\d+[a-z]?\b", re.I)


def validate_cas_format(number: str) -> bool:
    """CAS checksum integrity check. Syntax only -- proves nothing
    about which substance the number belongs to."""
    match = _CAS_RE.match((number or "").strip().upper())
    if not match:
        return False
    digits = (match.group(1) + match.group(2))[::-1]
    total = sum((i + 1) * int(d) for i, d in enumerate(digits))
    return total % 10 == int(match.group(3))


def validate_inchikey_format(key: str) -> bool:
    """Shape check for a 27-character InChIKey. Syntax only."""
    return bool(_INCHIKEY_RE.match((key or "").strip().upper()))


def validate_inchi_format(inchi: str) -> bool:
    """Prefix check for an InChI string. Syntax only."""
    return (inchi or "").strip().startswith("InChI=1")


def validate_pubchem_cid_format(cid: str) -> bool:
    """Shape check for a PubChem CID (positive integer). Syntax only."""
    return bool(_CID_RE.match((cid or "").strip()))


def _canon(text: str) -> str:
    """Canonical comparison key: collapsed whitespace, lowercase."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _canon_code(code: str) -> str:
    """Canonical identifier comparison form."""
    return re.sub(r"[\s\-.]+", "", (code or "").strip().upper())


def _infer_id_type(identifier: str) -> str:
    """Best-effort type label for a Stage-5 identifier string."""
    text = (identifier or "").strip().upper()
    if re.match(r"^E(\s|\d)", text):
        return "e_number"
    if text.startswith("INS"):
        return "ins_number"
    if _CAS_RE.match(text):
        return "cas"
    return "untyped"


def derive_name_key(normalized_text: str, identifier: Optional[str]) -> str:
    """Name portion of normalized text (identifier token excluded).

    Parity contract with Stage-5 ``_match_name_key``: the normalizer
    appends the identifier token to ``normalized_text`` (e.g.
    ``stabilizer INS 471``); name/alias agreement must use the name
    part so codes do not poison matching. A cross-test asserts both
    derivations agree on representative inputs.
    """
    text = normalized_text or ""
    if identifier and _canon_code(identifier):
        want = _canon_code(identifier)
        for match in _CODE_TOKEN_RE.finditer(text):
            if _canon_code(match.group(0)) == want:
                text = text[: match.start()] + " " + text[match.end():]
                break
    return _canon(text)


def filter_admissible(
    records: Sequence[SourceRecord],
) -> List[SourceRecord]:
    """Keep records whose source class may evidence identity claims.

    Wrong-class sources are ignored as evidence (never deleted --
    the caller retains the full list for audit)."""
    return [
        r
        for r in records
        if r.source.source_class in ADMISSIBLE_SOURCE_CLASSES
    ]


def name_agreeing(
    name_key: str, records: Sequence[SourceRecord]
) -> List[SourceRecord]:
    """Records agreeing on the name (preferred or listed names)."""
    return [
        r
        for r in records
        if _canon(r.entity.preferred_name) == name_key
        or any(_canon(n) == name_key for n in r.entity.names)
    ]


def identifier_agreeing(
    identifier: Optional[str], records: Sequence[SourceRecord]
) -> List[SourceRecord]:
    """Records carrying the candidate identifier (any spacing)."""
    if not identifier or not _canon_code(identifier):
        return []
    want = _canon_code(identifier)
    return [
        r
        for r in records
        if any(_canon_code(i.value) == want for i in r.entity.identifiers)
    ]


def v1_admissible_candidate(
    resolution_status: str, *, human_disambiguation: bool = False
) -> GateResult:
    """V1: only exact (or human-resolved) candidates may verify."""
    if resolution_status == "exact_match":
        return GateResult(RULE_V1, PASS, "exact_match candidate")
    if resolution_status == "ambiguous" and human_disambiguation:
        return GateResult(
            RULE_V1, PASS, "ambiguous resolved by recorded human review"
        )
    if resolution_status == "ambiguous":
        return GateResult(
            RULE_V1, FAIL, "ambiguous requires human disambiguation"
        )
    return GateResult(
        RULE_V1, FAIL, "status %s is not verifiable" % resolution_status
    )


def v2_sources_available(records: Sequence[SourceRecord]) -> GateResult:
    """V2: at least one source record must exist to check against."""
    if records:
        return GateResult(
            RULE_V2, PASS, "%d source record(s) present" % len(records)
        )
    return GateResult(RULE_V2, FAIL, "no source records returned")


def v3_identity_agreement(
    name_hits: Sequence[SourceRecord], *, dual_agreement: bool = False
) -> GateResult:
    """V3: name agreement plus independent corroboration.

    Corroboration is identifier dual-agreement (same record agrees on
    name and identifier) or two independent agreeing source records.
    Single-source name-alone agreement is UNKNOWN, never PASS.
    """
    if not name_hits:
        return GateResult(
            RULE_V3, FAIL, "no source record agrees on the name"
        )
    if dual_agreement or len({r.entity.entity_id for r in name_hits}) >= 2:
        return GateResult(
            RULE_V3, PASS, "name agreement with corroboration"
        )
    return GateResult(
        RULE_V3,
        UNKNOWN,
        "single source name agreement needs corroboration",
    )


def v4_identifiers(
    candidate_identifier: Optional[str],
    records: Sequence[SourceRecord],
    *,
    name_hit_ids: frozenset = frozenset(),
) -> GateResult:
    """V4: identifier format validity plus belonging agreement.

    ``name_hit_ids`` are entity IDs of name-agreeing records; an
    identifier match on one of those records is dual agreement.
    Format validity alone (e.g. a passing CAS checksum) never proves
    belonging and never verifies an entity.
    """
    if not candidate_identifier or not _canon_code(candidate_identifier):
        non_mol = any(
            r.entity.representation_type in NON_MOLECULAR_TYPES
            for r in records
        )
        if non_mol:
            return GateResult(
                RULE_V4,
                PASS,
                "no identifiers required for non-molecular entity",
            )
        return GateResult(
            RULE_V4, UNKNOWN, "no identifiers present to check"
        )
    id_type = _infer_id_type(candidate_identifier)
    if id_type == "cas" and not validate_cas_format(candidate_identifier):
        return GateResult(
            RULE_V4, FAIL, "malformed CAS number %s" % candidate_identifier
        )
    hits = identifier_agreeing(candidate_identifier, records)
    if any(h.entity.entity_id in name_hit_ids for h in hits):
        return GateResult(
            RULE_V4, PASS, "identifier agrees with source record"
        )
    if hits:
        return GateResult(
            RULE_V4, FAIL, "identifier claimed by a different entity"
        )
    return GateResult(
        RULE_V4, FAIL, "identifier disagrees with source records"
    )


def v5_entity_type(
    candidate_type: Optional[str], records: Sequence[SourceRecord]
) -> GateResult:
    """V5: candidate class must be compatible with the source class."""
    if not candidate_type or candidate_type == "unknown":
        return GateResult(
            RULE_V5, UNKNOWN, "candidate type unknown, cannot confirm"
        )
    for record in records:
        source_type = record.entity.representation_type or (
            record.entity.entity_type
        )
        if _canon(source_type) == _canon(candidate_type):
            return GateResult(
                RULE_V5, PASS, "entity type agrees: %s" % source_type
            )
    return GateResult(
        RULE_V5, FAIL, "candidate type conflicts with source record"
    )


def v6_source_appropriateness(
    records: Sequence[SourceRecord],
) -> GateResult:
    """V6: at least one consulted source may evidence identity."""
    admissible = filter_admissible(records)
    if admissible:
        return GateResult(
            RULE_V6,
            PASS,
            "%d admissible source(s)" % len(admissible),
        )
    return GateResult(
        RULE_V6, FAIL, "no consulted source may evidence identity"
    )


def v7_context(
    records: Sequence[SourceRecord], *, context: Optional[str] = None
) -> GateResult:
    """V7: required record contexts must be satisfied when present."""
    required = {
        _canon(c) for r in records for c in r.entity.contexts
    }
    if not required:
        return GateResult(RULE_V7, PASS, "no context requirements")
    if context is None:
        return GateResult(
            RULE_V7, UNKNOWN, "context required but none supplied"
        )
    if _canon(context) in required:
        return GateResult(RULE_V7, PASS, "context satisfied")
    return GateResult(
        RULE_V7, FAIL, "supplied context contradicts record scope"
    )


def evaluate_gate(
    *,
    resolution_status: str,
    normalized_text: str,
    candidate_identifier: Optional[str],
    candidate_type: Optional[str],
    records: Sequence[SourceRecord],
    context: Optional[str] = None,
    human_disambiguation: bool = False,
) -> Tuple[GateResult, ...]:
    """Run V1-V7 in order. Pure function of its inputs.

    V6 acts as an evidence filter: V3-V5 and V7 evaluate admissible
    records only. Corroboration flows one way (agreement sets into
    V3/V4 verdicts), never circularly between verdicts.
    """
    admissible = filter_admissible(records)
    key = derive_name_key(normalized_text, candidate_identifier)
    name_hits = name_agreeing(key, admissible)
    id_hits = identifier_agreeing(candidate_identifier, admissible)
    name_ids = frozenset(r.entity.entity_id for r in name_hits)
    dual = any(h.entity.entity_id in name_ids for h in id_hits)
    return (
        v1_admissible_candidate(
            resolution_status,
            human_disambiguation=human_disambiguation,
        ),
        v2_sources_available(records),
        v3_identity_agreement(name_hits, dual_agreement=dual),
        v4_identifiers(
            candidate_identifier, admissible, name_hit_ids=name_ids
        ),
        v5_entity_type(candidate_type, admissible),
        v6_source_appropriateness(records),
        v7_context(admissible, context=context),
    )
