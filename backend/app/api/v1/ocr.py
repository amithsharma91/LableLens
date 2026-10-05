"""OCR run endpoints (Stage 16 API).

Four operations over immutable OCR runs: ingest an extraction,
read it back, record one human correction, and analyze the
corrected-or-raw text through the frozen pipeline. This layer
never normalizes, resolves, verifies, or enriches text; analysis
delegates to the OCR service, which reuses the observation path.

Rate limits reuse the observation budgets: ingesting a run costs
what creating observations costs, and analyzing a run costs what
analyzing an observation costs. No new budget dimensions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.auth import Principal, require_authenticated
from app.api.dependencies import ocr_service
from app.api.errors import ERROR_RESPONSES, ApiError
from app.api.limits import limited
from app.schemas.common import MetaResponse
from app.schemas.ocr import OCRCorrectionRequest, OCRIngestRequest
from app.services import errors as _service_errors
from app.services.ocr_provider import OCRResult, ProviderFailure
from app.services.rate_limit import RateLimitAction

router = APIRouter()


def _meta(request: Request) -> MetaResponse:
    return MetaResponse(
        request_id=getattr(request.state, "request_id", None))


def _service(request: Request):
    """Request-scoped OCR service (see ServiceScopeMiddleware)."""
    return ocr_service(request)


def _run_view(run: dict, correction=None) -> dict:
    return {
        "run_id": str(run["id"]),
        "document_id": run.get("document_id"),
        "provider": run.get("provider"),
        "provider_version": run.get("provider_version"),
        "ocr_confidence": run.get("ocr_confidence"),
        "raw_text": run.get("raw_text"),
        "corrected_text": (
            correction.get("corrected_text") if correction else None
        ),
        "created_at": (
            run.get("created_at").isoformat()
            if run.get("created_at") is not None else None
        ),
    }


@router.post(
    "/ocr/runs",
    response_model=dict,
    status_code=201,
    summary="Record one OCR extraction run",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        422: ERROR_RESPONSES[422],
        429: ERROR_RESPONSES[429],
        500: ERROR_RESPONSES[500],
        503: ERROR_RESPONSES[503],
    },
)
async def create_ocr_run(
    payload: OCRIngestRequest,
    request: Request,
    principal: Principal = Depends(
        limited(RateLimitAction.OBSERVATION_CREATE)
    ),
):
    """Persist an OCR result; no parsing or analysis happens here."""
    service = _service(request)
    try:
        if payload.raw_text is not None:
            run = await service.register_result(
                OCRResult(
                    document_id=payload.document_id,
                    provider=payload.provider,
                    raw_text=payload.raw_text,
                    provider_version=payload.provider_version,
                    ocr_confidence=payload.ocr_confidence,
                    page_metadata=payload.page_metadata or {},
                    source_reference=payload.source_reference or {},
                ),
                run_id=(
                    str(payload.run_id)
                    if payload.run_id is not None else None
                ),
                owner=principal.subject,
                role="service",
            )
        else:
            run = await service.extract_with(
                payload.provider,
                payload.document_id,
                document_locator=payload.document_locator,
                run_id=(
                    str(payload.run_id)
                    if payload.run_id is not None else None
                ),
                owner=principal.subject,
                role="service",
            )
    except ProviderFailure as exc:
        raise ApiError(503, "OCR_PROVIDER_UNAVAILABLE", str(exc))
    except _service_errors.ServiceError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc))
    data = _run_view(run)
    return {"data": data, "meta": _meta(request).model_dump()}


@router.get(
    "/ocr/runs/{run_id}",
    response_model=dict,
    summary="Read one OCR run with its correction and observations",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        500: ERROR_RESPONSES[500],
    },
)
async def get_ocr_run(
    run_id: str,
    request: Request,
    principal: Principal = Depends(require_authenticated),
):
    """OCR-layer data only: run, correction, observation links."""
    service = _service(request)
    try:
        described = await service.describe(
            run_id, owner=principal.subject, role="service")
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "ocr run not found")
    data = _run_view(described["run"], described["correction"])
    data["correction_reason"] = (
        described["correction"].get("reason")
        if described["correction"] else None
    )
    data["observations"] = described["observations"]
    return {"data": data, "meta": _meta(request).model_dump()}


@router.post(
    "/ocr/runs/{run_id}/correction",
    response_model=dict,
    summary="Record one human correction of an OCR run",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def correct_ocr_run(
    run_id: str,
    payload: OCRCorrectionRequest,
    request: Request,
    principal: Principal = Depends(require_authenticated),
):
    """Store the revision separately; raw OCR stays immutable."""
    service = _service(request)
    try:
        correction = await service.correct_run(
            run_id,
            corrected_text=payload.corrected_text,
            reason=payload.reason,
            actor=principal.reviewer_id,
            owner=principal.subject,
            role="service",
        )
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "ocr run not found")
    except _service_errors.ServiceError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc))
    data = {
        "run_id": run_id,
        "corrected_text": correction.get("corrected_text"),
        "reason": correction.get("reason"),
        "actor": correction.get("actor"),
    }
    return {"data": data, "meta": _meta(request).model_dump()}


@router.post(
    "/ocr/runs/{run_id}/analyze",
    response_model=dict,
    summary="Observe and analyze an OCR run's corrected-or-raw text",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        429: ERROR_RESPONSES[429],
        500: ERROR_RESPONSES[500],
    },
)
async def analyze_ocr_run(
    run_id: str,
    request: Request,
    principal: Principal = Depends(
        limited(RateLimitAction.OBSERVATION_ANALYZE)
    ),
):
    """Parse, normalize, resolve, and verify via the frozen pipeline.

    Empty or ingredient-free text returns a warning outcome with no
    observations -- never a crash, never an invented entity.
    """
    service = _service(request)
    try:
        result = await service.analyze_run(
            run_id, owner=principal.subject, role="service")
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "ocr run not found")
    except _service_errors.ServiceError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc))
    items = []
    for item in result["items"]:
        items.append({
            "observation_id": item["observation_id"],
            "status": item["decision"].get("status"),
            "identity_confidence": item["decision"].get(
                "identity_confidence"),
        })
    data = {
        "run_id": result["run_id"],
        "corrected": result["corrected"],
        "warnings": result["warnings"],
        "items": items,
    }
    return {"data": data, "meta": _meta(request).model_dump()}
