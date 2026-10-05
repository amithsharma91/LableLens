"""Verification/claim/evidence response schemas (Stage 11 API).

Responses distinguish verification status, confidence, rule and
snapshot versions, gate verdicts, per-claim states, and evidence
provenance. No internal repository rows leak: every response is an
explicit public projection.
"""

from pydantic import BaseModel, Field
from typing import Any, List, Optional


class GateResultResponse(BaseModel):
    rule_id: str
    result: str
    detail: str


class ClaimResponse(BaseModel):
    claim_id: str
    entity_id: Optional[str] = None
    field: str = ""
    value: Any = None
    claim_type: Optional[str] = None
    status: str
    confidence: str


class EvidenceResponse(BaseModel):
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    provider: Optional[str] = None
    field: Optional[str] = None
    source_value: Optional[str] = None
    support_type: Optional[str] = None
    support_strength: Optional[str] = None
    locator: Optional[str] = None
    retrieved_at: Optional[str] = None
    source_version: Optional[str] = None
    response_hash: Optional[str] = None


class ClaimDetailResponse(BaseModel):
    claim: ClaimResponse
    evidence: List[EvidenceResponse] = Field(default_factory=list)


class DecisionHistoryItem(BaseModel):
    id: str
    status: str
    identity_confidence: str


class VerificationDetailResponse(BaseModel):
    decision_id: str
    status: str
    identity_confidence: str
    rules_version: str
    snapshot_version: str
    gate_results: List[GateResultResponse] = Field(default_factory=list)
    reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    claims: List[ClaimDetailResponse] = Field(default_factory=list)
    history: List[DecisionHistoryItem] = Field(default_factory=list)


class CandidateAlternativeResponse(BaseModel):
    candidate_ref: Optional[str] = None
    display_name: Optional[str] = None
    match_method: Optional[str] = None
    reason: Optional[str] = None


class SelectedCandidateResponse(BaseModel):
    candidate_ref: Optional[str] = None
    display_name: Optional[str] = None
    match_method: Optional[str] = None


class ResolutionResponse(BaseModel):
    raw_text: str
    normalized_text: str
    normalization_id: Optional[str] = None
    match_status: str
    identity_confidence: str
    entity: Optional[SelectedCandidateResponse] = None
    alternatives: List[CandidateAlternativeResponse] = Field(
        default_factory=list)


class AnalysisResponse(BaseModel):
    observation_id: str
    match_id: str
    resolution: ResolutionResponse
    decision_id: str
    status: str
    identity_confidence: str
    review_id: Optional[str] = None
