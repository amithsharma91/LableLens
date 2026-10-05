"""Review request/response schemas (Stage 11 API).

The reviewer identity never comes from the client: routes derive it
from the authenticated principal. Approval scope is identity-only;
attempts to approve other fields fail validation here.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Literal, Optional

DecisionType = Literal[
    "confirm_identity",
    "reject_identity",
    "request_more_evidence",
    "mark_unknown",
]


class ReviewSummaryResponse(BaseModel):
    review_id: str
    candidate_key: str
    verification_status: str
    priority: int
    status: str
    reviewer: Optional[str] = None


class ReviewEventResponse(BaseModel):
    event_id: str
    event_type: str
    actor: str
    reason: str
    previous_state: str = ""
    new_state: str
    timestamp: Optional[float] = None


class ReviewDetailResponse(BaseModel):
    review: ReviewSummaryResponse
    raw_text: str = ""
    normalized_text: str = ""
    identifier: Optional[str] = None
    evidence_hash: str = ""
    events: List[ReviewEventResponse] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: DecisionType
    reason: str = Field(min_length=1, max_length=2000)
    selected_candidate_ref: Optional[str] = Field(
        default=None, min_length=1, max_length=200)
    corrected_identifier: Optional[str] = Field(
        default=None, min_length=1, max_length=100)
    corrected_type: Optional[str] = Field(
        default=None, min_length=1, max_length=50)
    context: Optional[str] = Field(
        default=None, min_length=1, max_length=200)
    approved_fields: List[str] = Field(default_factory=lambda: ["identity"])

    def model_post_init(self, _context) -> None:
        allowed = {"identity"}
        unknown = set(self.approved_fields) - allowed
        if unknown:
            raise ValueError(
                "unapprovable fields: %s" % sorted(unknown))
