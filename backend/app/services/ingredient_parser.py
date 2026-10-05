"""Canonical hierarchical ingredient parser (Stage 2 extraction).

This module is the SINGLE canonical entry point for turning raw label
text into a structured ingredient tree. All future paths (OCR
post-processing, manual-text entry, re-analysis after user correction,
seed scripts, tests) must call :func:`parse_label_ingredients`.
No UI or service code may implement its own ``split(",")``.

Spec contracts honoured:
- ``DATA_PIPELINE.md`` Stage 2 (extraction preserves raw observation,
  extraction confidence tracked separately from OCR confidence).
- ``CHEMISTRY_DATA_SPEC.md`` mixture rule: this parser is
  chemistry-free. It extracts structure (nesting, percentages,
  additive identifiers) and performs only *syntactic* normalization
  (case/whitespace/punctuation). It never guesses entities, formulas,
  SMILES, CAS numbers, roles, or safety verdicts.
- ``EVIDENCE_AND_CONFIDENCE_SPEC.md``: raw text preserved per node,
  parsing confidence kept separate from any future identity
  confidence. Nodes start as ``match_status="unresolved"`` and
  ``verification_status="unverified"`` by construction.

Supported syntax (deterministic, no network, no AI):
- ``()``, ``[]``, ``{}`` grouping with arbitrary nesting and mixing.
- Top-level ``,`` and ``;`` separators (depth-0, outside quotes).
- Single/double quoted spans protecting embedded delimiters.
- Percentages (``68%``, ``(68%)``, ``68.5 %``) attached to a node.
- Additive identifiers (``INS471``, ``INS 471``, ``E330``, ``E 330``).
- Newline/whitespace OCR artefacts collapsed; newlines act as a
  fallback separator only when no top-level comma/semicolon exists.
- Malformed input (unbalanced brackets, unclosed quotes, stray
  closers, empty segments) never raises: the remainder is kept as
  literal text, confidence is downgraded, and a limitation recorded.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

__all__ = [
    "IngredientNode",
    "ParseResult",
    "parse_label_ingredients",
    "PARSER_VERSION",
]

PARSER_VERSION = "1.0.0"
CANONICAL_METHOD = "canonical_hierarchical_parser"

_OPENERS = "([{"
_CLOSERS = ")]}"
_MATCH = {"(": ")", "[": "]", "{": "}"}
_REV_MATCH = {")": "(", "]": "[", "}": "{"}

# e.g. "68%", "68.5 %", "10 %" (full-string match after strip).
_PERCENT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*%$")
# Trailing bare percentage without parens, e.g. "Sugar 20%".
_TRAILING_PERCENT_RE = re.compile(
    r"^(?P<head>.*?)(?P<val>\d+(?:\.\d+)?)\s*%\s*$"
)
# e.g. "INS471", "INS 471", "INS-471", "E330", "E 330" (full match).
_IDENTIFIER_RE = re.compile(r"^(?:INS|E)\s*-?\s*\d+[a-zA-Z]?$", re.I)
# Trailing bare identifier without parens, e.g. "Stabilizer INS471".
_TRAILING_ID_RE = re.compile(
    r"^(?P<head>.*?)(?P<tag>(?:INS|E)\s*-?\s*\d+[a-zA-Z]?)\s*$", re.I
)


@dataclass
class IngredientNode:
    """One structured ingredient observation.

    ``raw_text`` is the exact original segment (never destroyed).
    ``name`` is the cleaned display name (annotations removed).
    ``normalized_name`` is syntactic only (lowercase/whitespace/
    punctuation); it must NOT change chemical identity.
    Chemistry/entity fields stay empty until later pipeline stages.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    raw_text: str = ""
    name: str = ""
    normalized_name: str = ""
    parent_id: Optional[str] = None
    depth: int = 0
    position: int = 0
    percentage: Optional[float] = None
    identifier: Optional[str] = None
    children: List["IngredientNode"] = field(default_factory=list)
    classification: str = "ingredient"
    match_status: str = "unresolved"
    confidence: str = "high"
    verification_status: str = "unverified"
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """JSON-serialisable view of this node and its subtree."""
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "position": self.position,
            "percentage": self.percentage,
            "identifier": self.identifier,
            "children": [c.to_dict() for c in self.children],
            "classification": self.classification,
            "match_status": self.match_status,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "provenance": dict(self.provenance),
        }


@dataclass
class ParseResult:
    """Outcome of parsing one raw label string."""

    raw_text: str = ""
    nodes: List[IngredientNode] = field(default_factory=list)
    method: str = CANONICAL_METHOD
    version: str = PARSER_VERSION
    status: str = "complete"  # complete | partial
    limitations: List[str] = field(default_factory=list)

    def all_nodes(self) -> List[IngredientNode]:
        """Flat list of every node in document order (DFS)."""
        out: List[IngredientNode] = []

        def _walk(node: IngredientNode) -> None:
            out.append(node)
            for child in node.children:
                _walk(child)

        for top in self.nodes:
            _walk(top)
        return out

    def to_dict(self) -> dict:
        """JSON-serialisable view of the whole parse result."""
        return {
            "raw_text": self.raw_text,
            "nodes": [n.to_dict() for n in self.nodes],
            "method": self.method,
            "version": self.version,
            "status": self.status,
            "limitations": list(self.limitations),
        }


def _collapse_ws(text: str) -> str:
    """Collapse all whitespace runs (incl. newlines) to one space."""
    return re.sub(r"\s+", " ", text).strip()


def _strip_quotes(text: str) -> str:
    """Remove one layer of surrounding single/double quotes."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        return t[1:-1].strip()
    return t


def _normalize_identifier(tag: str) -> str:
    """Canonical syntactic form: uppercase, no spaces/dashes."""
    return re.sub(r"[\s\-]+", "", tag.strip().upper())


def _normalize_name(name: str) -> str:
    """Syntactic normalization only. Never maps synonyms/identity."""
    t = _collapse_ws(name).lower()
    t = _strip_quotes(t)
    t = t.strip(".,;:").strip()
    return _collapse_ws(t)


def _split_top_level(text: str, limitations: List[str]) -> List[str]:
    """Split on depth-0 commas/semicolons, respecting brackets/quotes.

    Never raises on malformed input: unbalanced openers keep the
    remainder literal, stray closers are literal, an unclosed quote
    quotes the remainder. Each anomaly appends a limitation.
    """
    segments: List[str] = []
    buf: List[str] = []
    stack: List[str] = []
    quote: Optional[str] = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in _OPENERS:
            stack.append(ch)
            buf.append(ch)
            i += 1
            continue
        if ch in _CLOSERS:
            if stack and _MATCH[stack[-1]] == ch:
                stack.pop()
                buf.append(ch)
            else:
                buf.append(ch)
                limitations.append(
                    "stray_closer_%s_kept_literal" % ch
                )
            i += 1
            continue
        if ch in (",", ";") and not stack:
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segments.append("".join(buf))
    if quote is not None:
        limitations.append("unclosed_quote_kept_literal")
    if stack:
        limitations.append(
            "unbalanced_opener_%s_kept_literal" % "".join(stack)
        )
    return segments


def _split_head_groups(segment: str) -> tuple:
    """Split ``HEAD (g1) [g2] {g3}`` into head + trailing groups.

    Only groups at depth 0 relative to the segment are considered,
    scanned from the end so inner nesting stays intact. Returns
    ``(head, [(opener, content), ...])`` in source order.
    """
    text = segment.strip()
    groups: List[tuple] = []
    while text.endswith(tuple(_CLOSERS)):
        closer = text[-1]
        opener = _REV_MATCH[closer]
        depth = 0
        quote: Optional[str] = None
        start = -1
        for i in range(len(text) - 1, -1, -1):
            ch = text[i]
            if quote is not None:
                if ch == quote:
                    # Ignore escaped quotes on backward scan.
                    quote = None
                continue
            if ch in ("'", '"'):
                quote = ch
                continue
            if ch == closer:
                depth += 1
            elif ch == opener:
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start < 0:
            break  # Unbalanced trailing closer: keep literal.
        # The group must be trailing (only whitespace after it).
        content = text[start + 1:len(text) - 1]
        groups.append((opener, content))
        text = text[:start].strip()
        if not text:
            break
    groups.reverse()
    return text, groups


def _parse_segment(
    segment: str,
    *,
    parent_id: Optional[str],
    depth: int,
    position: int,
    limitations: List[str],
) -> Optional[IngredientNode]:
    """Parse one delimiter-free segment into a node (recursive)."""
    raw = segment.strip()
    if not raw:
        limitations.append("empty_segment_skipped")
        return None

    head, groups = _split_head_groups(raw)

    percentage: Optional[float] = None
    identifier: Optional[str] = None
    child_sources: List[str] = []
    node_conf = "high"

    for _opener, content in groups:
        c = content.strip()
        if _PERCENT_RE.match(c):
            percentage = float(_PERCENT_RE.match(c).group(1))
        elif _IDENTIFIER_RE.match(c):
            identifier = _normalize_identifier(c)
        else:
            child_sources.append(c)

    # Bare trailing annotations without brackets: "Sugar 20%",
    # "Stabilizer INS471". Identifier check runs on the head that
    # remains after percentage removal so "X 10% INS471" works.
    m_pct = _TRAILING_PERCENT_RE.match(head)
    if m_pct and percentage is None:
        percentage = float(m_pct.group("val"))
        head = m_pct.group("head").strip()
    m_id = _TRAILING_ID_RE.match(head)
    if m_id and identifier is None:
        identifier = _normalize_identifier(m_id.group("tag"))
        head = m_id.group("head").strip()

    name = _strip_quotes(_collapse_ws(head).strip(".,;:").strip())
    if not name:
        # Segment was only annotations, e.g. "(10%)" alone.
        limitations.append("annotation_only_segment_kept_literal")
        name = _collapse_ws(raw)
        node_conf = "low"
    if not child_sources and groups:
        # All trailing groups were annotations, nothing nested.
        pass

    node = IngredientNode(
        raw_text=raw,
        name=name,
        normalized_name=_normalize_name(name) if name else "",
        parent_id=parent_id,
        depth=depth,
        position=position,
        percentage=percentage,
        identifier=identifier,
        classification=(
            "additive" if identifier is not None else "ingredient"
        ),
        match_status="unresolved",
        confidence=node_conf,
        verification_status="unverified",
        provenance={
            "source": "label_text",
            "extraction_method": CANONICAL_METHOD,
            "parser_version": PARSER_VERSION,
        },
    )

    for idx, child_text in enumerate(child_sources):
        for pos, part in enumerate(
            _split_top_level(child_text, limitations)
        ):
            child = _parse_segment(
                part,
                parent_id=node.id,
                depth=depth + 1,
                position=pos,
                limitations=limitations,
            )
            if child is not None:
                # Reassign position after empty-segment filtering.
                child.position = len(node.children)
                node.children.append(child)
    if node_conf == "high" and any(
        L.startswith("unbalanced_opener")
        or L.startswith("unclosed_quote")
        for L in limitations
    ):
        node.confidence = "low"
    return node


def _strip_leader(text: str) -> str:
    """Remove a leading ``Ingredients:`` label header if present.

    Real labels prefix the list ("Ingredients: water, ...",
    DATA_PIPELINE.md Stage 2 example). The header is list chrome,
    not an ingredient; stripping it is syntactic, not chemical.
    """
    return re.sub(r"^\s*ingredients\s*:\s*", "", text, flags=re.I)


def parse_label_ingredients(text: str) -> ParseResult:
    """Parse raw label text into a hierarchical ingredient tree.

    This is the canonical Stage-2 extraction entry point. Input is
    treated as an *observation* (raw OCR or user-entered text); output
    nodes are *structured observations*, not verified chemistry.
    """
    raw = text if isinstance(text, str) else ""
    result = ParseResult(raw_text=raw)
    if not raw or not raw.strip():
        result.status = "partial"
        result.limitations.append("empty_input")
        return result

    body = _strip_leader(raw)

    # Newlines are whitespace unless the text has no other top-level
    # separators, in which case each non-empty line is one ingredient
    # (covers OCR output that lost its commas).
    probe = _split_top_level(body, [])
    if len(probe) == 1 and "\n" in body:
        lines = [ln for ln in body.split("\n") if ln.strip()]
        if len(lines) > 1:
            segments = lines
        else:
            segments = _split_top_level(body, result.limitations)
    else:
        segments = _split_top_level(body, result.limitations)

    for seg in segments:
        node = _parse_segment(
            seg,
            parent_id=None,
            depth=0,
            position=len(result.nodes),
            limitations=result.limitations,
        )
        if node is not None:
            result.nodes.append(node)

    if result.limitations:
        result.status = "partial"
    if not result.nodes and raw.strip():
        result.status = "partial"
        result.limitations.append("no_ingredients_extracted")
    return result
