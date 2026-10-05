"""Provider-independent verification source contract.

Core verification logic depends only on ``VerificationSource``; no
vendor SDK, network client, or file format leaks past this boundary.
Adding a source means adding an implementation, never changing the
gate or the orchestrator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.services.entity_resolver import Resolution
from app.services.verification.models import SourceRecord

__all__ = ["VerificationSource"]


class VerificationSource(ABC):
    """Read-only identity/evidence lookup for the orchestrator."""

    adapter_id: str = "unspecified"
    adapter_version: str = "0"
    snapshot_version: str = ""
    available: bool = True

    def __init__(self) -> None:
        self._notices: list = []

    @abstractmethod
    def lookup_identity(
        self, resolution: Resolution
    ) -> List[SourceRecord]:
        """Return source records plausibly matching the candidate.

        Matching here is retrieval, not verification: returning a
        record asserts nothing about identity. Never raises on
        untrusted input; unknown input yields an empty list.
        """

    def _note(self, message: str) -> None:
        """Record a non-fatal operational notice for the caller."""
        if not hasattr(self, "_notices"):
            self._notices = []
        self._notices.append(message)

    def drain_notices(self) -> List[str]:
        """Collect and clear pending notices (e.g. timeouts)."""
        notices = list(getattr(self, "_notices", []))
        self._notices = []
        return notices
