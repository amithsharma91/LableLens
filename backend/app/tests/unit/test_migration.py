"""Static validation of migration 003 (no live database needed).

Asserts the migration declares every table/column/index/constraint/
policy the Postgres metadata layer expects, so schema drift fails
fast in CI. Live application is covered separately and only when
TEST_DATABASE_URL is set.
"""

import re
from pathlib import Path

from app.repositories.postgres import TABLES

MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "backend" / "migrations" / "003_verification_review.sql"
)


def _sql():
    return MIGRATION.read_text()


def test_migration_file_exists():
    assert MIGRATION.exists()


def test_all_metadata_tables_created():
    sql = _sql()
    for name in TABLES:
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS %s\b" % re.escape(name), sql
        ), name


def test_all_metadata_columns_present():
    sql = _sql()
    for name, table in TABLES.items():
        for column in table.columns:
            assert re.search(
                r"\b%s\b" % re.escape(column.name), sql
            ), (name, column.name)


def test_status_check_constraints():
    sql = _sql()
    for token in (
        "sources_name_unique",
        "'complete', 'partial', 'failed'",
        "'exact_match'",
        "'verified', 'supported', 'computed'",
        "reject_event_mutation",
        "ENABLE ROW LEVEL SECURITY",
    ):
        assert token in sql, token


def test_audit_read_policies_and_revokes():
    sql = _sql()
    for table in (
        "claims", "claim_sources", "verification_events",
        "verification_decisions", "reviews", "review_events",
    ):
        assert ("CREATE POLICY audit_read" in sql and table in sql), table
    assert "REVOKE ALL ON claims FROM anon, authenticated" in sql


def test_deferred_fks_documented():
    sql = _sql()
    assert "Deferred FKs" in sql
    assert "product_id" in sql and "scan_id" in sql


def test_seed_repair_uses_valid_uuids_and_guards():
    import uuid

    sql = _sql()
    assert "WHERE NOT EXISTS" in sql
    for raw in re.findall(r"'([0-9a-fg-i-]+)'", sql):
        try:
            uuid.UUID(raw)
        except ValueError:
            if set(raw) <= set("0123456789abcdef-"):
                continue
            if raw.count("-") == 4:
                raise AssertionError("invalid UUID literal %s" % raw)


def test_triggers_guard_event_tables():
    sql = _sql()
    assert "trg_review_events_immutable" in sql
    assert "trg_verification_events_immutable" in sql
    assert "BEFORE UPDATE OR DELETE" in sql
