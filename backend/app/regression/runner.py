"""Deterministic real-label regression runner (Stage 13).

One label runs the full trust pipeline through the existing service
layer, unchanged:

    LabelInput -> create (parse + persist observations)
      -> correct (only where the fixture documents a correction)
      -> analyze per observation (normalize + resolve + verify + persist)
      -> compare against the fixture expectations
      -> metrics + provenance trace

Identity is stable across runs: the scan id and every observation id
derive from the label id, and normalization/match/decision rows use
the existing deterministic ids, so a repeated run reuses rows instead
of duplicating them. The canonical registry is read-only here: the
runner never registers entities, and the run fails if the entity
table changes size.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.regression.label_input import LabelInput
from app.services.observation_service import ObservationService

__all__ = ["LabelRun", "run_label"]


class LabelRun:
    """Recorded outcome of one label's pipeline run."""

    def __init__(self, label_id: str) -> None:
        self.label_id = label_id
        self.scan_id: str = ""
        self.observations: List[Dict[str, Any]] = []
        self.ingredient_results: List[Dict[str, Any]] = []
        self.correction: Optional[Dict[str, Any]] = None
        self.mismatches: List[str] = []
        self.provenance: List[Dict[str, Any]] = []
        self.expected_unknowns: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label_id": self.label_id,
            "scan_id": self.scan_id,
            "observations": self.observations,
            "ingredient_results": self.ingredient_results,
            "correction": self.correction,
            "mismatches": self.mismatches,
            "provenance": self.provenance,
            "expected_unknowns": self.expected_unknowns,
        }


async def run_label(
    service: ObservationService,
    label: LabelInput,
    fixture: Dict[str, Any],
    *,
    role: str = "service",
) -> LabelRun:
    """Run one fixture through create/correct/analyze and compare."""
    run = LabelRun(label.label_id)
    run.expected_unknowns = list(fixture.get("expected_unknowns", []))
    created = await service.create(
        label.raw_text,
        scan_id=label.scan_id,
        observation_ids=[
            label.observation_id(position)
            for position in range(_node_count(service, label))
        ],
        source_type=(
            label.input_method
            if label.input_method in ("ocr", "manual", "user_entered")
            else "ocr"
        ),
        role=role,
    )
    run.scan_id = created["scan_id"]
    run.observations = [
        {
            "observation_id": item["observation_id"],
            "sequence_number": position,
            "raw_text": item["raw_text"],
            "normalized_text": item["normalized_text"],
        }
        for position, item in enumerate(created["items"])
    ]

    expected = {
        item["sequence"]: item
        for item in fixture.get("expected_ingredients", [])
    }
    correction = fixture.get("correction")
    if correction:
        # The correction case is its own observation, created from
        # the documented raw reading (not from the label text), so
        # the raw/corrected separation is exercised for real.
        correction_id = label.correction_observation_id()
        created_correction = await service.create(
            correction["raw_observed"],
            scan_id=label.scan_id,
            observation_ids=[correction_id],
            source_type="manual",
            role=role,
        )
        created_item = created_correction["items"][0]
        if created_item["raw_text"] != correction["raw_observed"]:
            run.mismatches.append(
                "correction raw text was not preserved verbatim")
        corrected = await service.correct(
            correction_id,
            corrected_text=correction["corrected_display"],
            reason=correction["reason"],
            role=role,
        )
        analyzed_correction = await service.analyze(
            correction_id, role=role)
        corrected_resolution = analyzed_correction["resolution"]
        run.correction = {
            "observation_id": correction_id,
            "raw_observed": correction["raw_observed"],
            "raw_preserved": created_item["raw_text"],
            "original_text": corrected["observation"].get(
                "original_text"),
            "display_text": corrected["observation"].get(
                "display_text"),
            "user_corrected": corrected["observation"].get(
                "user_corrected"),
            "normalized_text": corrected["normalized_text"],
            "match_status": corrected_resolution.get("match_status"),
            "verification_status": analyzed_correction["decision"].get(
                "status"),
        }
        want_sequence = expected.get(correction["applies_to_sequence"])
        if want_sequence is not None and (
            corrected["normalized_text"]
            != want_sequence.get("normalized")
        ):
            run.mismatches.append(
                "correction normalized %r != expected %r" % (
                    corrected["normalized_text"],
                    want_sequence.get("normalized")))

    for position, item in enumerate(created["items"]):
        analyzed = await service.analyze(
            item["observation_id"], role=role)
        resolution = analyzed["resolution"]
        decision = analyzed["decision"]
        selected = resolution.get("entity") or {}
        result = {
            "sequence": position,
            "observation_id": item["observation_id"],
            "raw_text": item["raw_text"],
            "normalized_text": resolution.get("normalized_text"),
            "match_status": resolution.get("match_status"),
            "identity_confidence": resolution.get(
                "identity_confidence"),
            "entity_ref": selected.get("candidate_ref"),
            "decision_id": analyzed.get("decision_id")
            or (analyzed.get("stored") or {}).get("id"),
            "match_id": analyzed.get("match_id"),
            "verification_status": decision.get("status"),
            "verification_confidence": decision.get(
                "identity_confidence"),
        }
        run.ingredient_results.append(result)
        want = expected.get(position)
        if want is None:
            run.mismatches.append(
                "sequence %d: no expectation recorded" % position)
            continue
        run.mismatches.extend(_compare(position, want, result))
        run.provenance.append({
            "label_id": label.label_id,
            "sequence": position,
            "observation_id": result["observation_id"],
            "match_id": result["match_id"],
            "decision_id": result["decision_id"],
            "entity_ref": result["entity_ref"],
        })

    if len(created["items"]) != len(expected):
        run.mismatches.append(
            "ingredient count %d != expected %d"
            % (len(created["items"]), len(expected)))
    return run


def _node_count(service: ObservationService, label: LabelInput) -> int:
    from app.services.ingredient_parser import parse_label_ingredients

    return len(parse_label_ingredients(label.raw_text).nodes)


# Fixture key -> pipeline result key. Fixtures use short names;
# results use the pipeline's own field names.
_COMPARE_FIELDS = (
    ("raw", "raw_text"),
    ("normalized", "normalized_text"),
    ("match_status", "match_status"),
    ("identity_confidence", "identity_confidence"),
    ("entity_ref", "entity_ref"),
    ("verification_status", "verification_status"),
    ("verification_confidence", "verification_confidence"),
)


def _compare(
    position: int, want: Dict[str, Any], got: Dict[str, Any]
) -> List[str]:
    mismatches = []
    for fixture_key, result_key in _COMPARE_FIELDS:
        if want.get(fixture_key) != got.get(result_key):
            mismatches.append(
                "sequence %d field %s: expected %r, got %r" % (
                    position, fixture_key, want.get(fixture_key),
                    got.get(result_key)))
    return mismatches
