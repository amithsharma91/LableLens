"""Read-only ChEBI evidence adapter (ChEBI 2.0 REST).

Official documentation:
https://www.ebi.ac.uk/chebi/backend/api/docs/
(OpenAPI schema at /chebi/backend/api/schema/, verified 2026-10-05;
endpoint shapes additionally confirmed live.)

Strategy (conservative, no fuzzy search):

1. exact name -> ``es_search/?term={name}`` accepted only when a hit's
   ``name``/``ascii_name`` equals the candidate name (normalized).
   No wildcards are ever sent. First exact hit in provider order wins;
   anything else is discarded, never assumed.
2. additive code (E/INS) -> compound detail ``names`` synonym list of
   the accepted hit, checked client-side for the code. No separate
   code-search endpoint is assumed.

Accepted hits become field-level ``EvidenceItem`` rows (name, formula,
average mass as molecular weight, SMILES, InChI, InChIKey, ChEBI
accession, evidenced synonyms). Records flow into the frozen V1-V7
gate; the adapter asserts nothing.

No authentication is required for these public endpoints. Molecular
weight is the provider's reported average mass formatted to two
decimals (presentation only, never a computed fact).
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Callable, List, Optional

from app.services.entity_resolver import Resolution
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.adapters.http import (
    HttpClient,
    ProviderBadRequest,
    ProviderError,
    ProviderNotFound,
    RateLimiter,
)
from app.services.verification.cache import EvidenceCache
from app.services.verification.evidence import (
    REVIEW_UNREVIEWED,
    SUPPORT_DIRECT,
    EvidenceItem,
    EvidenceSet,
    build_source_records,
)
from app.services.verification.gate import derive_name_key
from app.services.verification.models import SourceRecord

__all__ = ["ChebiAdapter", "CHEBI_DOCS_URL", "CHEBI_SCHEMA_URL"]

CHEBI_DOCS_URL = "https://www.ebi.ac.uk/chebi/backend/api/docs/"
CHEBI_SCHEMA_URL = "https://www.ebi.ac.uk/chebi/backend/api/schema/"
CHEBI_BASE_URL = "https://www.ebi.ac.uk"


def _canon(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text or "").strip().lower()


def _canon_code(code: str) -> str:
    import re

    return re.sub(r"[\s\-.]+", "", (code or "").strip().upper())


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


class ChebiAdapter(VerificationSource):
    """ChEBI 2.0 public REST evidence source (Class A per registry)."""

    adapter_id = "chebi"
    adapter_version = "1.0.0"

    def __init__(
        self,
        client: HttpClient | None = None,
        *,
        cache: EvidenceCache | None = None,
        offline: bool = False,
        date_provider: Callable[[], str] = _today,
    ) -> None:
        super().__init__()
        self._client = client or HttpClient(
            CHEBI_BASE_URL, limiter=RateLimiter()
        )
        self._cache = cache
        self._offline = offline
        self._today = date_provider
        self.snapshot_version = ""
        self.source_class = "A"

    # -- VerificationSource contract ---------------------------------

    def lookup_identity(
        self, resolution: Resolution
    ) -> List[SourceRecord]:
        """Evidence records for the candidate, or [] when absent."""
        if resolution is None:
            return []
        sets = self._lookup_sets(resolution)
        return build_source_records(sets)

    # -- lookup -------------------------------------------------------

    def _lookup_sets(
        self, resolution: Resolution
    ) -> List[EvidenceSet]:
        key = derive_name_key(
            resolution.normalized_text or "", resolution.identifier
        )
        identifier = (resolution.identifier or "").strip()
        if not key and not identifier:
            return []
        if key:
            hit = self._search_exact(key)
            if hit is not None:
                return self._with_code_evidence(hit, identifier)
        if identifier:
            self._note(
                "chebi code-only lookup unsupported; no evidence"
            )
        return []

    def _search_exact(self, term: str) -> Optional[EvidenceSet]:
        """Search; accept only an exact name/ascii_name hit."""
        kind, key = "chebi:search", term
        path = "/chebi/backend/api/public/es_search/?term=%s&size=5" % (
            urllib.parse.quote(term, safe="")
        )
        hit = self._cached_lookup(kind, key)
        if hit is not None:
            return hit
        if self._offline:
            self._note("chebi unavailable offline (no cached evidence)")
            return None
        try:
            payload, body = self._client.get_json(path)
        except (ProviderNotFound, ProviderBadRequest):
            return None
        except ProviderError as exc:
            self._note("chebi search failed: %s" % exc)
            return None
        if not isinstance(payload, list):
            self._note("chebi search shape unexpected; discarded")
            return None
        source = self._first_exact_hit(payload, term)
        if source is None:
            return None
        eset = self._evidence_set(
            "chebi:search:%s" % term, source, body
        )
        self._cached_store(kind, key, path, body, eset)
        return eset

    @staticmethod
    def _first_exact_hit(payload: list, term: str) -> Optional[dict]:
        want = _canon(term)
        for hit in payload:
            if not isinstance(hit, dict):
                continue
            source = hit.get("_source")
            if not isinstance(source, dict):
                continue
            names = {
                _canon(str(source.get("name", ""))),
                _canon(str(source.get("ascii_name", ""))),
            }
            if want in names and want:
                return source
        return None

    def _with_code_evidence(
        self, eset: EvidenceSet, identifier: str
    ) -> List[EvidenceSet]:
        """Attach code evidence from compound-detail synonyms."""
        if not identifier:
            return [eset]
        accession_items = [
            i for i in eset.items if i.field == "identifier:chebi_id"
        ]
        if not accession_items:
            return [eset]
        synonyms = self._detail_synonyms(
            str(accession_items[0].source_value)
        )
        if _canon_code(identifier) not in {_canon_code(s) for s in synonyms}:
            self._note(
                "chebi code %s not evidenced; name evidence kept"
                % identifier
            )
            return [eset]
        items = list(eset.items) + [
            EvidenceItem(
                source="ChEBI",
                source_id="CHEBI",
                provider=self.adapter_id,
                retrieved_at=eset.retrieved_at,
                publication_date=None,
                source_version="live ChEBI 2.0 REST, unversioned",
                field="identifier:e_number",
                source_value=identifier,
                unit=None,
                support_type=SUPPORT_DIRECT,
                support_strength="strong",
                review_status=REVIEW_UNREVIEWED,
                locator=eset.locator,
            )
        ]
        return [
            EvidenceSet(
                provider=eset.provider,
                lookup_key=eset.lookup_key,
                retrieved_at=eset.retrieved_at,
                response_hash=eset.response_hash,
                locator=eset.locator,
                items=tuple(items),
                notices=eset.notices,
            )
        ]

    def _detail_synonyms(self, accession: str) -> List[str]:
        numeric = accession.split(":")[-1]
        kind, key = "chebi:detail", numeric
        path = "/chebi/backend/api/public/compound/%s/" % (
            urllib.parse.quote(numeric, safe="")
        )
        hit = self._cached_lookup(kind, key)
        if hit is not None:
            return [
                str(i.source_value)
                for i in hit.items
                if i.field == "synonym"
            ]
        if self._offline:
            return []
        try:
            payload, body = self._client.get_json(path)
        except ProviderError as exc:
            self._note("chebi detail failed: %s" % exc)
            return []
        if not isinstance(payload, dict):
            return []
        names = self._synonym_names(payload)
        self._cached_store(
            kind,
            key,
            path,
            body,
            EvidenceSet(
                provider=self.adapter_id,
                lookup_key="chebi:detail:%s" % numeric,
                retrieved_at=self._today(),
                response_hash="",
                locator=accession,
                items=tuple(
                    EvidenceItem(
                        source="ChEBI",
                        source_id="CHEBI",
                        provider=self.adapter_id,
                        retrieved_at=self._today(),
                        publication_date=None,
                        source_version="live ChEBI 2.0 REST",
                        field="synonym",
                        source_value=name,
                        unit=None,
                        support_type="secondary",
                        support_strength="weak",
                        review_status=REVIEW_UNREVIEWED,
                        locator=accession,
                    )
                    for name in names[:20]
                ),
                notices=(),
            ),
        )
        return names

    @staticmethod
    def _synonym_names(detail: dict) -> List[str]:
        try:
            groups = detail.get("names", {})
            entries = groups.get("SYNONYM", [])
        except AttributeError:
            return []
        out = []
        for entry in entries:
            if isinstance(entry, dict):
                value = entry.get("ascii_name") or entry.get("name")
                if isinstance(value, str) and value:
                    out.append(value)
        return out[:500]

    # -- evidence building ----------------------------------------------

    def _evidence_set(
        self, lookup_key: str, source: dict, body: bytes
    ) -> EvidenceSet:
        import hashlib

        locator = str(source.get("chebi_accession", "?"))
        today = self._today()
        base = dict(
            source="ChEBI",
            source_id="CHEBI",
            provider=self.adapter_id,
            retrieved_at=today,
            publication_date=None,
            source_version="live ChEBI 2.0 REST, unversioned",
            support_type=SUPPORT_DIRECT,
            support_strength="strong",
            review_status=REVIEW_UNREVIEWED,
            locator=locator,
        )
        items = [
            EvidenceItem(
                field="preferred_name",
                source_value=str(source.get("name", "")),
                **base,
            ),
            EvidenceItem(
                field="identifier:chebi_id",
                source_value=locator,
                **base,
            ),
        ]
        if isinstance(source.get("formula"), str) and source["formula"]:
            items.append(
                EvidenceItem(
                    field="formula", source_value=source["formula"], **base
                )
            )
        mass = self._format_mass(source.get("mass"))
        if mass is not None:
            items.append(
                EvidenceItem(
                    field="molecular_weight",
                    source_value=mass,
                    unit="g/mol",
                    **base,
                )
            )
        for field_name, prop in (
            ("smiles", "smiles"),
            ("inchi", "inchi"),
            ("inchikey", "inchikey"),
        ):
            value = source.get(prop)
            if isinstance(value, str) and value:
                items.append(
                    EvidenceItem(
                        field=field_name, source_value=value, **base
                    )
                )
        return EvidenceSet(
            provider=self.adapter_id,
            lookup_key=lookup_key,
            retrieved_at=today,
            response_hash=hashlib.sha256(body).hexdigest(),
            locator=locator,
            items=tuple(items),
            notices=(),
        )

    @staticmethod
    def _format_mass(value: object) -> Optional[str]:
        """Average mass to two decimals (presentation only)."""
        try:
            return "%.2f" % float(str(value))
        except (TypeError, ValueError):
            return None

    # -- cached transport -------------------------------------------------

    def _cached_lookup(
        self, kind: str, key: str
    ) -> Optional[EvidenceSet]:
        """Replay stored evidence identically, or None on miss/expiry."""
        if self._cache is None:
            return None
        entry = self._cache.get(self.adapter_id, kind, key)
        if entry is None:
            return None
        return self._cache.to_evidence_set(entry)

    def _cached_store(
        self,
        kind: str,
        key: str,
        path: str,
        body: bytes,
        eset: EvidenceSet,
    ) -> None:
        # Retrieval symmetry first: stored lookup_key MUST equal the
        # key _cached_lookup queries (see PubChem adapter note).
        if self._cache is None:
            return
        self._cache.put(
            provider=self.adapter_id,
            lookup_kind=kind,
            lookup_key=key,
            request_identity=path,
            response_body=body,
            source_version="live ChEBI 2.0 REST",
            freshness_class="stable",
            evidence=eset.items,
            locator=eset.locator,
        )
