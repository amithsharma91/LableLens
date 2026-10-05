"""Deterministic Stage-13 metrics over real-label runs.

Counts only what the pipeline produced; no accuracy claim, no AI
score. Verification coverage is the share of resolved ingredients
(exact or candidate matches) that reached a terminal verified or
provisional decision. The entity-match false-positive count is the
number of ingredients the fixture expects to be unknown that
nevertheless received a canonical entity -- any nonzero value is a
failure, not a statistic to admire.
"""

from __future__ import annotations

from typing import Any, Dict, List

__all__ = ["summarize", "render"]


def summarize(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "labels_processed": len(runs),
        "ingredients_observed": 0,
        "ingredients_normalized": 0,
        "exact_matches": 0,
        "alias_matches": 0,
        "candidate_matches": 0,
        "ambiguous": 0,
        "unresolved": 0,
        "verified": 0,
        "provisional": 0,
        "unverified": 0,
        "conflicted": 0,
        "unknown": 0,
        "mismatches": 0,
        "entity_match_false_positives": 0,
        "unknown_count": 0,
    }
    for run in runs:
        for result in run.get("ingredient_results", []):
            metrics["ingredients_observed"] += 1
            if result.get("normalized_text"):
                metrics["ingredients_normalized"] += 1
            status = result.get("match_status")
            if status == "exact_match":
                metrics["exact_matches"] += 1
            elif status == "candidate":
                metrics["candidate_matches"] += 1
            elif status == "ambiguous":
                metrics["ambiguous"] += 1
            elif status == "unresolved":
                metrics["unresolved"] += 1
            verdict = result.get("verification_status")
            if verdict in metrics:
                metrics[verdict] += 1
            if verdict == "unknown":
                metrics["unknown_count"] += 1
        metrics["mismatches"] += len(run.get("mismatches", []))
    metrics["entity_match_false_positives"] = _false_positives(runs)
    resolved = (
        metrics["exact_matches"] + metrics["alias_matches"]
        + metrics["candidate_matches"]
    )
    decided = metrics["verified"] + metrics["provisional"]
    metrics["verification_coverage"] = (
        round(decided / resolved, 4) if resolved else 0.0
    )
    return metrics


def _false_positives(runs: List[Dict[str, Any]]) -> int:
    """Unknown-expected ingredients that still received an entity."""
    count = 0
    for run in runs:
        expected_unknown = set(
            run.get("expected_unknowns") or [])
        for result in run.get("ingredient_results", []):
            if (
                result.get("normalized_text") in expected_unknown
                and result.get("entity_ref")
            ):
                count += 1
    return count


def render(metrics: Dict[str, Any]) -> str:
    lines = ["labels=%d ingredients=%d normalized=%d" % (
        metrics["labels_processed"],
        metrics["ingredients_observed"],
        metrics["ingredients_normalized"])]
    lines.append("match: exact=%d alias=%d candidate=%d ambiguous=%d "
                 "unresolved=%d" % (
                     metrics["exact_matches"],
                     metrics["alias_matches"],
                     metrics["candidate_matches"],
                     metrics["ambiguous"],
                     metrics["unresolved"]))
    lines.append("verify: verified=%d provisional=%d unverified=%d "
                 "conflicted=%d unknown=%d" % (
                     metrics["verified"],
                     metrics["provisional"],
                     metrics["unverified"],
                     metrics["conflicted"],
                     metrics["unknown"]))
    lines.append(
        "false_positives=%d unknown=%d coverage=%s mismatches=%d"
        % (metrics["entity_match_false_positives"],
           metrics["unknown_count"],
           metrics["verification_coverage"],
           metrics["mismatches"]))
    return "\n".join(lines)
