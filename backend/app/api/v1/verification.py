"""Verification, claim, and evidence read endpoints (Stage 11 API).

All responses are projections of persisted rows: verification status
and confidence stay per-decision and per-claim, evidence keeps its
provenance, and history is never rewritten. Read-only: no PUT/DELETE
routes exist anywhere in this API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.auth import Principal, require_authenticated
from app.api.dependencies import services
from app.api.errors import ERROR_RESPONSES, ApiError
from app.schemas.common import MetaResponse
from app.schemas.verification import (
    CandidateAlternativeResponse,
    ClaimDetailResponse,
    ClaimResponse,
    DecisionHistoryItem,
    EvidenceResponse,
    GateResultResponse,
    ResolutionResponse,
    SelectedCandidateResponse,
    VerificationDetailResponse,
)
from app.services import errors as _service_errors

router = APIRouter()


def _meta(request: Request) -> MetaResponse:
    return MetaResponse(
        request_id=getattr(request.state, "request_id", None))


def _services(request: Request):
    """Request-scoped service bundle (see ServiceScopeMiddleware)."""
    return services(request)


def _claim_detail(item: dict) -> ClaimDetailResponse:
    claim = item["claim"]
    return ClaimDetailResponse(
        claim=ClaimResponse(
            claim_id=str(claim["id"]),
            entity_id=(
                str(claim["chemical_entity_id"])
                if claim.get("chemical_entity_id") else None
            ),
            field=claim.get("field_name") or "",
            value=claim.get("claim_value_text")
            if claim.get("claim_value_text") is not None
            else claim.get("claim_value_numeric"),
            claim_type=claim.get("claim_type"),
            status=claim.get("verification_status", ""),
            confidence=claim.get("confidence", ""),
        ),
        evidence=[
            EvidenceResponse(
                source_id=str(e.get("source_id"))
                if e.get("source_id") else None,
                source_name=e.get("source_name"),
                provider=e.get("provider"),
                field=None,
                source_value=e.get("source_value"),
                support_type=e.get("support_type"),
                support_strength=e.get("support_strength"),
                locator=e.get("source_locator"),
                retrieved_at=(
                    str(e.get("retrieved_at"))
                    if e.get("retrieved_at") else None
                ),
                source_version=e.get("source_version"),
                response_hash=e.get("response_hash"),
            )
            for e in item.get("evidence", [])
        ],
    )


@router.get(
    "/observations/{observation_id}/verification",
    response_model=dict,
    summary="Verification detail with claims, evidence, history",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def get_verification(
    observation_id: str,
    request: Request,
    principal: Principal = Depends(require_authenticated),
):
    """Status, confidence, versions, gate, claims, history."""
    service = _services(request).observations
    try:
        result = await service.get_verification(
            observation_id, owner=principal.subject)
    except _service_errors.NotFoundError as exc:
        raise ApiError(404, "NOT_FOUND", str(exc))
    decision = result["decision"]
    response = VerificationDetailResponse(
        decision_id=str(decision["id"]),
        status=decision.get("status", ""),
        identity_confidence=decision.get("identity_confidence", ""),
        rules_version=decision.get("rules_version", ""),
        snapshot_version=decision.get("snapshot_version", ""),
        gate_results=[
            GateResultResponse(
                rule_id=g.get("rule_id", ""),
                result=g.get("result", ""),
                detail=g.get("detail", ""),
            )
            for g in decision.get("gate_results") or []
        ],
        reason=decision.get("reason"),
        warnings=list(decision.get("warnings") or []),
        claims=[_claim_detail(c) for c in result["claims"]],
        history=[
            DecisionHistoryItem(
                id=str(h["id"]),
                status=h.get("status", ""),
                identity_confidence=h.get("identity_confidence", ""),
            )
            for h in result["history"]
        ],
    )
    return {"data": response.model_dump(), "meta": _meta(request).model_dump()}


@router.get(
    "/claims/{claim_id}",
    response_model=dict,
    summary="One claim with its evidence links",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def get_claim(
    claim_id: str,
    request: Request,
    principal: Principal = Depends(require_authenticated),
):
    """Claim-level state; never inherits another claim's status."""
    service = _services(request).observations
    try:
        result = await service.get_claim(claim_id)
    except _service_errors.NotFoundError:
        raise ApiError(404, "NOT_FOUND", "claim not found")
    return {
        "data": _claim_detail(result).model_dump(),
        "meta": _meta(request).model_dump(),
    }


@router.get(
    "/observations/{observation_id}/resolution",
    response_model=dict,
    summary="Alias of the candidates view (spec match shape)",
    responses={
        400: ERROR_RESPONSES[400],
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        422: ERROR_RESPONSES[422],
        500: ERROR_RESPONSES[500],
    },
)
async def get_resolution_alias(
    observation_id: str,
    request: Request,
    principal: Principal = Depends(require_authenticated),
):
    """Same data as /candidates, kept for spec-naming compatibility."""
    service = _services(request).observations
    try:
        result = await service.get_candidates(
            observation_id, owner=principal.subject)
    except _service_errors.NotFoundError as exc:
        raise ApiError(404, "NOT_FOUND", str(exc))
    entity = result.get("entity")
    response = ResolutionResponse(
        raw_text=result["raw_text"],
        normalized_text=result["normalized_text"],
        normalization_id=result.get("normalization_id"),
        match_status=result["match_status"],
        identity_confidence=result["identity_confidence"],
        entity=(
            SelectedCandidateResponse(
                candidate_ref=(entity or {}).get("candidate_ref"),
                display_name=(entity or {}).get("display_name"),
                match_method=(entity or {}).get("match_method"),
            )
            if entity is not None else None
        ),
        alternatives=[
            CandidateAlternativeResponse(
                candidate_ref=a.get("candidate_ref"),
                display_name=a.get("display_name"),
                match_method=a.get("match_method"),
                reason=a.get("reason"),
            )
            for a in result.get("alternatives", [])
        ],
    )
    return {"data": response.model_dump(), "meta": _meta(request).model_dump()}
