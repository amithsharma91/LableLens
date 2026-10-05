"""OCR-to-pipeline orchestration (Stage 16).

Flow per OCR run:

    provider extraction (or client-supplied text)
      -> immutable ocr_runs row
      -> optional single human correction (ocr_corrections row)
      -> observations from corrected-or-raw text (Stage 2/4 inside
         ObservationService.create)
      -> per-observation analyze (Stage 5 + frozen V1-V7)

The service holds no business rules beyond orchestration. OCR text
is never repaired here: corrupted names/codes flow downstream
verbatim and resolve to nothing, and a human correction is the
only repair path. OCR confidence is stored and reported; it is
never mapped to identity confidence.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from app.repositories.serialize import (
    ocr_correction_row,
    ocr_run_row,
)
from app.services import errors as _errors
from app.services.entity_resolver import (
    EntityRegistry,
    InMemoryRegistry,
)
from app.services.ingredient_parser import parse_label_ingredients
from app.services.observation_service import ObservationService
from app.services.ocr_provider import (
    OCRDocument,
    OCRProvider,
    OCRResult,
    ProviderFailure,
)

__all__ = ["OCRService", "observation_id_for_run"]


def observation_id_for_run(
    run_id: str, kind: str, sequence_number: int
) -> str:
    """Stable observation id for one OCR-run ingredient position.

    `kind` is "raw" or "corrected": corrected text yields different
    ids, so the raw-derived observations stay intact as history and
    a rerun reuses rows instead of duplicating them.
    """
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        "|".join([
            "ocr-observation", str(run_id), kind,
            str(sequence_number),
        ]),
    ))


def scan_id_for_run(run_id: str) -> str:
    """Stable scan id grouping one OCR run's observations."""
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL, "|".join(["ocr-scan", str(run_id)])))


class OCRService:
    """OCR runs, corrections, and observation derivation."""

    def __init__(
        self,
        repos,
        registry: Optional[EntityRegistry] = None,
        adapters: Optional[list] = None,
        providers: Optional[Dict[str, OCRProvider]] = None,
        review_service=None,
    ) -> None:
        self._repos = repos
        self._observations = ObservationService(
            repos,
            registry=registry or InMemoryRegistry(
                [], registry_id="empty_production_registry",
                version="0",
            ),
            adapters=list(adapters or []),
            review_service=review_service,
        )
        self._providers = dict(providers or {})

    # -- ingest ----------------------------------------------------------

    async def register_result(
        self,
        result: OCRResult,
        *,
        run_id: Optional[str] = None,
        role: str = "service",
    ) -> dict:
        """Persist one immutable OCR run. No parsing happens here."""
        if not isinstance(result, OCRResult):
            raise _errors.ServiceError(
                "ocr result must be an OCRResult")
        resolved = run_id or str(uuid.uuid4())
        await self._repos.ocr.save_run(
            ocr_run_row(
                run_id=resolved,
                document_id=result.document_id,
                provider=result.provider,
                raw_text=result.raw_text,
                provider_version=result.provider_version,
                ocr_confidence=result.ocr_confidence,
                page_metadata=dict(result.page_metadata or {}),
                source_reference=dict(result.source_reference or {}),
            ),
            role=role,
        )
        return await self._repos.ocr.get_run(
            resolved, role="service")

    async def extract_with(
        self,
        provider_name: str,
        document_id: str,
        *,
        document_locator: Optional[str] = None,
        run_id: Optional[str] = None,
        role: str = "service",
    ) -> dict:
        """Extract via a named provider, then persist the run.

        The provider runs before any write, so a provider failure
        leaves no partial rows behind.
        """
        try:
            provider = self._providers[provider_name]
        except KeyError:
            raise _errors.ServiceError(
                "unknown ocr provider %r" % provider_name)
        try:
            result = await provider.extract(OCRDocument(
                document_id=document_id,
                locator=document_locator,
            ))
        except ProviderFailure:
            raise
        except Exception as exc:
            raise ProviderFailure(
                "provider %r failed: %s" % (
                    provider_name, type(exc).__name__))
        return await self.register_result(
            result, run_id=run_id, role=role)

    # -- correct ---------------------------------------------------------

    async def correct_run(
        self,
        run_id: str,
        *,
        corrected_text: str,
        reason: str,
        actor: str,
        role: str = "service",
    ) -> dict:
        """Record the run's single human revision without touching raw.

        The raw OCR text stays immutable; the corrected full text is
        stored as a separate row with reason and actor. A second
        correction is refused, mirroring the observation-level rule:
        there is no silent correction chain, only one documented
        revision.
        """
        if not (corrected_text or "").strip():
            raise _errors.ServiceError("corrected text is empty")
        if not (reason or "").strip():
            raise _errors.ServiceError("correction reason is required")
        if not (actor or "").strip():
            raise _errors.ServiceError("correction actor is required")
        try:
            await self._repos.ocr.get_run(run_id, role=role)
        except KeyError:
            raise _errors.NotFoundError("ocr run not found")
        try:
            await self._repos.ocr.get_correction(run_id, role=role)
        except KeyError:
            pass
        else:
            raise _errors.ServiceError("ocr run already corrected")
        await self._repos.ocr.save_correction(
            ocr_correction_row(
                ocr_run_id=str(run_id),
                corrected_text=corrected_text.strip(),
                reason=reason.strip(),
                actor=actor.strip(),
            ),
            role=role,
        )
        return await self._repos.ocr.get_correction(
            str(run_id), role="service")

    async def _effective_text(
        self, run_id: str, *, role: str
    ) -> tuple:
        try:
            run = await self._repos.ocr.get_run(run_id, role=role)
        except KeyError:
            raise _errors.NotFoundError("ocr run not found")
        try:
            correction = await self._repos.ocr.get_correction(
                str(run_id), role=role)
        except KeyError:
            correction = None
        if correction is not None:
            return run, correction["corrected_text"], "corrected"
        return run, run["raw_text"], "raw"

    # -- observe + analyze -----------------------------------------------

    async def observe(
        self, run_id: str, *, role: str = "service"
    ) -> dict:
        """Derive observations from corrected-or-raw run text.

        Parsing and normalization run inside
        :meth:`ObservationService.create`; this layer only selects
        the text and carries the run linkage (ocr_run_id, confidence,
        deterministic ids). Empty or ingredient-free text returns a
        warning outcome -- never a crash, never an invented entity.
        """
        run, text, kind = await self._effective_text(
            run_id, role=role)
        parsed = parse_label_ingredients(text or "")
        warnings: List[str] = list(parsed.limitations)
        if not text or not text.strip():
            warnings.append("empty_ocr_text")
        if not parsed.nodes:
            warnings.append("no_ingredients_extracted")
            return {
                "run_id": str(run["id"]),
                "scan_id": None,
                "corrected": kind == "corrected",
                "items": [],
                "warnings": warnings,
            }
        created = await self._observations.create(
            text,
            scan_id=scan_id_for_run(str(run["id"])),
            observation_ids=[
                observation_id_for_run(
                    str(run["id"]), kind, position)
                for position in range(len(parsed.nodes))
            ],
            source_type="ocr",
            ocr_run_id=str(run["id"]),
            ocr_confidence=run.get("ocr_confidence"),
            role=role,
        )
        return {
            "run_id": str(run["id"]),
            "scan_id": created["scan_id"],
            "corrected": kind == "corrected",
            "items": created["items"],
            "warnings": warnings,
        }

    async def analyze_run(
        self, run_id: str, *, role: str = "service"
    ) -> dict:
        """Observe, then analyze every derived observation."""
        observed = await self.observe(run_id, role=role)
        items = []
        for item in observed["items"]:
            analyzed = await self._observations.analyze(
                item["observation_id"], role=role)
            items.append({
                "observation_id": item["observation_id"],
                "raw_text": item["raw_text"],
                "resolution": analyzed["resolution"],
                "decision": analyzed["decision"],
                "decision_id": (
                    analyzed.get("decision_id")
                    or (analyzed.get("stored") or {}).get("id")),
                "review_id": analyzed.get("review_id"),
            })
        observed["items"] = items
        return observed

    async def describe(
        self, run_id: str, *, role: str = "service"
    ) -> dict:
        """Run plus correction plus derived observations (OCR layer).

        Returns OCR-layer data only: no resolution, no verification,
        no chemistry. Consumers needing analysis call analyze_run.
        """
        try:
            run = await self._repos.ocr.get_run(run_id, role=role)
        except KeyError:
            raise _errors.NotFoundError("ocr run not found")
        try:
            correction = await self._repos.ocr.get_correction(
                str(run_id), role=role)
        except KeyError:
            correction = None
        observations = await self._repos.matches.list_run_observations(
            str(run["id"]), role=role)
        return {
            "run": run,
            "correction": correction,
            "observations": [
                {
                    "observation_id": row["id"],
                    "sequence_number": row.get("sequence_number"),
                    "raw_text": row.get("raw_text"),
                    "display_text": row.get("display_text"),
                    "user_corrected": bool(
                        row.get("user_corrected")),
                }
                for row in observations
            ],
        }
