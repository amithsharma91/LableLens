"""OCR provider boundary (Stage 16).

An OCR provider turns a document reference into an :class:`OCRResult`
-- transcribed text plus provenance. Providers never see chemistry:
the result carries no normalized identity, no entity, no confidence
about identity, and no evidence. Chemical confidence is produced
exclusively downstream by the canonical registry plus approved
evidence plus the frozen V1-V7 gate.

Provider selection lives outside the domain: orchestration depends
on the :class:`OCRProvider` protocol, and only the deterministic
:class:`FakeOCRProvider` ships here. No vendor SDK is imported, and
no provider secret is accepted, stored, or returned anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Protocol

__all__ = [
    "OCRDocument",
    "OCRResult",
    "OCRProvider",
    "ProviderFailure",
    "FakeOCRProvider",
]


class ProviderFailure(Exception):
    """An OCR provider failed to extract (timeout, outage, bad input).

    Raised before anything is persisted, so a provider failure can
    never leave a half-written OCR run behind. Routes translate it
    to a controlled 503; the failure carries no credentials and no
    document bytes.
    """


def _valid_confidence(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and not (value != value)  # NaN
        and 0.0 <= float(value) <= 1.0
    )


@dataclass(frozen=True)
class OCRDocument:
    """Reference to an input image/document.

    `locator` is an opaque reference (URL, storage key); `content`
    carries raw bytes in memory only when a provider needs them
    (e.g. base64 upload). Bytes are never persisted: `OCRResult`
    carries no content field, and serialization builders take only
    whitelisted scalar fields, so content cannot leak into a row.
    """

    document_id: str
    locator: Optional[str] = None
    content: Optional[bytes] = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id is required")
        if self.content is not None and not isinstance(
            self.content, (bytes, bytearray)
        ):
            raise ValueError("content must be bytes")


@dataclass(frozen=True)
class OCRResult:
    """One immutable OCR extraction plus its provenance.

    ``raw_text`` may be empty: empty OCR is a supported failure
    mode handled downstream with warnings, not a validation error
    (refusing it here would make "no text detected" unrepresentable).
    ``ocr_confidence`` describes transcription fidelity only and
    must never be read as chemical-identity confidence.
    """

    document_id: str
    provider: str
    raw_text: str
    provider_version: Optional[str] = None
    ocr_confidence: Optional[float] = None
    page_metadata: Dict[str, Any] = field(default_factory=dict)
    source_reference: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id is required")
        if not self.provider.strip():
            raise ValueError("provider is required")
        if not isinstance(self.raw_text, str):
            raise ValueError("raw_text must be a string")
        if (
            self.ocr_confidence is not None
            and not _valid_confidence(self.ocr_confidence)
        ):
            raise ValueError(
                "ocr_confidence must be a number in [0, 1]")
        if self.page_metadata is not None and not isinstance(
            self.page_metadata, dict
        ):
            raise ValueError("page_metadata must be a mapping")
        if self.source_reference is not None and not isinstance(
            self.source_reference, dict
        ):
            raise ValueError("source_reference must be a mapping")


class OCRProvider(Protocol):
    """Extract text from a document reference. Implementations are
    injected; core orchestration never names a vendor."""

    name: str

    async def extract(self, document: OCRDocument) -> OCRResult:
        """Return the extraction or raise :class:`ProviderFailure`."""
        ...  # pragma: no cover - interface only


class FakeOCRProvider:
    """Deterministic in-memory provider for tests and development.

    Maps document ids to canned results; unknown documents and
    explicitly registered failures raise :class:`ProviderFailure`
    before anything is persisted. Two instances over the same
    mapping behave identically, which is how provider independence
    is tested.
    """

    def __init__(
        self,
        results: Optional[Mapping[str, OCRResult]] = None,
        *,
        name: str = "fake-test",
        failures: Optional[List[str]] = None,
    ) -> None:
        self._results = dict(results or {})
        self._failures = set(failures or [])
        self.name = name
        self.calls: List[str] = []

    def register(self, result: OCRResult) -> None:
        self._results[result.document_id] = result

    async def extract(self, document: OCRDocument) -> OCRResult:
        self.calls.append(document.document_id)
        if document.document_id in self._failures:
            raise ProviderFailure(
                "fake provider failure for %s" % document.document_id)
        try:
            result = self._results[document.document_id]
        except KeyError:
            raise ProviderFailure(
                "no canned result for %s" % document.document_id)
        if result.provider != self.name:
            # Re-label to the extracting provider so provenance
            # always names who actually ran, never a stale label.
            return OCRResult(
                document_id=result.document_id,
                provider=self.name,
                raw_text=result.raw_text,
                provider_version=result.provider_version,
                ocr_confidence=result.ocr_confidence,
                page_metadata=dict(result.page_metadata),
                source_reference=dict(result.source_reference),
            )
        return result
