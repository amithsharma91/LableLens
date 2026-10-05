from fastapi import APIRouter
from app.schemas.common import HealthResponse, HealthData

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        data=HealthData(status="ok", version="0.1.0")
    )
