"""Read-only PubChem evidence adapter (PUG-REST).

Official documentation:
https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
(verified 2026-10-05; endpoint shapes additionally confirmed live:
property/synonym lookups, ``PUGREST.NotFound`` 404 body.)

Strategy (conservative, no fuzzy search):

1. numeric CID identifier  -> ``/compound/cid/{n}/...``
2. CAS-shaped identifier   -> ``/compound/name/{cas}/...``
3. exact name              -> ``/compound/name/{name}/...`` accepted
   only when the returned ``Title`` equals the candidate name
   (normalized); anything else is discarded, never assumed.
4. additive code (E/INS)   -> name-endpoint lookup of the code string,
   accepted only when the record's synonym list contains the code.
   This uses the provider's own synonym index, verified client-side.

Every accepted record becomes field-level ``EvidenceItem`` rows
(title, formula, weight, SMILES, InChI, InChIKey, IUPAC name, CID,
synonym-evidenced codes). The adapter asserts nothing: records flow
into the frozen V1-V7 gate via ``SourceRecord`` conversion.

Rate behavior: conservative client-side spacing (default 1.0 s). The
official per-client quota is NOT asserted here (unknown); spacing only
avoids hammering. No API key is used or needed.
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
from app.services.verification.gate import derive_name_key, validate_cas_format
from app.services.verification.models import SourceRecord

__all__ = ["PubChemAdapter", "PUBCHEM_DOCS_URL", "PUBCHEM_PROPERTIES"]

PUBCHEM_DOCS_URL = "https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest"
PUBCHEM_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# Property list for identity/chemistry evidence. ``SMILES`` is the
# isomeric SMILES as documented by PUG-REST; stored verbatim, never
# transformed or canonicalized here.
PUBCHEM_PROPERTIES = (
    "Title,MolecularFormula,MolecularWeight,SMILES,InChI,InChIKey,"
    "IUPACName"
)


def _canon(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text or "").strip().lower()


def _canon_code(code: str) -> str:
    import re

    return re.sub(r"[\s\-.]+", "", (code or "").strip().upper())


def _code_field(identifier: str) -> str:
    """Evidence field label for an additive code (INS vs E)."""
    if (identifier or "").strip().upper().startswith("INS"):
        return "identifier:ins_number"
    return "identifier:e_number"


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


class PubChemAdapter(VerificationSource):
    """PUG-REST evidence source (Class A per source registry)."""

    adapter_id = "pubchem"
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
            PUBCHEM_BASE_URL, limiter=RateLimiter()
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
        if identifier and identifier.replace(" ", "").isdigit():
            hit = self._fetch_cid(identifier.replace(" ", ""))
            return [hit] if hit is not None else []
        if identifier and validate_cas_format(identifier):
            hit = self._fetch_name(identifier, expect_title=None)
            return [hit] if hit is not None else []
        if key:
            hit = self._fetch_name(key, expect_title=key)
            if hit is not None:
                return self._with_code_evidence(hit, identifier)
            if identifier:
                return self._lookup_code(identifier)
            return []
        if identifier:
            return self._lookup_code(identifier)
        return []

    def _lookup_code(self, identifier: str) -> List[EvidenceSet]:
        """Resolve an additive code via the provider synonym index."""
        kind, key = "pubchem:code", identifier
        path = (
            "/compound/name/%s/property/%s/JSON"
            % (
                urllib.parse.quote(identifier, safe=""),
                PUBCHEM_PROPERTIES,
            )
        )
        hit = self._cached_lookup(kind, key)
        if hit is not None:
            return [hit]
        if self._offline:
            self._note("pubchem unavailable offline (no cached evidence)")
            return []
        try:
            payload, body = self._client.get_json(path)
        except (ProviderNotFound, ProviderBadRequest):
            return []
        except ProviderError as exc:
            self._note("pubchem code lookup failed: %s" % exc)
            return []
        props = self._first_properties(payload)
        if props is None:
            return []
        cid = str(props.get("CID", ""))
        synonyms = self._fetch_synonyms(cid) if cid else []
        if _canon_code(identifier) not in {
            _canon_code(s) for s in synonyms
        }:
            self._note(
                "pubchem code %s not in record synonyms; discarded"
                % identifier
            )
            return []
        eset = self._evidence_set(
            "pubchem:code:%s" % identifier,
            props,
            synonyms,
            body,
            code_match=identifier,
        )
        self._cached_store(kind, key, path, body, eset)
        return [eset]

    def _fetch_cid(self, cid: str) -> Optional[EvidenceSet]:
        kind, key = "pubchem:cid", cid
        path = (
            "/compound/cid/%s/property/%s/JSON"
            % (urllib.parse.quote(cid, safe=""), PUBCHEM_PROPERTIES)
        )
        hit = self._cached_lookup(kind, key)
        if hit is not None:
            return hit
        if self._offline:
            self._note("pubchem unavailable offline (no cached evidence)")
            return None
        try:
            payload, body = self._client.get_json(path)
        except (ProviderNotFound, ProviderBadRequest):
            return None
        except ProviderError as exc:
            self._note("pubchem cid lookup failed: %s" % exc)
            return None
        props = self._first_properties(payload)
        if props is None:
            return None
        eset = self._evidence_set(
            "pubchem:cid:%s" % cid, props, [], body, code_match=None
        )
        self._cached_store(kind, key, path, body, eset)
        return eset

    def _fetch_name(
        self, name: str, *, expect_title: Optional[str]
    ) -> Optional[EvidenceSet]:
        """Name lookup; accepted only on exact Title agreement."""
        kind, key = "pubchem:name", name
        path = (
            "/compound/name/%s/property/%s/JSON"
            % (
                urllib.parse.quote(name, safe=""),
                PUBCHEM_PROPERTIES,
            )
        )
        hit = self._cached_lookup(kind, key)
        if hit is not None:
            if expect_title is not None and not self._title_matches(
                hit, expect_title
            ):
                return None
            return hit
        if self._offline:
            self._note("pubchem unavailable offline (no cached evidence)")
            return None
        try:
            payload, body = self._client.get_json(path)
        except (ProviderNotFound, ProviderBadRequest):
            return None
        except ProviderError as exc:
            self._note("pubchem name lookup failed: %s" % exc)
            return None
        props = self._first_properties(payload)
        if props is None:
            return None
        if expect_title is not None and _canon(
            str(props.get("Title", ""))
        ) != _canon(expect_title):
            self._note(
                "pubchem title mismatch for %s; discarded" % name
            )
            return None
        eset = self._evidence_set(
            "pubchem:name:%s" % name, props, [], body, code_match=None
        )
        self._cached_store(kind, key, path, body, eset)
        return eset

    @staticmethod
    def _title_matches(eset: EvidenceSet, expect_title: str) -> bool:
        titles = [
            str(i.source_value)
            for i in eset.items
            if i.field == "preferred_name"
        ]
        return any(_canon(t) == _canon(expect_title) for t in titles)

    def _with_code_evidence(
        self, eset: EvidenceSet, identifier: str
    ) -> List[EvidenceSet]:
        """Attach synonym-evidenced code mapping to a name hit."""
        if not identifier:
            return [eset]
        cid_items = eset.fields("identifier:pubchem_cid")
        if not cid_items:
            return [eset]
        synonyms = self._fetch_synonyms(str(cid_items[0].source_value))
        supported = [
            s for s in synonyms if _canon_code(s) == _canon_code(identifier)
        ]
        if not supported:
            self._note(
                "pubchem code %s not evidenced; name evidence kept"
                % identifier
            )
            return [eset]
        items = list(eset.items) + [
            self._item(eset, _code_field(identifier), supported[0])
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

    def _fetch_synonyms(self, cid: str) -> List[str]:
        kind, key = "pubchem:synonyms", cid
        path = "/compound/cid/%s/synonyms/JSON" % urllib.parse.quote(
            cid, safe=""
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
            self._note("pubchem synonyms failed: %s" % exc)
            return []
        try:
            info = payload["InformationList"]["Information"][0]
            synonyms = info.get("Synonym", [])
        except (KeyError, IndexError, TypeError, AttributeError):
            return []
        names = [s for s in synonyms if isinstance(s, str)][:500]
        self._cached_store(
            kind,
            key,
            path,
            body,
            EvidenceSet(
                provider=self.adapter_id,
                lookup_key="pubchem:synonyms:%s" % cid,
                retrieved_at=self._today(),
                response_hash="",
                locator="CID:%s" % cid,
                items=tuple(
                    self._synonym_item(cid, s) for s in names[:20]
                ),
                notices=(),
            ),
        )
        return names

    def _synonym_item(self, cid: str, value: str) -> EvidenceItem:
        return EvidenceItem(
            source="PubChem",
            source_id="PUBCHEM",
            provider=self.adapter_id,
            retrieved_at=self._today(),
            publication_date=None,
            source_version="live PUG-REST, unversioned",
            field="synonym",
            source_value=value,
            unit=None,
            support_type="secondary",
            support_strength="weak",
            review_status=REVIEW_UNREVIEWED,
            locator="CID:%s" % cid,
        )

    # -- parsing --------------------------------------------------------

    @staticmethod
    def _first_properties(payload: dict) -> Optional[dict]:
        try:
            table = payload["PropertyTable"]
            props = table["Properties"]
            first = props[0]
        except (KeyError, IndexError, TypeError):
            return None
        return first if isinstance(first, dict) else None

    def _evidence_set(
        self,
        lookup_key: str,
        props: dict,
        synonyms: List[str],
        body: bytes,
        *,
        code_match: Optional[str],
    ) -> EvidenceSet:
        import hashlib

        locator = "CID:%s" % props.get("CID", "?")
        today = self._today()
        base = dict(
            source="PubChem",
            source_id="PUBCHEM",
            provider=self.adapter_id,
            retrieved_at=today,
            publication_date=None,
            source_version="live PUG-REST, unversioned per record",
            support_type=SUPPORT_DIRECT,
            support_strength="strong",
            review_status=REVIEW_UNREVIEWED,
            locator=locator,
        )
        items = [
            EvidenceItem(
                field="preferred_name",
                source_value=str(props.get("Title", "")),
                **{k: v for k, v in base.items()},
            )
        ]
        field_map = (
            ("formula", "MolecularFormula"),
            ("molecular_weight", "MolecularWeight"),
            ("smiles", "SMILES"),
            ("inchi", "InChI"),
            ("inchikey", "InChIKey"),
            ("iupac_name", "IUPACName"),
        )
        for field_name, prop in field_map:
            value = props.get(prop)
            if isinstance(value, (str, int, float)) and str(value):
                if field_name == "molecular_weight":
                    value = self._format_mass(value) or value
                items.append(
                    EvidenceItem(field=field_name, source_value=value, **base)
                )
        if "CID" in props:
            items.append(
                EvidenceItem(
                    field="identifier:pubchem_cid",
                    source_value=str(props["CID"]),
                    **{k: v for k, v in base.items()},
                )
            )
        for syn in synonyms:
            if _canon_code(syn) == _canon_code(code_match or "\0"):
                items.append(
                    EvidenceItem(
                        field=_code_field(code_match or ""),
                        source_value=syn,
                        **{k: v for k, v in base.items()},
                    )
                )
        for syn in synonyms[:20]:
            if isinstance(syn, str) and syn:
                items.append(
                    EvidenceItem(
                        field="synonym",
                        source_value=syn,
                        support_type="secondary",
                        source="PubChem",
                        source_id="PUBCHEM",
                        provider=self.adapter_id,
                        retrieved_at=today,
                        publication_date=None,
                        source_version="live PUG-REST, unversioned",
                        support_strength="weak",
                        review_status=REVIEW_UNREVIEWED,
                        locator=locator,
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

    def _item(
        self, eset: EvidenceSet, field_name: str, value: object
    ) -> EvidenceItem:
        return EvidenceItem(
            source="PubChem",
            source_id="PUBCHEM",
            provider=self.adapter_id,
            retrieved_at=eset.retrieved_at,
            publication_date=None,
            source_version="live PUG-REST, unversioned per record",
            field=field_name,
            source_value=str(value),
            unit=None,
            support_type=SUPPORT_DIRECT,
            support_strength="strong",
            review_status=REVIEW_UNREVIEWED,
            locator=eset.locator,
        )

    @staticmethod
    def _format_mass(value: object) -> Optional[str]:
        """Two-decimal presentation (never a computed fact)."""
        try:
            return "%.2f" % float(str(value))
        except (TypeError, ValueError):
            return None

    # -- cached transport -------------------------------------------------

    def _cached_lookup(self, kind: str, key: str) -> Optional[EvidenceSet]:
        """Replay stored evidence identically, or None on miss/expiry."""
        if self._cache is None:
            return None
        entry = self._cache.get(self.adapter_id, kind, key)
        if entry is None:
            return None
        return self._cache.to_evidence_set(entry)

    def _cached_store(
        self, kind: str, key: str, path: str, body: bytes, eset: EvidenceSet
    ) -> None:
        # Retrieval symmetry first: the stored lookup_key MUST equal
        # the key _cached_lookup will query, or hits never happen.
        # (EvidenceSet.lookup_key remains diagnostic-only metadata;
        # it never enters records or decisions.)
        if self._cache is None:
            return
        self._cache.put(
            provider=self.adapter_id,
            lookup_kind=kind,
            lookup_key=key,
            request_identity=path,
            response_body=body,
            source_version="live PUG-REST",
            freshness_class="stable",
            evidence=eset.items,
            locator=eset.locator,
        )
