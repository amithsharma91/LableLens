"""Verification source adapters."""

from app.services.verification.adapters.base import VerificationSource
from app.services.verification.adapters.manual import ManualAdapter
from app.services.verification.adapters.snapshot import (
    SnapshotAdapter,
    SnapshotError,
)

__all__ = [
    "ManualAdapter",
    "SnapshotAdapter",
    "SnapshotError",
    "VerificationSource",
]
