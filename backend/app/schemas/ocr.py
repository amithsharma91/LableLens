"""OCR run request/response schemas (Stage 16 API).

These schemas carry transcription plus provenance only: document
reference, provider label, confidence, and page metadata. No
normalized identity, no entity, no chemistry, and no evidence
passes through this layer. `extra="forbid"` everywhere, matching
the existing convention that request bodies cannot assert identity.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID


class OCRIngestRequest(BaseModel):
    """Record one OCR extraction (client text or provider run)."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=512)
    raw_text: Optional[str] = Field(default=None, max_length=20000)
    provider: str = Field(default="client", min_length=1, max_length=120)
    provider_version: Optional[str] = Field(
        default=None, max_length=120)
    ocr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    document_locator: Optional[str] = Field(
        default=None, max_length=1024)
    page_metadata: Optional[dict] = None
    source_reference: Optional[dict] = None
    run_id: Optional[UUID] = None


class OCRCorrectionRequest(BaseModel):
    """One documented human revision of an OCR run's text."""

    model_config = ConfigDict(extra="forbid")

    corrected_text: str = Field(min_length=1, max_length=20000)
    reason: str = Field(min_length=1, max_length=2000)
