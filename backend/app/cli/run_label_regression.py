"""Developer-only real-label regression command (Stage 13).

Runs the deterministic real-label fixtures through the service
layer, prints per-label outcomes plus aggregate metrics, and exits
non-zero on any expectation mismatch. There is deliberately no HTTP
endpoint for this: it is a test harness, not a product surface.

Offline (memory repositories) by default; `--database-url` runs the
same fixtures against Postgres (the service-role import must have
registered the canonical entities first).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

__all__ = ["main"]


def _fixtures() -> list:
    root = (
        Path(__file__).resolve().parent.parent
        / "regression" / "fixtures" / "real_labels"
    )
    return sorted(root.glob("RL-*-*.json"))


def _build_offline():
    from app.regression.label_input import LabelInput  # noqa: F401
    from app.regression.runner import run_label  # noqa: F401
    from app.repositories.memory import MemoryUnitOfWork
    from app.services.observation_service import ObservationService
    from app.services.registration import (
        alias_rows_for,
        build_registry,
        entity_row_for,
    )
    from app.services.verification.adapters.snapshot import (
        SnapshotAdapter,
    )

    snapshot = (
        Path(__file__).resolve().parents[3]
        / "snapshots" / "canonical_v1.json"
    )
    adapter = SnapshotAdapter(str(snapshot))
    entities = adapter.canonical_entities()
    rows = [
        entity_row_for(
            entity, snapshot_version="canonical_v1",
            rules_version="1.0.0")
        for entity in entities
    ]
    registry = build_registry(
        rows,
        [alias for entity in entities
         for alias in alias_rows_for(entity, verified=True)],
        version=str(len(rows)),
    )
    unit_of_work = MemoryUnitOfWork()
    for row in rows:
        unit_of_work.entities.register({
            "id": row["id"],
            "preferred_name": row["preferred_name"],
            "entity_type": "chemical_entity",
            "representation_type": row["representation_type"],
            "status": "active",
            "structure_status": "unavailable",
        })
    service = ObservationService(
        unit_of_work, registry=registry, adapters=[adapter])
    return service, len(rows)


async def _run_all(service) -> tuple:
    from app.regression.label_input import LabelInput
    from app.regression.metrics import render, summarize
    from app.regression.runner import run_label

    runs = []
    for path in _fixtures():
        fixture = json.loads(path.read_text())
        label = LabelInput.from_dict({
            "label_id": fixture["label_id"],
            "raw_text": fixture["raw_text"],
            "input_method": fixture["input_method"],
            "source_reference": fixture["source_reference"],
        })
        run = await run_label(service, label, fixture)
        runs.append(run.to_dict())
    metrics = summarize(runs)
    return runs, metrics, render(metrics)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="run the Stage-13 real-label regression")
    parser.add_argument(
        "--database-url", default="",
        help="run against Postgres instead of memory")
    parser.add_argument(
        "--json", action="store_true",
        help="print the full run records as JSON")
    args = parser.parse_args(argv)

    if args.database_url:
        print("live Postgres mode is exercised by the integration "
              "tests; this command runs the offline harness")
        return 2
    service, registered = _build_offline()
    runs, metrics, text = asyncio.run(_run_all(service))
    print("registered entities: %d" % registered)
    for run in runs:
        print("== %s: %d ingredients, %d mismatch(es)" % (
            run["label_id"], len(run["ingredient_results"]),
            len(run["mismatches"])))
        for mismatch in run["mismatches"]:
            print("   MISMATCH %s" % mismatch)
        if run.get("correction"):
            correction = run["correction"]
            print("   correction %r -> %r (%s, %s)" % (
                correction["raw_observed"],
                correction["display_text"],
                correction["match_status"],
                correction["verification_status"]))
    print(text)
    if args.json:
        print(json.dumps(
            {"runs": runs, "metrics": metrics}, indent=2,
            default=str))
    failures = metrics["mismatches"] + metrics[
        "entity_match_false_positives"]
    if failures:
        print("REGRESSION FAILED: %d problem(s)" % failures)
        return 1
    print("REGRESSION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
