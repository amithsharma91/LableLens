"""Real-label input boundary (Stage 13 regression slice).

`LabelInput` is the smallest typed abstraction that feeds a real-label
record into the backend pipeline. It carries the raw ingredient text
exactly as observed plus where it came from -- never a judgment about
what the text means. Parsing, normalization, resolution, verification,
and review all happen downstream, unchanged.

No AI, no OCR inference, no provider calls. Fixture text is untrusted
data: the pipeline must persist it verbatim and must never execute,
import, or promote it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
import uuid

__all__ = ["LabelInput", "INPUT_METHODS", "label_namespace"]

# Source-type vocabulary shared with the pipeline (DATA_PIPELINE §2).
INPUT_METHODS = ("ocr", "manual", "user_entered", "user_corrected")


def label_namespace(label_id: str) -> uuid.UUID:
    """Stable namespace for one label's deterministic run ids."""
    return uuid.uuid5(uuid.NAMESPACE_URL, "labellens-label:%s" % label_id)


def observation_id_for(label_id: str, sequence_number: int) -> str:
    """Stable observation id for one ingredient position.

    Re-running the same label reuses the row instead of duplicating
    it; a genuinely new run is a new label id, never a mutated one.
    """
    return str(uuid.uuid5(
        label_namespace(label_id),
        "observation:%d" % sequence_number,
    ))


def scan_id_for(label_id: str) -> str:
    """Stable scan id grouping one label's observations."""
    return str(uuid.uuid5(
        label_namespace(label_id), "scan:%s" % label_id))


@dataclass(frozen=True)
class LabelInput:
    """One real-label record at the pipeline input boundary."""

    label_id: str
    raw_text: str
    input_method: str
    source_reference: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.label_id.strip():
            raise ValueError("label_id is required")
        if not self.raw_text.strip():
            raise ValueError("raw_text is required")
        if self.input_method not in INPUT_METHODS:
            raise ValueError(
                "input_method must be one of %s" % (", ".join(INPUT_METHODS)))
        for key in ("source_id", "retrieved_at"):
            if key not in self.source_reference:
                raise ValueError(
                    "source_reference must include %s" % key)

    @property
    def scan_id(self) -> str:
        return scan_id_for(self.label_id)

    def observation_id(self, sequence_number: int) -> str:
        return observation_id_for(self.label_id, sequence_number)

    def correction_observation_id(self) -> str:
        """Stable id for the fixture's documented correction case."""
        return str(uuid.uuid5(
            label_namespace(self.label_id), "observation:correction"))

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "LabelInput":
        """Build from a fixture mapping; unknown keys are refused.

        Fixture text is untrusted: extra keys (for example anything
        resembling an identity, role, or instruction field) raise
        instead of being silently carried into the pipeline.
        """
        known = {"label_id", "raw_text", "input_method",
                 "source_reference"}
        extra = set(payload) - known
        if extra:
            raise ValueError(
                "unknown label input fields: %s" % sorted(extra))
        reference = payload.get("source_reference") or {}
        if not isinstance(reference, dict):
            raise ValueError("source_reference must be a mapping")
        return cls(
            label_id=str(payload.get("label_id", "")),
            raw_text=str(payload.get("raw_text", "")),
            input_method=str(payload.get("input_method", "")),
            source_reference=dict(reference),
        )
