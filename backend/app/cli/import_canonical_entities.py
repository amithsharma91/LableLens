"""Canonical entity import: the one controlled registration path.

    DATABASE_URL=... ENTITY_IMPORT_CONFIRM=service-role \
        python -m app.cli.import_canonical_entities

This is an administrative import, not an API endpoint. It requires
direct database credentials (the service role), and refuses to run
without an explicit confirmation value so a stray shell invocation
cannot populate the canonical registry. Nothing here is reachable
from the HTTP application: there is no route, no dependency, and no
auth role that maps to it.

The import is deterministic and idempotent. Running it twice reports
the same records as already present and creates no duplicates. A
rejected record aborts the whole run (all-or-nothing) with a
deterministic report; the transaction is rolled back, so no partial
state survives a failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.repositories.postgres import PostgresUnitOfWork
from app.services.registration import (
    RegistrationError,
    RegistrationRejected,
    register_canonical_entities,
)
from app.services.verification.adapters.snapshot import (
    SnapshotAdapter,
    SnapshotError,
)
from app.services.verification.gate import VERIFICATION_RULES_VERSION

__all__ = ["main", "run_import"]

logger = logging.getLogger("labellens.import")

CONFIRM_VALUE = "service-role"
EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_ERROR = 2


def _default_snapshot_path() -> str:
    if settings.snapshot_path:
        return settings.snapshot_path
    candidate = (
        Path(__file__).resolve().parents[3] / "snapshots"
        / "canonical_v1.json"
    )
    return str(candidate) if candidate.exists() else ""


async def run_import(
    *,
    database_url: str,
    snapshot_path: str,
    expected_snapshot_version: Optional[str] = None,
    rules_version: str = VERIFICATION_RULES_VERSION,
) -> dict:
    """Register the approved snapshot records; return the report."""
    adapter = SnapshotAdapter(snapshot_path)
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        unit_of_work = PostgresUnitOfWork(engine)
        report = await register_canonical_entities(
            unit_of_work,
            adapter,
            expected_snapshot_version=expected_snapshot_version or None,
            rules_version=rules_version,
        )
    finally:
        await engine.dispose()
    return report.as_dict()


def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="import_canonical_entities",
        description=(
            "Register approved canonical snapshot records in "
            "chemical_entities (service role)."
        ),
    )
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--snapshot", default="")
    parser.add_argument(
        "--expect-snapshot-version",
        default=settings.expected_snapshot_version,
    )
    parser.add_argument(
        "--rules-version", default=VERIFICATION_RULES_VERSION,
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point. Prints a deterministic JSON report on stdout."""
    logging.basicConfig(level=logging.INFO)
    args = _parse_args(argv)
    if settings.entity_import_confirm.strip() != CONFIRM_VALUE:
        print(
            "refused: set ENTITY_IMPORT_CONFIRM=service-role to confirm "
            "this service-role database operation",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    snapshot_path = args.snapshot or _default_snapshot_path()
    if not snapshot_path:
        print("refused: no snapshot path configured", file=sys.stderr)
        return EXIT_REFUSED
    try:
        report = asyncio.run(
            run_import(
                database_url=args.database_url,
                snapshot_path=snapshot_path,
                expected_snapshot_version=args.expect_snapshot_version,
                rules_version=args.rules_version,
            )
        )
    except RegistrationRejected as exc:
        print(
            json.dumps(exc.report.as_dict(), indent=2, sort_keys=True),
            file=sys.stderr,
        )
        return EXIT_REFUSED
    except SnapshotError as exc:
        print("snapshot rejected: %s" % exc, file=sys.stderr)
        return EXIT_REFUSED
    except RegistrationError as exc:
        print("import refused: %s" % exc, file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps(report, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
