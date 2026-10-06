"""Observation service: raw text in, persisted pipeline out.

Flow per top-level parser node (Stage-2 tree preserved in responses):

    raw text -> parse -> observation + normalization rows
      -> resolve (registry) -> candidates + match rows
      -> verify (adapters) -> decision + claim/evidence rows
      -> routed decisions submitted for human review

The service holds no business rules beyond orchestration: parsing,
normalization, resolution, verification, and review validation all
live in their domain modules. Persistence goes through repository
interfaces only (works with memory or Postgres bundles).
"""

from __future__ import annotations

import uuid
from typing import Optional

from app.services import errors as _errors
from app.services.entity_resolver import (
    EntityRegistry,
    InMemoryRegistry,
    resolve_node,
)
from app.services.verification.evidence import CombinedAdapter
from app.services.ingredient_normalizer import (
    NORMALIZER_METHOD,
    NORMALIZER_VERSION,
    normalize_label_text,
)
from app.services.ingredient_parser import parse_label_ingredients
from app.repositories.serialize import (
    candidate_rows,
    match_row,
    normalization_row,
    observation_row,
)
from app.services.storage import store_verification_decision
from app.services.verification.orchestrator import verify_candidate

__all__ = ["ObservationService"]


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _normalization_id(
    observation_id: str, normalized_text: str, status: str
) -> str:
    """Stable normalization id for one observation's text.

    Deterministic (uuid5 over the observation id plus the normalized
    content, method, and version) so re-running the same input
    reuses the row instead of duplicating it. A corrected text
    normalizes differently, so it naturally yields a different id
    and the pre-correction row stays intact as history.
    """
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "|".join([
            "normalization", observation_id, normalized_text,
            NORMALIZER_METHOD, NORMALIZER_VERSION, status,
        ]),
    ))


class ObservationService:
    """Pipeline orchestration over injected registry/adapters/repos."""

    def __init__(
        self,
        repos,
        registry: Optional[EntityRegistry] = None,
        adapters: Optional[list] = None,
        review_service=None,
    ) -> None:
        self._repos = repos
        self._registry = registry or InMemoryRegistry(
            [], registry_id="empty_production_registry", version="0"
        )
        self._adapters = list(adapters or [])
        self._review_service = review_service

    # -- create ----------------------------------------------------------

    async def create(
        self,
        raw_text: str,
        *,
        scan_id: Optional[str] = None,
        observation_id: Optional[str] = None,
        observation_ids: Optional[list] = None,
        source_type: str = "ocr",
        ocr_run_id: Optional[str] = None,
        ocr_confidence: Optional[float] = None,
        owner: Optional[str] = None,
        role: str = "service",
    ) -> dict:
        """Parse raw text and persist one observation per top-level node.

        Raw text is stored verbatim; nothing is normalized, corrected,
        or enriched at this step. Nested children stay in the returned
        tree (re-derivable deterministically); per-node persistence
        below the top level is a documented later extension.

        `observation_ids` optionally assigns stable ids to each node
        in order (used by deterministic re-runs); `observation_id`
        keeps its single-node meaning. Normalization ids derive from
        the observation id plus normalized content, so repeating the
        same input reuses rows instead of duplicating them.
        """
        parsed = parse_label_ingredients(raw_text)
        if not parsed.nodes:
            raise _errors.ServiceError("no ingredients extracted")
        if observation_ids is not None and len(observation_ids) != len(
            parsed.nodes
        ):
            raise _errors.ServiceError(
                "observation id count does not match node count")
        scan = scan_id or _new_uuid()
        items = []
        for position, node in enumerate(parsed.nodes):
            node_id = node.id
            if (
                observation_id is not None
                and len(parsed.nodes) == 1
            ):
                node_id = observation_id
            if observation_ids is not None:
                node_id = observation_ids[position]
            await self._repos.matches.save_observation(
                observation_row(
                    observation_id=node_id,
                    scan_id=scan,
                    sequence_number=position,
                    raw_text=node.raw_text,
                    source_type=source_type,
                    ocr_run_id=ocr_run_id,
                    ocr_confidence=ocr_confidence,
                    owner_subject=owner,
                ),
                role=role,
            )
            normalized = normalize_label_text(node.raw_text)
            top = normalized.nodes[0] if normalized.nodes else None
            normalized_text = (
                top.normalized_text if top else node.raw_text
            )
            await self._repos.matches.save_normalization(
                normalization_row(
                    normalization_id=_normalization_id(
                        node_id, normalized_text, normalized.status),
                    observation_id=node_id,
                    normalized_text=normalized_text,
                    method=NORMALIZER_METHOD,
                    version=NORMALIZER_VERSION,
                    status=normalized.status,
                    owner_subject=owner,
                ),
                role=role,
            )
            items.append({
                "observation_id": node_id,
                "scan_id": scan,
                "raw_text": node.raw_text,
                "normalized_text": (
                    top.normalized_text if top else node.raw_text
                ),
                "status": normalized.status,
                "tree": [n.to_dict() for n in parsed.nodes],
            })
        # Tree attached once (identical for every item of the request).
        tree = [n.to_dict() for n in parsed.nodes]
        for item in items:
            item["tree"] = tree
        return {"items": items, "scan_id": scan}

    # -- correct ---------------------------------------------------------

    async def correct(
        self,
        observation_id: str,
        *,
        corrected_text: str,
        reason: str,
        owner: Optional[str] = None,
        role: str = "service",
    ) -> dict:
        """Record a human correction without rewriting history.

        The original `raw_text` stays immutable: the first correction
        moves it to `original_text` and stores the corrected reading
        in `display_text`. A fresh normalization row is persisted for
        the corrected text, so the pre-correction normalization
        remains as history and later reads/analyses use the latest
        one. Correcting an already-corrected observation is refused:
        there is no correction chain, only one documented revision.
        A correction never establishes identity, chemistry, role, or
        verification -- it only repairs text.
        """
        if not (corrected_text or "").strip():
            raise _errors.ServiceError("corrected text is empty")
        if not (reason or "").strip():
            raise _errors.ServiceError("correction reason is required")
        try:
            stored = await self._repos.matches.get_observation(
                observation_id, role=role)
        except KeyError:
            raise _errors.NotFoundError("observation not found")
        _errors.require_owner_match(
            stored.get("owner_subject"), owner,
            resource="observation")
        if stored.get("user_corrected"):
            raise _errors.ServiceError("observation already corrected")
        updated = await self._repos.matches.record_correction(
            observation_id,
            display_text=corrected_text.strip(),
            original_text=stored.get("raw_text") or "",
            reason=reason.strip(),
            role=role,
        )
        normalized = normalize_label_text(corrected_text.strip())
        top = normalized.nodes[0] if normalized.nodes else None
        normalized_text = (
            top.normalized_text if top else corrected_text.strip()
        )
        normalization_id = await self._repos.matches.save_normalization(
            normalization_row(
                normalization_id=_normalization_id(
                    observation_id, normalized_text,
                    "corrected:%s" % normalized.status),
                observation_id=observation_id,
                normalized_text=normalized_text,
                method=NORMALIZER_METHOD,
                version=NORMALIZER_VERSION,
                status=normalized.status,
                owner_subject=stored.get("owner_subject"),
            ),
            role=role,
        )
        return {
            "observation": updated,
            "normalization_id": normalization_id,
            "normalized_text": normalized_text,
        }

    # -- analyze -----------------------------------------------------------

    async def analyze(
        self, observation_id: str, *, owner: Optional[str] = None,
        role: str = "service",
    ) -> dict:
        """Resolve + verify one observation; persist everything.

        Analysis runs on the corrected display text when a human
        correction exists, otherwise on the raw text. The raw text
        itself is never altered by this step.
        """
        chain = await self._chain(
            observation_id, owner=owner, role=role)
        effective = (
            chain["observation"].get("display_text")
            or chain["observation"]["raw_text"]
        )
        reparsed = parse_label_ingredients(effective)
        if len(reparsed.nodes) != 1:
            raise _errors.ServiceError("segment reparse mismatch")
        normalized = normalize_label_text(
            reparsed.nodes[0].raw_text)
        if not normalized.nodes:
            raise _errors.ServiceError("normalization produced nothing")
        node = normalized.nodes[0]
        resolution = resolve_node(node, self._registry)
        data_owner = chain["observation"].get("owner_subject")
        match_id = await self._repos.matches.save_match(
            match_row(resolution, normalization_id=chain[
                "normalization"]["id"], owner_subject=data_owner),
            role=role,
        )
        await self._repos.matches.save_candidates(
            candidate_rows(resolution, normalization_id=chain[
                "normalization"]["id"], owner_subject=data_owner),
            role=role,
        )
        combined = CombinedAdapter(list(self._adapters))
        decision = verify_candidate(resolution, combined)
        stored = await store_verification_decision(
            self._repos, decision, match_id,
            self._candidate_key(resolution),
            owner_subject=data_owner,
        )
        review_id = None
        if self._review_service is not None:
            records = combined.lookup_identity(resolution) or []
            review_id = await self._review_service.submit(
                decision, resolution, records, owner=data_owner)
        return {
            "observation_id": observation_id,
            "match_id": match_id,
            "resolution": resolution.to_dict(),
            "decision": decision.to_dict(),
            "stored": stored,
            "review_id": review_id,
        }

    # -- reads ---------------------------------------------------------------

    async def get(
        self, observation_id: str, *, owner: Optional[str] = None,
        role: str = "authenticated",
    ) -> dict:
        """Observation + normalization + live re-derived tree."""
        chain = await self._chain(
            observation_id, owner=owner, role=role)
        observation = chain["observation"]
        effective = (
            observation.get("display_text") or observation["raw_text"]
        )
        reparsed = parse_label_ingredients(effective)
        return {
            "observation_id": observation["id"],
            "scan_id": observation["scan_id"],
            "raw_text": observation["raw_text"],
            "display_text": observation.get("display_text"),
            "user_corrected": bool(observation.get("user_corrected")),
            "normalized_text": chain["normalization"]["normalized_text"],
            "status": chain["normalization"]["status"],
            "tree": [n.to_dict() for n in reparsed.nodes],
        }

    async def get_candidates(
        self, observation_id: str, *, owner: Optional[str] = None,
        role: str = "authenticated",
    ) -> dict:
        """Resolution view: raw, normalized, method, status, alternatives."""
        chain = await self._chain(
            observation_id, owner=owner, role=role)
        match = chain["match"]
        if match is None:
            raise _errors.NotFoundError("not yet analyzed")
        resolution = {
            "raw_text": chain["observation"]["raw_text"],
            "normalized_text": chain["normalization"]["normalized_text"],
            "match_status": match["match_status"],
            "identity_confidence": match["identity_confidence"],
            "entity": None,
            "alternatives": [],
        }
        selected = next(
            (c for c in chain["candidates"]
             if (c.get("match_reasons") or {}).get("selected")),
            None,
        )
        if selected is not None:
            reasons = selected.get("match_reasons") or {}
            resolution["entity"] = {
                "candidate_ref": reasons.get("candidate_ref"),
                "display_name": selected.get("candidate_name"),
                "match_method": selected.get("match_status"),
            }
        for candidate in chain["candidates"]:
            reasons = candidate.get("match_reasons") or {}
            if selected is not None and candidate["id"] == selected["id"]:
                continue
            resolution["alternatives"].append({
                "candidate_ref": reasons.get("candidate_ref"),
                "display_name": candidate.get("candidate_name"),
                "match_method": candidate.get("match_status"),
                "reason": reasons.get("reason"),
            })
        resolution["normalization_id"] = chain["normalization"]["id"]
        return resolution

    async def get_verification(
        self, observation_id: str, *, owner: Optional[str] = None,
        role: str = "authenticated",
    ) -> dict:
        """Current decision + claims + evidence + history."""
        chain = await self._chain(
            observation_id, owner=owner, role=role)
        match = chain["match"]
        if match is None:
            raise _errors.NotFoundError("not yet analyzed")
        decisions = await self._repos.verification.list_decisions(role=role)
        mine = [
            d for d in decisions
            if d.get("entity_match_id") == match["id"]
        ]
        mine.sort(key=lambda d: str(d.get("id")))
        if not mine:
            raise _errors.NotFoundError("no verification stored")
        current = mine[-1]
        claims = []
        for claim_id in current.get("claim_ids") or []:
            try:
                claim = await self._repos.claims.get_claim(
                    claim_id, role=role)
            except KeyError:
                continue
            evidence = await self._evidence_with_names(
                claim["id"], role=role)
            claims.append({"claim": claim, "evidence": evidence})
        return {
            "decision": current,
            "claims": claims,
            "history": [
                {"id": d["id"], "status": d["status"],
                 "identity_confidence": d["identity_confidence"]}
                for d in mine
            ],
        }

    async def _evidence_with_names(
        self, claim_id: str, *, role: str
    ) -> list:
        rows = await self._repos.evidence.list_for_claim(
            claim_id, role=role)
        enriched = []
        for row in rows:
            item = dict(row)
            try:
                source = await self._repos.evidence.get_source(
                    str(row["source_id"]), role=role)
                item["source_name"] = source.get("name")
            except KeyError:
                item["source_name"] = None
            enriched.append(item)
        return enriched

    async def get_claim(
        self, claim_id: str, *, role: str = "authenticated"
    ) -> dict:
        """One claim with its evidence links."""
        try:
            claim = await self._repos.claims.get_claim(claim_id, role=role)
        except KeyError:
            raise _errors.NotFoundError("claim not found")
        evidence = await self._evidence_with_names(claim_id, role=role)
        return {"claim": claim, "evidence": evidence}

    # -- internals ---------------------------------------------------------------

    async def _chain(
        self, observation_id: str, *, owner: Optional[str] = None,
        role: str,
    ) -> dict:
        try:
            norm = await self._repos.matches.get_normalization_for_observation(
                observation_id, role=role
            )
            chain = await self._repos.matches.get_chain(
                norm["id"], role=role)
        except KeyError:
            raise _errors.NotFoundError("observation not found")
        _errors.require_owner_match(
            chain["observation"].get("owner_subject"), owner,
            resource="observation")
        return chain

    @staticmethod
    def _candidate_key(resolution) -> str:
        from app.services.verification.review import candidate_key_for

        return candidate_key_for(
            resolution.normalized_text or "", resolution.identifier)
