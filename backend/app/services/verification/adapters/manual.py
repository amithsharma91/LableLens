"""Manual verification path (stub).

No human-review mechanism exists yet, so this adapter is explicitly
unavailable: it returns no records and never approves anything. It
exists so the orchestrator's multi-adapter fan-out has a stable slot
for the future manual path without any fake-approval behavior.
"""

from __future__ import annotations

from typing import List

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.models import SourceRecord

__all__ = ["ManualAdapter"]


class ManualAdapter(VerificationSource):
    """Unavailable stub. Never verifies, never approves."""

    adapter_id = "manual_review"
    adapter_version = "1.0.0"
    available = False

    def lookup_identity(
        self, resolution: Resolution
    ) -> List[SourceRecord]:
        """Always empty: no review queue exists to consult."""
        return []
