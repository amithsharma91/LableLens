"""Observation request/response schemas (Stage 11 API).

Raw label text is carried verbatim end to end: the API never
normalizes, corrects, or enriches it. Structure comes from the
Stage-2/4 pipeline output, not from client interpretation.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from uuid import UUID


class CreateObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(min_length=1, max_length=5000)
    scan_id: Optional[UUID] = None
    observation_id: Optional[UUID] = None


class IngredientNodeResponse(BaseModel):
    node_id: str
    raw_text: str
    name: str
    normalized_name: str
    depth: int
    position: int
    percentage: Optional[float] = None
    identifier: Optional[str] = None
    children: List["IngredientNodeResponse"] = Field(default_factory=list)


IngredientNodeResponse.model_rebuild()


class ObservationResponse(BaseModel):
    observation_id: UUID
    scan_id: UUID
    raw_text: str
    normalized_text: str
    status: str
    tree: List[IngredientNodeResponse] = Field(default_factory=list)


class ObservationDetailResponse(BaseModel):
    observation: ObservationResponse
    normalization_id: Optional[UUID] = None
