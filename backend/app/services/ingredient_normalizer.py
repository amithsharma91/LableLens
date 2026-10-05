"""Syntactic normalization layer (Stage 4).

Canonical entry point: :func:`normalize_result` (parser output in,
normalized tree out). Convenience entry point for raw strings:
:func:`normalize_label_text` (parse + normalize).

What this module MAY do (syntactic only):
- Unicode/whitespace/case/punctuation canonicalization.
- Additive-code spacing (``INS471`` -> ``INS 471``, ``E330`` -> ``E 330``).
- Carry parser structure (nesting, percentages, identifiers) forward.

What this module MUST NEVER do (later stages own these):
- Map an alias to a chemical identity (``vitamin C`` stays text).
- Resolve umbrella terms (``natural flavour``, ``fragrance``).
- Correct OCR typos into guessed words (``Sodlum`` stays ``sodlum``,
  flagged at most with ``possible_ocr_variation``).
- Emit SMILES, InChI, CAS, formulas, molecular weights, roles,
  evidence, or any verified claim.

Every output preserves the full chain back to the raw observation:
``raw_text`` + ``parser_node_id`` + tree position + provenance.
Uncertain input keeps its original text and gains a warning;
normalization status degrades to ``partial``/``failed`` instead.

Spec contracts honoured:
- ``DATA_PIPELINE.md`` Stage 4 (status ``complete | partial``,
  ``failed``; normalization is not identity).
- ``DATABASE_SCHEMA.md`` ``ingredient_normalizations`` separation:
  this layer has its own record identity (own ``id``) referencing
  the parser observation via ``parser_node_id``.
- ADR-016: consumes parser nodes; never re-implements tokenizing.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from app.services.ingredient_parser import (
    IngredientNode,
    ParseResult,
    parse_label_ingredients,
)

__all__ = [
    "NormalizedIngredient",
    "NormalizationResult",
    "normalize_node",
    "normalize_result",
    "normalize_label_text",
    "NORMALIZER_VERSION",
]

NORMALIZER_VERSION = "1.0.0"
NORMALIZER_METHOD = "rule"

# Status vocabulary mirrors DATA_PIPELINE.md Stage 4 output contract.
STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

# Deterministic ASCII folding for harmless punctuation variants.
# Maps curly quotes, dashes, ellipsis, and non-breaking spaces to
# their plain equivalents. Letter content is never altered here.
_PUNCT_MAP = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
    "\u00a0": " ",
    "\u2000": " ",
    "\u2001": " ",
    "\u2002": " ",
    "\u2003": " ",
    "\u2007": " ",
    "\u202f": " ",
}

# Additive-code token inside running text, e.g. "ins471", "E 330",
# "ci15985". Requires trailing digits so words like "vitamin e"
# or "ice" are never treated as codes.
_CODE_TOKEN_RE = re.compile(
    r"\b(ins|e|ci)\s*-?\s*(\d+[a-z]?)\b", re.I
)

# Digit buried inside letters, e.g. "glycer1n", "w@ter"-style
# artefacts are covered by _SUSPECT_CHARS. Trailing-digit tokens
# ("B12", "D3", "PEG-40") are legitimate and NOT flagged.
_BURIED_DIGIT_RE = re.compile(r"[A-Za-z]+\d+[A-Za-z]")

# Characters that never belong in a clean label token.
_SUSPECT_CHARS = set("@#$^*_~`|\\")


def _fold_punct(text: str) -> str:
    """Replace known harmless unicode punctuation with ASCII."""
    for src, dst in _PUNCT_MAP.items():
        if src in text:
            text = text.replace(src, dst)
    return text


def _collapse_ws(text: str) -> str:
    """Collapse all whitespace runs (incl. newlines) to one space."""
    return re.sub(r"\s+", " ", text).strip()


def _strip_quotes(text: str) -> str:
    """Remove one layer of surrounding single/double quotes."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        return t[1:-1].strip()
    return t


def _space_code_token(match: "re.Match") -> str:
    """Render an additive-code token as ``PREFIX NUMBER``, uppercase."""
    return "%s %s" % (match.group(1).upper(), match.group(2))


def _canonical_code(code: str) -> str:
    """Spaced uppercase form of a parser identifier, e.g. ``INS 471``."""
    nospace = re.sub(r"[\s\-]+", "", code.strip().upper())
    m = re.match(r"^(INS|E|CI)(\d+[A-Z]?)$", nospace)
    if m:
        return "%s %s" % (m.group(1), m.group(2))
    return code.strip().upper()


def _contains_code(text: str, spaced_code: str) -> bool:
    """True if the spaced code is already represented in the text."""
    flat = re.sub(r"[\s\-]+", "", text.upper())
    want = re.sub(r"[\s\-]+", "", spaced_code.upper())
    return want in flat


@dataclass
class NormalizedIngredient:
    """One syntactically normalized ingredient observation.

    ``raw_text`` is the untouched parser segment. ``normalized_text``
    is the stable canonical string (lowercase, except additive codes).
    No chemistry, identity, role, or evidence fields exist here by
    design -- see the module docstring and the safety regression test.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parser_node_id: str = ""
    parent_id: Optional[str] = None
    raw_text: str = ""
    normalized_text: str = ""
    depth: int = 0
    position: int = 0
    percentage: Optional[float] = None
    identifier: Optional[str] = None
    status: str = STATUS_COMPLETE
    warnings: List[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    children: List["NormalizedIngredient"] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-serialisable view of this node and its subtree."""
        return {
            "id": self.id,
            "parser_node_id": self.parser_node_id,
            "parent_id": self.parent_id,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "depth": self.depth,
            "position": self.position,
            "percentage": self.percentage,
            "identifier": self.identifier,
            "status": self.status,
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class NormalizationResult:
    """Outcome of normalizing one parser ``ParseResult``."""

    raw_text: str = ""
    nodes: List[NormalizedIngredient] = field(default_factory=list)
    method: str = NORMALIZER_METHOD
    version: str = NORMALIZER_VERSION
    status: str = STATUS_COMPLETE
    limitations: List[str] = field(default_factory=list)

    def all_nodes(self) -> List[NormalizedIngredient]:
        """Flat list of every node in document order (DFS)."""
        out: List[NormalizedIngredient] = []

        def _walk(node: NormalizedIngredient) -> None:
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


def _detect_warnings(name: str) -> List[str]:
    """Deterministic syntactic suspicion signals (never corrections)."""
    warnings: List[str] = []
    if any(ch in _SUSPECT_CHARS for ch in name):
        warnings.append("possible_ocr_variation")
    else:
        for token in name.split():
            if _BURIED_DIGIT_RE.search(token):
                warnings.append("possible_ocr_variation")
                break
    return warnings


def _canonical_text(name: str) -> str:
    """Build the stable canonical string for a parser node name."""
    text = _fold_punct(name)
    text = _collapse_ws(text)
    text = _strip_quotes(text)
    text = text.strip(".,;:").strip()
    text = _collapse_ws(text).lower()
    text = _CODE_TOKEN_RE.sub(_space_code_token, text)
    return _collapse_ws(text)


def normalize_node(
    node: IngredientNode,
    *,
    parent_id: Optional[str] = None,
    warnings_inherit: Optional[List[str]] = None,
) -> NormalizedIngredient:
    """Normalize one parser node (recursive over its children)."""
    out = NormalizedIngredient(
        parser_node_id=node.id,
        parent_id=parent_id,
        raw_text=node.raw_text,
        depth=node.depth,
        position=node.position,
        percentage=node.percentage,
        provenance={
            "source": "label_text",
            "parser_node_id": node.id,
            "parser_version": node.provenance.get("parser_version"),
            "normalizer_method": NORMALIZER_METHOD,
            "normalizer_version": NORMALIZER_VERSION,
        },
    )

    if not node.raw_text and not node.name:
        out.normalized_text = ""
        out.status = STATUS_FAILED
        out.warnings.append("empty_observation")
        return out

    text = _canonical_text(node.name)
    identifier: Optional[str] = None
    if node.identifier is not None:
        identifier = _canonical_code(node.identifier)
        if text and not _contains_code(text, identifier):
            text = "%s %s" % (text, identifier)
        elif not text:
            text = identifier

    out.normalized_text = text
    out.identifier = identifier
    out.warnings.extend(_detect_warnings(node.name))
    if warnings_inherit:
        out.warnings.extend(warnings_inherit)
    if node.confidence != "high":
        out.warnings.append("uncertain_parse_%s" % node.confidence)
    if out.warnings:
        out.status = STATUS_PARTIAL

    for child in node.children:
        out.children.append(
            normalize_node(child, parent_id=out.id)
        )
    return out


def normalize_result(parse: ParseResult) -> NormalizationResult:
    """Normalize a full parser ``ParseResult``, preserving the tree."""
    result = NormalizationResult(raw_text=parse.raw_text)
    result.limitations.extend(parse.limitations)
    if not parse.nodes:
        result.status = STATUS_FAILED
        result.limitations.append("no_parser_nodes_to_normalize")
        return result
    for node in parse.nodes:
        result.nodes.append(normalize_node(node))
    flat = result.all_nodes()
    if any(n.status == STATUS_FAILED for n in flat):
        result.status = STATUS_FAILED
    elif (
        any(n.status == STATUS_PARTIAL for n in flat)
        or result.limitations
    ):
        result.status = STATUS_PARTIAL
    return result


def normalize_label_text(text: str) -> NormalizationResult:
    """Convenience entry point: parse raw label text, then normalize."""
    return normalize_result(parse_label_ingredients(text))
