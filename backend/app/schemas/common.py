from pydantic import BaseModel
from typing import Any, Dict, Optional

class MetaResponse(BaseModel):
    request_id: Optional[str] = None
    api_version: str = "v1"

class HealthData(BaseModel):
    status: str
    version: str

class HealthResponse(BaseModel):
    data: HealthData
    meta: Optional[MetaResponse] = None
