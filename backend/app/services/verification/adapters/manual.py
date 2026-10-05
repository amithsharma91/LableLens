"""Manual review path (real implementation, Stage 9).

This adapter supplies NO source evidence: ``lookup_identity`` always
returns an empty list, because human judgment is not a chemical
source and must never be fabricated into one. Its real function is
holding explicit, auditable ``ReviewSelection`` records that route
back through the frozen V1-V7 gate via ``reverify_candidate`` --
human judgment travels through verification, never around it.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.models import SourceRecord
from app.services.verification.review import ReviewSelection

__all__ = ["ManualAdapter"]


class ManualAdapter(VerificationSource):
    """Registry of human review selections (evidence-free)."""

    adapter_id = "manual_review"
    adapter_version = "2.0.0"
    available = True

    def __init__(
        self, selections: List[ReviewSelection] | None = None
    ) -> None:
        super().__init__()
        self._selections: Dict[str, ReviewSelection] = {}
        for selection in selections or []:
            self.register_selection(selection)

    def register_selection(self, selection: ReviewSelection) -> None:
        """Record an approved review selection for later reverify."""
        self._selections[selection.candidate_key] = selection

    def get_selection(
        self, candidate_key: str
    ) -> Optional[ReviewSelection]:
        """Return the registered selection for a candidate key."""
        return self._selections.get(candidate_key)

    def lookup_identity(
        self, resolution: Resolution
    ) -> List[SourceRecord]:
        """Always empty: human judgment is not source evidence."""
        return []
