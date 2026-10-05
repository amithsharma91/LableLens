"""Verification orchestrator (Stage-7 entry point).

Canonical entry point: :func:`verify_candidate`.

Pipeline per decision:

    Resolution (Stage-5 hypothesis, never rewritten)
        ↓ adapter fan-out (snapshot now; more adapters later)
    SourceRecord list (retrieval, not verification)
        ↓ frozen gate V1-V7 (pure; see gate.py)
    VerificationDecision (explained outcome + evidence + claims)

Status mapping (frozen with the gate):

- all PASS                        → verified / HIGH
- V1 FAIL on ambiguous            → provisional (needs disambiguation)
- V1 FAIL otherwise, no records   → unknown
- V1 FAIL otherwise, records seen → unverified
- identifier/name contradiction   → conflicted / CONFLICTED
- V2 FAIL (no records at all)     → unknown
- V6 FAIL (nothing admissible)    → unverified
- V5 FAIL (type conflict)         → unverified
- V4 FAIL (malformed identifier)  → unverified
- V7 FAIL (context contradiction) → provisional
- otherwise any UNKNOWN           → provisional
  (MEDIUM when identity agreed, else LOW)

No mapping ever promotes a non-PASS gate to verified.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.evidence import detect_conflicts
from app.services.verification.gate import (
    VERIFICATION_RULES_VERSION,
    FAIL,
    PASS,
    evaluate_gate,
    filter_admissible,
    identifier_agreeing,
    name_agreeing,
)
from app.services.verification.models import (
    CONF_CONFLICTED,
    CONF_HIGH,
    CONF_LOW,
    CONF_MEDIUM,
    CONF_UNKNOWN,
    STATUS_CONFLICTED,
    STATUS_PROVISIONAL,
    STATUS_UNKNOWN,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
    FieldEvidence,
    GateResult,
    IdentityClaim,
    SourceMetadata,
    SourceRecord,
    VerificationDecision,
)
from app.services.verification.review import (
    ReviewSelection,
    candidate_key_for,
    current_context_hash,
)

__all__ = ["verify_candidate", "reverify_candidate", "ORCHESTRATOR_VERSION"]

ORCHESTRATOR_VERSION = "1.0.0"


def _details(results: Sequence[GateResult]) -> dict:
    return {g.rule_id: g for g in results}


def _join_reasons(results: Sequence[GateResult]) -> str:
    return "; ".join(
        "%s=%s (%s)" % (g.rule_id, g.result, g.detail) for g in results
    )


def _source_refs(records: Sequence[SourceRecord]) -> Tuple[SourceMetadata, ...]:
    seen = set()
    out: List[SourceMetadata] = []
    for record in records:
        key = (record.source.source_id, record.source.record_locator)
        if key not in seen:
            seen.add(key)
            out.append(record.source)
    return tuple(out)


def _identity_evidence(
    entity_id: str, records: Sequence[SourceRecord]
) -> Tuple[FieldEvidence, ...]:
    return tuple(
        FieldEvidence(
            field="identity",
            value=record.entity.preferred_name,
            unit=None,
            source=record.source,
        )
        for record in records
    )


def verify_candidate(
    resolution: Resolution,
    adapter: VerificationSource,
    *,
    context: Optional[str] = None,
    human_disambiguation: bool = False,
) -> VerificationDecision:
    """Verify one Stage-5 resolution against an adapter's records."""
    records = adapter.lookup_identity(resolution) or []
    return _decide(
        resolution_status=resolution.status,
        normalized_text=resolution.normalized_text or "",
        candidate_identifier=resolution.identifier,
        candidate_type=_candidate_type(resolution),
        records=records,
        adapter=adapter,
        context=context,
        human_disambiguation=human_disambiguation,
        extra_warnings=tuple(resolution.warnings),
    )


def reverify_candidate(
    resolution: Resolution,
    adapter: VerificationSource,
    selection: ReviewSelection,
    *,
    context: Optional[str] = None,
) -> VerificationDecision:
    """Re-verify after an approved human review selection.

    The selection must match the current candidate (key), name one of
    its candidates, and carry the hash of the evidence under review.
    Fresh evidence is fetched and hashed identically: any material
    change rejects the stale selection instead of reusing the old
    approval. The frozen gate still decides; human judgment only
    disambiguates and corrects identifier/type inputs.
    """
    key = candidate_key_for(
        resolution.normalized_text or "", resolution.identifier
    )
    if selection.candidate_key != key:
        raise ValueError(
            "selection targets a different candidate; re-resolve first"
        )
    refs = {
        c.candidate_ref
        for c in ([resolution.selected_candidate] + list(resolution.candidates))
        if c is not None
    }
    if selection.selected_candidate_ref not in refs:
        raise ValueError("selection is not among resolution candidates")
    records = adapter.lookup_identity(resolution) or []
    fresh_hash = current_context_hash(
        key,
        records,
        snapshot_version=getattr(adapter, "snapshot_version", ""),
        rules_version=VERIFICATION_RULES_VERSION,
    )
    if fresh_hash != selection.evidence_context_hash:
        raise ValueError(
            "evidence changed since review; re-review required"
        )
    chosen = next(
        c
        for c in ([resolution.selected_candidate] + list(resolution.candidates))
        if c is not None
        and c.candidate_ref == selection.selected_candidate_ref
    )
    review_note = "human_review %s by %s: selected %s" % (
        selection.review_id,
        selection.reviewer,
        selection.selected_candidate_ref,
    )
    effective_text = _swap_code(
        resolution.normalized_text or "",
        resolution.identifier,
        selection.corrected_identifier,
    )
    return _decide(
        resolution_status=resolution.status,
        normalized_text=effective_text,
        candidate_identifier=(
            selection.corrected_identifier or resolution.identifier
        ),
        candidate_type=(
            selection.corrected_type or chosen.candidate_type
        ),
        records=records,
        adapter=adapter,
        context=selection.context or context,
        human_disambiguation=True,
        extra_warnings=tuple(resolution.warnings) + (review_note,),
    )


def _swap_code(text: str, old: Optional[str], new: Optional[str]) -> str:
    """Substitute a reviewer-corrected identifier token in place.

    The printed code was judged wrong; the corrected code is the new
    claim. Name-key derivation then sees a clean name. If the old
    token is absent, text is returned unchanged (the gate will judge
    the result honestly).
    """
    import re as _re

    if not old or not new:
        return text
    want = _re.sub(r"[\s\-.]+", "", old.strip().upper())
    pattern = _re.compile(r"\b(?:INS|E|CI)\s*-?\s*\d+[a-z]?\b", _re.I)
    for match in pattern.finditer(text):
        if _re.sub(r"[\s\-.]+", "", match.group(0).upper()) == want:
            return text[: match.start()] + new + text[match.end():]
    return text


def _candidate_type(resolution: Resolution) -> str:
    key_candidates = [resolution.selected_candidate] + list(
        resolution.candidates
    )
    return next(
        (
            c.candidate_type
            for c in key_candidates
            if c is not None and c.candidate_type != "unknown"
        ),
        "unknown",
    )


def _decide(
    *,
    resolution_status: str,
    normalized_text: str,
    candidate_identifier: Optional[str],
    candidate_type: str,
    records: list,
    adapter: VerificationSource,
    context: Optional[str],
    human_disambiguation: bool,
    extra_warnings: tuple,
) -> VerificationDecision:
    admissible = filter_admissible(records)
    warnings: List[str] = list(extra_warnings)
    drain = getattr(adapter, "drain_notices", None)
    if callable(drain):
        warnings.extend(drain())
    field_conflicts = detect_conflicts(admissible)
    results = evaluate_gate(
        resolution_status=resolution_status,
        normalized_text=normalized_text,
        candidate_identifier=candidate_identifier,
        candidate_type=candidate_type,
        records=records,
        context=context,
        human_disambiguation=human_disambiguation,
    )
    by_rule = _details(results)
    reason = _join_reasons(results)
    if field_conflicts:
        reason += "; provider field conflict on " + ", ".join(
            sorted({c.field for c in field_conflicts})
        )
    if getattr(adapter, "snapshot_version", "") and (
        getattr(adapter, "rules_version", None)
        not in (None, VERIFICATION_RULES_VERSION)
    ):
        warnings.append("snapshot_rules_version_mismatch")

    def decide(
        status: str,
        confidence: str,
        extra_reason: str = "",
        entity_id: Optional[str] = None,
    ) -> VerificationDecision:
        full_reason = reason + ("; " + extra_reason if extra_reason else "")
        adapter_rules = getattr(adapter, "rules_version", None)
        if status == STATUS_VERIFIED and adapter_rules not in (
            None,
            VERIFICATION_RULES_VERSION,
        ):
            # Records curated under different rules cannot verify
            # under current rules: downgrade, never silently accept.
            status = STATUS_PROVISIONAL
            confidence = CONF_LOW
            full_reason += "; snapshot rules version mismatch"
        return VerificationDecision(
            status=status,
            identity_confidence=confidence,
            gate_results=tuple(results),
            claims=_build_claims(
                status, confidence, name_agreeing_all(admissible)
            ),
            evidence=_identity_evidence(
                entity_id or "", agreeing_records(admissible)
            ),
            source_refs=_source_refs(admissible or records),
            reason=full_reason,
            warnings=tuple(warnings),
            rules_version=VERIFICATION_RULES_VERSION,
            snapshot_version=getattr(adapter, "snapshot_version", ""),
            entity_id=entity_id,
        )

    if field_conflicts:
        # Providers disagree on identity-adjacent fields. Disagreement
        # trumps any passing gate: surfacing conflicted is the only
        # honest outcome (Stage-6 conflict case 6).
        return decide(
            STATUS_CONFLICTED,
            CONF_CONFLICTED,
            "provider field disagreement",
        )

    if all(g.result == PASS for g in results):
        agreed = agreeing_records(admissible)
        entity_id = agreed[0].entity.entity_id if agreed else None
        decision = decide(
            STATUS_VERIFIED, CONF_HIGH, entity_id=entity_id
        )
        return _with_field_claims(decision, agreed)

    v1 = by_rule["V1_admissible_candidate"]
    if v1.result == FAIL and resolution_status == "ambiguous":
        return decide(
            STATUS_PROVISIONAL,
            CONF_LOW,
            "ambiguous candidate requires human disambiguation",
        )
    if v1.result == FAIL:
        if not records:
            return decide(STATUS_UNKNOWN, CONF_UNKNOWN, "no source found")
        return decide(
            STATUS_UNVERIFIED, CONF_UNKNOWN, "candidate inadmissible"
        )

    v3 = by_rule["V3_identity_agreement"]
    v4 = by_rule["V4_identifier_validation"]
    contradictory = v3.result == FAIL and (
        _has_identifier_conflict(
            normalized_text, candidate_identifier, admissible
        )
    )
    if v4.result == FAIL and _explicit_mismatch(
        normalized_text, candidate_identifier, admissible
    ):
        contradictory = True
    if contradictory:
        return decide(
            STATUS_CONFLICTED,
            CONF_CONFLICTED,
            "sources disagree on identity",
        )

    if by_rule["V2_authoritative_source"].result == FAIL:
        return decide(STATUS_UNKNOWN, CONF_UNKNOWN, "no source records")
    if by_rule["V6_source_appropriateness"].result == FAIL:
        return decide(
            STATUS_UNVERIFIED, CONF_UNKNOWN, "no admissible source"
        )
    if by_rule["V5_entity_type_validation"].result == FAIL:
        return decide(
            STATUS_UNVERIFIED, CONF_UNKNOWN, "entity type blocked"
        )
    if v4.result == FAIL:
        return decide(
            STATUS_UNVERIFIED, CONF_UNKNOWN, "identifier integrity failed"
        )
    if by_rule["V7_context_checks"].result == FAIL:
        return decide(
            STATUS_PROVISIONAL, CONF_LOW, "context contradiction"
        )
    confidence = (
        CONF_MEDIUM if v3.result == PASS else CONF_LOW
    )
    return decide(STATUS_PROVISIONAL, confidence, "gate incomplete")


def agreeing_records(
    records: Sequence[SourceRecord],
) -> List[SourceRecord]:
    """Admissible records in deterministic entity order."""
    return sorted(records, key=lambda r: r.entity.entity_id)


def name_agreeing_all(
    records: Sequence[SourceRecord],
) -> List[SourceRecord]:
    """Alias kept for claim-building readability."""
    return agreeing_records(records)


def _has_identifier_conflict(
    normalized_text: str,
    identifier: Optional[str],
    records: Sequence[SourceRecord],
) -> bool:
    return _explicit_mismatch(normalized_text, identifier, records)


def _explicit_mismatch(
    normalized_text: str,
    identifier: Optional[str],
    records: Sequence[SourceRecord],
) -> bool:
    """True when two claims genuinely disagree (not merely absent).

    Mismatch means: the identifier is carried by some record(s) while
    the name is agreed by other record(s), with no record agreeing on
    both. Absence of evidence on either side is not a mismatch.
    """
    if not identifier:
        return False
    from app.services.verification.gate import derive_name_key

    key = derive_name_key(normalized_text or "", identifier)
    id_ids = {
        r.entity.entity_id
        for r in identifier_agreeing(identifier, records)
    }
    name_ids = {
        r.entity.entity_id for r in name_agreeing(key, records)
    }
    return bool(id_ids) and bool(name_ids) and not (id_ids & name_ids)


def _build_claims(
    status: str, confidence: str, records: Sequence[SourceRecord]
) -> Tuple[IdentityClaim, ...]:
    if status != STATUS_VERIFIED or not records:
        primary = records[0] if records else None
        return (
            IdentityClaim(
                entity_id=(
                    primary.entity.entity_id if primary else ""
                ),
                field="identity",
                value=(
                    primary.entity.preferred_name if primary else ""
                ),
                status=status,
                confidence=confidence,
                evidence=tuple(r.source for r in records),
            ),
        )
    entity = records[0].entity
    return (
        IdentityClaim(
            entity_id=entity.entity_id,
            field="identity",
            value=entity.preferred_name,
            status=status,
            confidence=confidence,
            evidence=tuple(r.source for r in records),
        ),
    )


def _with_field_claims(
    decision: VerificationDecision, records: Sequence[SourceRecord]
) -> VerificationDecision:
    """Attach stored field claims for a verified identity.

    Field values come verbatim from snapshot evidence -- the engine
    never computes or invents them. Non-verified decisions carry no
    field claims at all.
    """
    if decision.status != STATUS_VERIFIED or not records:
        return decision
    entity = records[0].entity
    claims = list(decision.claims)
    evidence = list(decision.evidence)
    for item in entity.fields:
        claims.append(
            IdentityClaim(
                entity_id=entity.entity_id,
                field=item.field,
                value=item.value,
                status=STATUS_VERIFIED,
                confidence=CONF_HIGH,
                evidence=(item.source,),
            )
        )
        evidence.append(item)
    return VerificationDecision(
        status=decision.status,
        identity_confidence=decision.identity_confidence,
        gate_results=decision.gate_results,
        claims=tuple(claims),
        evidence=tuple(evidence),
        source_refs=decision.source_refs,
        reason=decision.reason,
        warnings=decision.warnings,
        rules_version=decision.rules_version,
        snapshot_version=decision.snapshot_version,
        entity_id=decision.entity_id,
    )
