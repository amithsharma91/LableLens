from pydantic import BaseModel, Field
from typing import Any, Dict, Optional


class MetaResponse(BaseModel):
    request_id: Optional[str] = None
    api_version: str = "v1"


class PaginationMeta(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0


class CollectionMeta(MetaResponse):
    pagination: PaginationMeta = Field(default_factory=PaginationMeta)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
    meta: MetaResponse = Field(default_factory=MetaResponse)


class HealthData(BaseModel):
    status: str
    version: str


class HealthResponse(BaseModel):
    data: HealthData
    meta: Optional[MetaResponse] = None
