"""Candidate entity resolution (Stage 5).

Canonical entry point: :func:`resolve_entities` (Stage-4
``NormalizationResult`` in, resolution tree out). Single-ingredient
entry point: :func:`resolve_node`.

What this stage answers:
    "What entities are plausible interpretations of this label text?"
What this stage MUST NOT answer (later stages own these):
    chemical identity verification, formulas, CAS, SMILES/InChI,
    molecular weights, descriptors, roles, regulatory status, or any
    verified claim. No ``verified`` status exists in this module.

Priority order (deterministic, provider-independent, no network):
    1. exact_identifier      (e.g. ``INS 471``, ``E 330``)
    2. exact_normalized_name  (e.g. ``citric acid``)
    3. exact_alias            (explicit registry aliases only)
    4. controlled_ocr_similarity (bounded Levenshtein, flagged)
    5. contextual_candidate   (supporting signal only, never alone)
    6. unresolved

Statuses: ``exact_match | candidate | ambiguous | unresolved``.
``selected_candidate`` is set ONLY for ``exact_match`` -- never the
first of several, never an OCR-near guess. Identity confidence uses
qualitative states (HIGH/MEDIUM/LOW/UNKNOWN); internal ``match_score``
values are ranking aids only, never calibrated probabilities, and
never imply scientific certainty.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.services.ingredient_normalizer import (
    NormalizationResult,
    NormalizedIngredient,
)

__all__ = [
    "RegistryEntry",
    "EntityRegistry",
    "InMemoryRegistry",
    "Candidate",
    "Resolution",
    "ResolutionResult",
    "resolve_node",
    "resolve_entities",
    "RESOLVER_VERSION",
]

RESOLVER_VERSION = "1.0.0"
RESOLVER_METHOD = "deterministic_registry"

STATUS_EXACT = "exact_match"
STATUS_CANDIDATE = "candidate"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNRESOLVED = "unresolved"

CONF_HIGH = "HIGH"
CONF_MEDIUM = "MEDIUM"
CONF_LOW = "LOW"
CONF_UNKNOWN = "UNKNOWN"

METHOD_IDENTIFIER = "exact_identifier"
METHOD_NAME = "exact_normalized_name"
METHOD_ALIAS = "exact_alias"
METHOD_OCR = "controlled_ocr_similarity"
METHOD_CONTEXT = "contextual_candidate"

# Method rank drives deterministic candidate ordering (lower wins).
_METHOD_RANK = {
    METHOD_IDENTIFIER: 0,
    METHOD_NAME: 1,
    METHOD_ALIAS: 2,
    METHOD_OCR: 3,
}

# Ranking-only base scores. NOT probabilities, NOT certainty.
_METHOD_SCORE = {
    METHOD_IDENTIFIER: 1.0,
    METHOD_NAME: 0.95,
    METHOD_ALIAS: 0.85,
}

# OCR-near bounds: maximum edit distance, minimum string lengths.
# Short tokens ("salt", "oil") are excluded: near-matches on them
# are guesses, not candidates.
OCR_MAX_DISTANCE = 2
OCR_MIN_LENGTH = 5

# Hard cap on returned alternatives; overflow is recorded, and the
# status stays ambiguous (never silently narrowed).
MAX_ALTERNATIVES = 8


@dataclass
class RegistryEntry:
    """One explicit registry record. NOT a verified chemical entity.

    ``ref`` is a registry-local reference (e.g. ``TEST-001``), never
    a chemical-entity UUID. ``entity_class`` mirrors the chemistry
    spec vocabulary (mixture, natural_complex, ...) so non-molecular
    terms keep their class instead of being forced into molecules.
    """

    ref: str = ""
    preferred_name: str = ""
    display_name: str = ""
    aliases: List[str] = field(default_factory=list)
    identifiers: List[str] = field(default_factory=list)
    entity_class: str = "unknown"
    contexts: List[str] = field(default_factory=list)
    source: str = ""


@dataclass
class Candidate:
    """One plausible interpretation. Candidate, never verified."""

    candidate_ref: str = ""
    display_name: str = ""
    candidate_type: str = "unknown"
    source: str = ""
    match_method: str = ""
    match_score: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict:
        """JSON-serialisable view (ranking score, not probability)."""
        return {
            "candidate_ref": self.candidate_ref,
            "display_name": self.display_name,
            "candidate_type": self.candidate_type,
            "source": self.source,
            "match_method": self.match_method,
            "match_score": self.match_score,
            "reason": self.reason,
        }


@dataclass
class Resolution:
    """Resolution outcome for one normalized ingredient (tree node)."""

    raw_text: str = ""
    normalized_text: str = ""
    parser_node_id: str = ""
    normalization_id: str = ""
    parent_id: Optional[str] = None
    depth: int = 0
    position: int = 0
    percentage: Optional[float] = None
    identifier: Optional[str] = None
    status: str = STATUS_UNRESOLVED
    candidates: List[Candidate] = field(default_factory=list)
    selected_candidate: Optional[Candidate] = None
    identity_confidence: str = CONF_UNKNOWN
    methods: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    children: List["Resolution"] = field(default_factory=list)

    @property
    def alternatives(self) -> List[Candidate]:
        """Candidates other than the selected one (empty if none)."""
        if self.selected_candidate is None:
            return list(self.candidates)
        return [
            c
            for c in self.candidates
            if c.candidate_ref != self.selected_candidate.candidate_ref
        ]

    def to_dict(self) -> dict:
        """JSON-serialisable view of this node and its subtree."""
        return {
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "parser_node_id": self.parser_node_id,
            "normalization_id": self.normalization_id,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "position": self.position,
            "percentage": self.percentage,
            "identifier": self.identifier,
            "match_status": self.status,
            "identity_confidence": self.identity_confidence,
            "entity": (
                self.selected_candidate.to_dict()
                if self.selected_candidate is not None
                else None
            ),
            "alternatives": [c.to_dict() for c in self.alternatives],
            "methods": list(self.methods),
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class ResolutionResult:
    """Outcome of resolving a full normalized tree."""

    raw_text: str = ""
    nodes: List[Resolution] = field(default_factory=list)
    method: str = RESOLVER_METHOD
    version: str = RESOLVER_VERSION
    status: str = STATUS_UNRESOLVED
    limitations: List[str] = field(default_factory=list)

    def all_nodes(self) -> List[Resolution]:
        """Flat list of every node in document order (DFS)."""
        out: List[Resolution] = []

        def _walk(node: Resolution) -> None:
            out.append(node)
            for child in node.children:
                _walk(child)

        for top in self.nodes:
            _walk(top)
        return out

    def to_dict(self) -> dict:
        """JSON-serialisable view of the whole result."""
        return {
            "raw_text": self.raw_text,
            "nodes": [n.to_dict() for n in self.nodes],
            "method": self.method,
            "version": self.version,
            "status": self.status,
            "limitations": list(self.limitations),
        }


class EntityRegistry(ABC):
    """Provider-independent registry contract (Stage 5 reads only)."""

    registry_id: str = "unspecified"
    version: str = "0"

    @abstractmethod
    def lookup_exact_name(self, key: str) -> List[RegistryEntry]:
        """Entries whose preferred name equals ``key`` (exact)."""

    @abstractmethod
    def lookup_alias(self, key: str) -> List[RegistryEntry]:
        """Entries with an explicit alias equal to ``key`` (exact)."""

    @abstractmethod
    def lookup_identifier(self, code: str) -> List[RegistryEntry]:
        """Entries mapped to an additive code (any spacing accepted)."""

    @abstractmethod
    def iter_names(self) -> List[Tuple[str, RegistryEntry]]:
        """All (preferred-name-or-alias, entry) pairs for OCR scan."""


def _canon_code(code: str) -> str:
    """Canonical identifier form: uppercase, no spaces/dashes."""
    return re.sub(r"[\s\-]+", "", code.strip().upper())


def _canon_text(text: str) -> str:
    """Canonical lookup key: collapsed whitespace, lowercase."""
    return re.sub(r"\s+", " ", text).strip().lower()


class InMemoryRegistry(EntityRegistry):
    """Explicit in-memory registry built from declared entries only.

    No fuzzy invention: aliases and identifiers match exactly as
    declared. An empty entry list is valid and resolves nothing --
    the honest state until trustworthy data is registered.
    """

    def __init__(
        self,
        entries: List[RegistryEntry],
        *,
        registry_id: str = "inmemory",
        version: str = "0",
    ) -> None:
        self.registry_id = registry_id
        self.version = version
        self._entries = list(entries)
        self._by_name: Dict[str, List[RegistryEntry]] = {}
        self._by_alias: Dict[str, List[RegistryEntry]] = {}
        self._by_code: Dict[str, List[RegistryEntry]] = {}
        for entry in self._entries:
            key = _canon_text(entry.preferred_name)
            if key:
                self._by_name.setdefault(key, []).append(entry)
            for alias in entry.aliases:
                akey = _canon_text(alias)
                if akey:
                    self._by_alias.setdefault(akey, []).append(entry)
            for code in entry.identifiers:
                ckey = _canon_code(code)
                if ckey:
                    self._by_code.setdefault(ckey, []).append(entry)

    def lookup_exact_name(self, key: str) -> List[RegistryEntry]:
        return list(self._by_name.get(_canon_text(key), []))

    def lookup_alias(self, key: str) -> List[RegistryEntry]:
        return list(self._by_alias.get(_canon_text(key), []))

    def lookup_identifier(self, code: str) -> List[RegistryEntry]:
        return list(self._by_code.get(_canon_code(code), []))

    def iter_names(self) -> List[Tuple[str, RegistryEntry]]:
        pairs: List[Tuple[str, RegistryEntry]] = []
        for entry in self._entries:
            if entry.preferred_name.strip():
                pairs.append((entry.preferred_name, entry))
            for alias in entry.aliases:
                if alias.strip():
                    pairs.append((alias, entry))
        return pairs


def _levenshtein(a: str, b: str, max_dist: int) -> int:
    """Bounded edit distance; returns > max_dist on early exit."""
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            val = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            cur.append(val)
            if val < row_min:
                row_min = val
        if row_min > max_dist:
            return max_dist + 1
        prev = cur
    return prev[len(b)]


def _match_name_key(node: NormalizedIngredient) -> str:
    """Name portion of the normalized text (identifier excluded).

    The normalizer appends the identifier token to
    ``normalized_text`` (e.g. ``stabilizer INS 471``); name/alias
    lookup must use the name part so codes do not poison matching.
    """
    text = node.normalized_text
    if node.identifier and _contains_code_flat(text, node.identifier):
        text = _remove_code_token(text, node.identifier)
    return _canon_text(text)


def _contains_code_flat(text: str, spaced_code: str) -> bool:
    flat = re.sub(r"[\s\-]+", "", text.upper())
    want = re.sub(r"[\s\-]+", "", spaced_code.upper())
    return want in flat and bool(want)


def _remove_code_token(text: str, spaced_code: str) -> str:
    want = re.sub(r"[\s\-]+", "", spaced_code.upper())
    pattern = re.compile(
        r"\b(?:INS|E|CI)\s*-?\s*\d+[a-z]?\b", re.I
    )
    out = text
    for match in pattern.finditer(text):
        flat = re.sub(r"[\s\-]+", "", match.group(0).upper())
        if flat == want:
            out = (out[: match.start()] + " " + out[match.end():])
            break
    return re.sub(r"\s+", " ", out).strip()


def _ocr_candidates(
    key: str, registry: EntityRegistry
) -> List[Tuple[RegistryEntry, int]]:
    """Bounded controlled-similarity scan; returns (entry, dist)."""
    if len(key) < OCR_MIN_LENGTH:
        return []
    hits: List[Tuple[RegistryEntry, int]] = []
    seen = set()
    for name, entry in registry.iter_names():
        ckey = _canon_text(name)
        if len(ckey) < OCR_MIN_LENGTH or entry.ref in seen:
            continue
        dist = _levenshtein(key, ckey, OCR_MAX_DISTANCE)
        if dist <= OCR_MAX_DISTANCE:
            seen.add(entry.ref)
            hits.append((entry, dist))
    hits.sort(key=lambda h: (h[1], h[0].display_name, h[0].ref))
    return hits


def _make_candidate(
    entry: RegistryEntry,
    method: str,
    score: float,
    reason: str,
) -> Candidate:
    return Candidate(
        candidate_ref=entry.ref,
        display_name=entry.display_name or entry.preferred_name,
        candidate_type=entry.entity_class,
        source=entry.source,
        match_method=method,
        match_score=score,
        reason=reason,
    )


def resolve_node(
    node: NormalizedIngredient,
    registry: EntityRegistry,
    *,
    parent_context: Optional[str] = None,
) -> Resolution:
    """Resolve one normalized ingredient against ``registry``."""
    res = Resolution(
        raw_text=node.raw_text,
        normalized_text=node.normalized_text,
        parser_node_id=node.parser_node_id,
        normalization_id=node.id,
        depth=node.depth,
        position=node.position,
        percentage=node.percentage,
        identifier=node.identifier,
        provenance={
            "source": "label_text",
            "parser_node_id": node.parser_node_id,
            "normalization_id": node.id,
            "resolver_method": RESOLVER_METHOD,
            "resolver_version": RESOLVER_VERSION,
            "registry_id": registry.registry_id,
            "registry_version": registry.version,
        },
    )

    key = _match_name_key(node)
    if not key and not node.identifier:
        res.warnings.append("empty_normalized_text")
        return res

    found: Dict[str, Candidate] = {}
    by_ref: Dict[str, RegistryEntry] = {}

    def _add(entry: RegistryEntry, method: str, reason: str) -> None:
        if entry.ref not in found:
            by_ref[entry.ref] = entry
            found[entry.ref] = _make_candidate(
                entry, method, _METHOD_SCORE[method], reason
            )

    for entry in registry.lookup_identifier(node.identifier or ""):
        if node.identifier:
            _add(
                entry,
                METHOD_IDENTIFIER,
                "identifier %s explicitly mapped in registry %s"
                % (node.identifier, registry.registry_id),
            )
    for entry in registry.lookup_exact_name(key):
        _add(
            entry,
            METHOD_NAME,
            "normalized text exactly equals registered name",
        )
    for entry in registry.lookup_alias(key):
        _add(
            entry,
            METHOD_ALIAS,
            "normalized text exactly equals registered alias",
        )

    exact = list(found.values())
    ocr_hits: List[Candidate] = []
    if not exact:
        for entry, dist in _ocr_candidates(key, registry):
            by_ref.setdefault(entry.ref, entry)
            longest = max(len(key), len(_canon_text(
                entry.preferred_name
            )))
            score = round(1.0 - dist / longest, 4) if longest else 0.0
            if entry.ref not in found:
                ocr_hits.append(
                    _make_candidate(
                        entry,
                        METHOD_OCR,
                        score,
                        "controlled similarity (edit distance %d); "
                        "original text preserved, candidate only"
                        % dist,
                    )
                )

    # Context is a supporting signal only: it annotates candidates
    # found by other methods, never creates a match on its own.
    if parent_context:
        pkey = _canon_text(parent_context)
        for cand in exact + ocr_hits:
            entry = by_ref.get(cand.candidate_ref)
            if entry is not None and any(
                _canon_text(c) == pkey for c in entry.contexts
            ):
                cand.reason += "; parent_context_agreement"
                if METHOD_CONTEXT not in res.methods:
                    res.methods.append(METHOD_CONTEXT)

    ordered = sorted(
        exact + ocr_hits,
        key=lambda c: (
            _METHOD_RANK[c.match_method],
            -c.match_score,
            c.display_name,
            c.candidate_ref,
        ),
    )
    total = len(ordered)
    if total > MAX_ALTERNATIVES:
        res.warnings.append(
            "alternatives_truncated_%d_of_%d" % (MAX_ALTERNATIVES, total)
        )
        ordered = ordered[:MAX_ALTERNATIVES]
    res.candidates = ordered

    for cand in ordered:
        if cand.match_method not in res.methods:
            res.methods.append(cand.match_method)
    res.methods.sort(key=lambda m: _METHOD_RANK.get(m, 99))

    if total == 0:
        res.status = STATUS_UNRESOLVED
        res.identity_confidence = CONF_UNKNOWN
    elif total == 1 and ordered[0].match_method in _METHOD_RANK:
        only = ordered[0]
        if only.match_method == METHOD_OCR:
            res.status = STATUS_CANDIDATE
            res.identity_confidence = CONF_LOW
            res.warnings.append("ocr_near_candidate_only")
        else:
            res.status = STATUS_EXACT
            res.selected_candidate = only
            if only.match_method == METHOD_ALIAS:
                res.identity_confidence = CONF_MEDIUM
            else:
                res.identity_confidence = CONF_HIGH
    else:
        res.status = STATUS_AMBIGUOUS
        if all(
            c.match_method in (
                METHOD_IDENTIFIER,
                METHOD_NAME,
                METHOD_ALIAS,
            )
            for c in ordered
        ):
            res.identity_confidence = CONF_MEDIUM
        else:
            res.identity_confidence = CONF_LOW
        res.warnings.append("ambiguous_requires_clarification")
    return res


def resolve_entities(
    result: NormalizationResult, registry: EntityRegistry
) -> ResolutionResult:
    """Resolve a full normalized tree, preserving structure/links."""
    out = ResolutionResult(raw_text=result.raw_text)
    out.limitations.extend(result.limitations)
    if not result.nodes:
        out.limitations.append("no_normalized_nodes_to_resolve")
        return out

    def _walk(
        node: NormalizedIngredient,
        parent_res_id: Optional[str],
        parent_norm_text: Optional[str],
    ) -> Resolution:
        res = resolve_node(
            node, registry, parent_context=parent_norm_text
        )
        res.parent_id = parent_res_id
        for child in node.children:
            res.children.append(
                _walk(child, res.normalization_id, node.normalized_text)
            )
        return res

    for node in result.nodes:
        out.nodes.append(_walk(node, None, None))

    flat = out.all_nodes()
    counts = [n.status for n in flat]
    if STATUS_EXACT in counts or STATUS_CANDIDATE in counts:
        out.status = (
            STATUS_EXACT if STATUS_EXACT in counts else STATUS_CANDIDATE
        )
    elif STATUS_AMBIGUOUS in counts:
        out.status = STATUS_AMBIGUOUS
    return out
