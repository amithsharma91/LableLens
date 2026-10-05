"""Observation endpoints (Stage 11 API).

Raw label text is accepted verbatim and stored verbatim: this layer
never normalizes, corrects, or enriches it. Analysis runs the frozen
pipeline (parse/normalize/resolve/verify) server-side.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.api.auth import Principal, require_authenticated
from app.api.dependencies import observation_service
from app.api.errors import ERROR_RESPONSES, ApiError
from app.api.limits import limited
from app.schemas.common import (
    CollectionMeta,
    MetaResponse,
    PaginationMeta,
)
from app.schemas.observations import (
    CreateObservationRequest,
    IngredientNodeResponse,
    ObservationDetailResponse,
    ObservationResponse,
)
from app.schemas.verification import (
    AnalysisResponse,
    CandidateAlternativeResponse,
    ResolutionResponse,
    SelectedCandidateResponse,
)
from app.services import errors as _service_errors
from app.services.rate_limit import RateLimitAction

router = APIRouter()


def _meta(request: Request) -> MetaResponse:
    return MetaResponse(
        request_id=getattr(request.state, "request_id", None))


def _node(node: dict) -> IngredientNodeResponse:
    return IngredientNodeResponse(
        node_id=node.get("id", ""),
        raw_text=node.get("rawText", ""),
        name=node.get("name", ""),
        normalized_name=node.get("normalizedName", ""),
        depth=int(node.get("depth", 0) or 0),
        position=int(node.get("position", 0) or 0),
        percentage=node.get("percentage"),
        identifier=node.get("identifier"),
        children=[_node(c) for c in node.get("children", [])],
    )


def _service(request: Request):
    """Request-scoped observation service (see ServiceScopeMiddleware)."""
    return observation_service(request)


@router.post(
    "/observations",
    response_model=dict,
    status_code=201,
    summary="Create observations from raw label text",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        422: ERROR_RESPONSES[422],
        429: ERROR_RESPONSES[429],
        500: ERROR_RESPONSES[500],
    },
)
async def create_observation(
    payload: CreateObservationRequest,
    request: Request,
    principal: Principal = Depends(
        limited(RateLimitAction.OBSERVATION_CREATE)
    ),
):
    """Parse raw text; persist one observation per top-level node."""
    service = _service(request)
    try:
        result = await service.create(
            payload.raw_text,
            scan_id=str(payload.scan_id) if payload.scan_id else None,
            observation_id=(
                str(payload.observation_id)
                if payload.observation_id else None
            ),
        )
    except _service_errors.ServiceError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc))
    items = [
        ObservationResponse(
            observation_id=uuid.UUID(item["observation_id"]),
            scan_id=uuid.UUID(item["scan_id"]),
            raw_text=item["raw_text"],
            normalized_text=item["normalized_text"],
            status=item["status"],
            tree=[_node(n) for n in item["tree"]],
        )
        for item in result["items"]
    ]
    return {
        "data": [i.model_dump() for i in items],
        "meta": CollectionMeta(
            request_id=getattr(request.state, "request_id", None),
            pagination=PaginationMeta(
                page=1, page_size=len(items), total=len(items)),
        ).model_dump(),
    }


@router.get(
    "/observations/{observation_id}",
    response_model=dict,
    summary="Retrieve one observation with its tree",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def get_observation(
    observation_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_authenticated),
):
    """Observation, normalization, and re-derived tree."""
    service = _service(request)
    try:
        result = await service.get(str(observation_id))
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "observation not found")
    response = ObservationDetailResponse(
        observation=ObservationResponse(
            observation_id=uuid.UUID(result["observation_id"]),
            scan_id=uuid.UUID(result["scan_id"]),
            raw_text=result["raw_text"],
            normalized_text=result["normalized_text"],
            status=result["status"],
            tree=[_node(n) for n in result["tree"]],
        ),
        normalization_id=None,
    )
    return {"data": response.model_dump(), "meta": _meta(request).model_dump()}


@router.post(
    "/observations/{observation_id}/analyze",
    response_model=dict,
    summary="Resolve and verify one observation",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        429: ERROR_RESPONSES[429],
        500: ERROR_RESPONSES[500],
    },
)
async def analyze_observation(
    observation_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(
        limited(RateLimitAction.OBSERVATION_ANALYZE)
    ),
):
    """Run resolve + verify + persist (+ review routing)."""
    service = _service(request)
    try:
        result = await service.analyze(str(observation_id))
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "observation not found")
    except _service_errors.MissingEntityError as exc:
        raise ApiError(422, "ENTITY_NOT_FOUND", str(exc))
    except _service_errors.ServiceError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc))
    resolution = result["resolution"]
    decision = result["decision"]
    stored = result.get("stored") or {}
    selected = resolution.get("entity")
    entity = None
    if selected is not None:
        entity = SelectedCandidateResponse(
            candidate_ref=selected.get("candidate_ref"),
            display_name=selected.get("display_name"),
            match_method=selected.get("match_method"),
        )
    alternatives = [
        CandidateAlternativeResponse(
            candidate_ref=c.get("candidate_ref"),
            display_name=c.get("display_name"),
            match_method=c.get("match_method"),
            reason=c.get("reason"),
        )
        for c in resolution.get("alternatives", [])
    ]
    response = AnalysisResponse(
        observation_id=str(observation_id),
        match_id=result["match_id"],
        resolution=ResolutionResponse(
            raw_text=resolution.get("raw_text", ""),
            normalized_text=resolution.get("normalized_text", ""),
            normalization_id=resolution.get("normalization_id") or None,
            match_status=resolution.get("match_status", ""),
            identity_confidence=resolution.get(
                "identity_confidence", "UNKNOWN"),
            entity=entity,
            alternatives=alternatives,
        ),
        decision_id=stored.get("id", ""),
        status=decision.get("status", ""),
        identity_confidence=decision.get("identity_confidence", ""),
        review_id=result.get("review_id"),
    )
    return {"data": response.model_dump(), "meta": _meta(request).model_dump()}


@router.get(
    "/observations/{observation_id}/candidates",
    response_model=dict,
    summary="Resolution view for one observation",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def get_candidates(
    observation_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_authenticated),
):
    """Raw, normalized, method, status, entity, alternatives."""
    service = _service(request)
    try:
        result = await service.get_candidates(str(observation_id))
    except _service_errors.NotFoundError as exc:
        raise ApiError(404, "NOT_FOUND", str(exc))
    response = ResolutionResponse(
        raw_text=result["raw_text"],
        normalized_text=result["normalized_text"],
        normalization_id=result.get("normalization_id"),
        match_status=result["match_status"],
        identity_confidence=result["identity_confidence"],
        entity=result["entity"],
        alternatives=result["alternatives"],
    )
    return {"data": response.model_dump(), "meta": _meta(request).model_dump()}
