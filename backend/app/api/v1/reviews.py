"""Review endpoints (Stage 11 API).

Reviewer identity always comes from the authenticated principal:
request bodies carry decisions, reasons, and candidate references,
never the trusted reviewer identity. Approval scope stays
identity-only (schema-validated). Events are read-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.api.auth import Principal, require_authenticated, require_reviewer
from app.api.dependencies import review_service
from app.api.errors import ERROR_RESPONSES, ApiError
from app.schemas.common import (
    CollectionMeta,
    MetaResponse,
    PaginationMeta,
)
from app.schemas.reviews import (
    DecisionRequest,
    ReviewDetailResponse,
    ReviewEventResponse,
    ReviewSummaryResponse,
)
from app.services import errors as _service_errors

router = APIRouter()

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _meta(request: Request) -> MetaResponse:
    return MetaResponse(
        request_id=getattr(request.state, "request_id", None))


def _services(request: Request):
    """Request-scoped review service (see ServiceScopeMiddleware)."""
    return review_service(request)


def _summary(row: dict) -> ReviewSummaryResponse:
    return ReviewSummaryResponse(
        review_id=row["id"],
        candidate_key=row.get("candidate_key", ""),
        verification_status=row.get("verification_status", ""),
        priority=int(row.get("priority", 99)),
        status=row.get("status", ""),
        reviewer=row.get("reviewer"),
    )


@router.get(
    "/reviews/pending",
    response_model=dict,
    summary="Open reviews in deterministic priority order",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def list_pending(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    principal: Principal = Depends(require_authenticated),
):
    """Bounded pagination; repository order is authoritative."""
    service = _services(request)
    result = await service.list_pending(
        page=page, page_size=page_size)
    return {
        "data": [_summary(r).model_dump() for r in result["items"]],
        "meta": CollectionMeta(
            request_id=getattr(request.state, "request_id", None),
            pagination=PaginationMeta(
                page=page, page_size=page_size, total=result["total"]),
        ).model_dump(),
    }


@router.get(
    "/reviews/{review_id}",
    response_model=dict,
    summary="One review with its event history",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def get_review(
    review_id: str,
    request: Request,
    principal: Principal = Depends(require_authenticated),
):
    """Review plus append-only events (read-only)."""
    service = _services(request)
    try:
        result = await service.get(review_id)
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "review not found")
    row = result["review"]
    response = ReviewDetailResponse(
        review=_summary(row),
        raw_text=row.get("raw_text", ""),
        normalized_text=row.get("normalized_text", ""),
        identifier=row.get("identifier"),
        evidence_hash=row.get("evidence_hash", ""),
        events=[
            ReviewEventResponse(
                event_id=e["id"],
                event_type=e.get("event_type", ""),
                actor=e.get("actor", ""),
                reason=e.get("reason", ""),
                previous_state=e.get("previous_state") or "",
                new_state=e.get("new_state", ""),
                timestamp=None,
            )
            for e in result["events"]
        ],
    )
    return {"data": response.model_dump(), "meta": _meta(request).model_dump()}


@router.post(
    "/reviews/{review_id}/claim",
    response_model=dict,
    summary="Claim a queued review as the authenticated reviewer",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def claim_review(
    review_id: str,
    request: Request,
    principal: Principal = Depends(require_reviewer),
):
    """Reviewer identity comes from authentication, never the body."""
    service = _services(request)
    try:
        result = await service.claim(review_id, principal)
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "review not found")
    except _service_errors.ConflictError as exc:
        raise ApiError(409, "CONFLICT", str(exc))
    row = result["review"]
    return {
        "data": _summary(row).model_dump(),
        "meta": _meta(request).model_dump(),
    }


@router.post(
    "/reviews/{review_id}/decision",
    response_model=dict,
    summary="Record a reasoned review decision",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def record_decision(
    review_id: str,
    payload: DecisionRequest,
    request: Request,
    principal: Principal = Depends(require_reviewer),
):
    """Validated by Stage-9 rules; confirmations re-verify via V1-V7."""
    service = _services(request)
    try:
        result = await service.decide(
            review_id, payload.model_dump(), principal)
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "review not found")
    except _service_errors.ConflictError as exc:
        raise ApiError(409, "CONFLICT", str(exc))
    except _service_errors.MissingEntityError as exc:
        raise ApiError(422, "ENTITY_NOT_FOUND", str(exc))
    except _service_errors.ServiceError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc))
    data = {
        "review_id": result.get("review_id", review_id),
        "status": result.get("status") or result.get("review", {}).get(
            "status", ""),
    }
    if "decision" in result:
        data["decision"] = result["decision"]
    return {"data": data, "meta": _meta(request).model_dump()}
