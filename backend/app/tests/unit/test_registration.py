"""Canonical registration safety tests (Stage 12, offline).

Uses the real approved snapshot artifact through the real parser and
the real service, with memory repositories. Every fixture builds
records through the immutable snapshot structure, so a record can only
be *approved* by editing that structure -- there is no shortcut that
skips validation.

The safety matrix required for this stage is covered here:
valid import, malformed record, missing provenance, wrong
verification state, unsupported entity type, duplicate idempotency,
wrong snapshot version, wrong rules version, mixture preserved, no
chemistry inference, provenance preserved, and no partial state after
a refused transaction.
"""

import copy
import json

import pytest

from app.repositories.memory import MemoryUnitOfWork
from app.services.registration import (
    ALLOWED_ENTITY_TYPES,
    RegistrationError,
    RegistrationRejected,
    build_registry,
    canonical_entity_uuid,
    empty_registry,
    entity_row_for,
    load_registry_from_repository,
    register_canonical_entities,
)
from app.services.verification.adapters.snapshot import SnapshotError
from app.services.verification.gate import VERIFICATION_RULES_VERSION

from app.tests.api.helpers import SNAPSHOT_PATH


def _payload():
    return json.loads(SNAPSHOT_PATH.read_text())


def _write_snapshot(tmp_path, payload):
    path = tmp_path / "canonical_test.json"
    path.write_text(json.dumps(payload))
    return str(path)


def _adapter(tmp_path, mutate=None, *, rules_version=None,
             snapshot_version=None):
    from app.services.verification.adapters.snapshot import SnapshotAdapter

    payload = _payload()
    if rules_version is not None:
        payload["verification_rule_version"] = rules_version
    if snapshot_version is not None:
        payload["snapshot_version"] = snapshot_version
    if mutate is not None:
        mutate(payload)
    return SnapshotAdapter(_write_snapshot(tmp_path, payload))


async def _register(adapter, uow=None, **kwargs):
    uow = uow or MemoryUnitOfWork()
    report = await register_canonical_entities(uow, adapter, **kwargs)
    return report, uow


# -- the approved artifact itself --------------------------------------


async def test_approved_snapshot_imports_every_record(tmp_path):
    report, uow = await _register(_adapter(tmp_path))
    assert report.considered == 4
    assert report.registered == 4
    assert report.already_present == 0
    assert report.rejected == 0
    assert report.snapshot_version == "canonical_v1"
    assert report.rules_version == VERIFICATION_RULES_VERSION
    assert len(await uow.entities.list_entities(role="service")) == 4


async def test_report_is_deterministic_and_serialisable(tmp_path):
    report, _ = await _register(_adapter(tmp_path))
    payload = report.as_dict()
    assert payload["records_registered"] == 4
    assert payload["records_rejected"] == 0
    assert payload["rejections"] == []
    # No timestamps: the same import yields byte-identical output.
    assert json.dumps(payload, sort_keys=True) == json.dumps(
        report.as_dict(), sort_keys=True)
    assert "secret" not in json.dumps(payload).lower()


async def test_valid_record_persists_approved_fields_only(tmp_path):
    _, uow = await _register(_adapter(tmp_path))
    rows = {row["id"]: row for row in
            await uow.entities.list_entities(role="service")}
    citric = next(
        row for row in rows.values()
        if row["preferred_name"] == "citric acid")
    # Values are transcribed from the approved snapshot, verbatim.
    assert citric["formula"] == "C6H8O7"
    assert citric["inchikey"] == "KRKNYBCHXYNGOX-UHFFFAOYSA-N"
    assert float(citric["molecular_weight"]) == 192.12
    assert citric["molecular_weight_unit"] == "g/mol"
    assert citric["pubchem_cid"] == 311
    assert citric["status"] == "verified"
    assert citric["entity_type"] in ALLOWED_ENTITY_TYPES


# -- idempotency -------------------------------------------------------


async def test_second_import_creates_no_duplicates(tmp_path):
    adapter = _adapter(tmp_path)
    uow = MemoryUnitOfWork()
    first = await register_canonical_entities(uow, adapter)
    assert first.registered == 4
    assert first.already_present == 0

    second = await register_canonical_entities(uow, adapter)
    assert second.registered == 0
    assert second.already_present == 4
    assert len(await uow.entities.list_entities(role="service")) == 4


async def test_import_is_idempotent_across_a_second_run(tmp_path):
    """Same artifact re-parsed from disk: one identity per record."""
    uow = MemoryUnitOfWork()
    await register_canonical_entities(uow, _adapter(tmp_path))
    first_ids = {row["id"] for row in
                 await uow.entities.list_entities(role="service")}
    second = await register_canonical_entities(
        uow, _adapter(tmp_path), expected_snapshot_version="canonical_v1")
    second_ids = {row["id"] for row in
                  await uow.entities.list_entities(role="service")}
    assert second.already_present == 4
    assert first_ids == second_ids
    assert len(first_ids) == 4


def test_entity_id_mapping_is_stable_and_deterministic():
    uuid_id = "2671a263-ff76-4c1b-9b07-d3d8c521db1e"
    assert canonical_entity_uuid(uuid_id) == uuid_id
    # A non-UUID stable identifier maps deterministically, so repeated
    # imports resolve to one row.
    assert canonical_entity_uuid("citric-acid") == \
        canonical_entity_uuid("citric-acid")
    assert canonical_entity_uuid("citric-acid") != \
        canonical_entity_uuid("glycerol")


# -- refusal matrix ----------------------------------------------------


def _drop_provenance(payload):
    payload["records"][0]["provenance"]["record_locator"] = ""


def _clear_source(payload):
    payload["records"][0]["provenance"]["source_id"] = ""


def _provisional(payload):
    payload["records"][0]["verification_status"] = "provisional"


def _unverified_state(payload):
    payload["records"][0]["verification_status"] = "unverified"


def _bad_entity_type(payload):
    payload["records"][0]["entity_type"] = "product"


def _bad_representation(payload):
    payload["records"][0]["representation_type"] = "not_a_type"


def _no_identifiers(payload):
    payload["records"][0]["identifiers"] = []


def _missing_name(payload):
    payload["records"][0]["preferred_name"] = "  "


def _missing_verified_at(payload):
    payload["records"][0]["verified_at"] = ""


def _bad_pubchem(payload):
    payload["records"][0]["identifiers"] = [
        {"id_type": "pubchem_cid", "value": "not-a-number"}
    ]


def _duplicate_ids(payload):
    payload["records"][1]["entity_id"] = payload["records"][0]["entity_id"]


@pytest.mark.parametrize(
    "mutate,fragment",
    [
        (_drop_provenance, "provenance locator"),
        (_clear_source, "provenance source"),
        (_provisional, "not approved"),
        (_bad_entity_type, "entity type"),
        (_no_identifiers, "identity identifiers"),
        (_missing_name, "preferred name"),
        (_missing_verified_at, "verification date"),
        (_bad_pubchem, "pubchem_cid"),
        (_duplicate_ids, "duplicate"),
    ],
)
async def test_invalid_record_refuses_the_whole_import(
    tmp_path, mutate, fragment
):
    adapter = _adapter(tmp_path, mutate)
    uow = MemoryUnitOfWork()
    with pytest.raises(RegistrationRejected) as excinfo:
        await register_canonical_entities(uow, adapter)
    report = excinfo.value.report
    assert report.registered == 0
    assert report.rejected >= 1
    assert any(fragment in item.reason for item in report.rejections)
    # All-or-nothing: nothing was written, not even the valid records.
    assert await uow.entities.list_entities(role="service") == []
    assert await uow.entities.list_aliases(role="service") == []


@pytest.mark.parametrize(
    "mutate",
    [
        # Rejected by snapshot parsing, before registration runs.
        _unverified_state,
        _bad_representation,
    ],
)
async def test_record_the_parser_refuses_never_imports(tmp_path, mutate):
    """A record outside the approved vocabulary stops at parse time."""
    with pytest.raises(SnapshotError):
        _adapter(tmp_path, mutate)


async def test_wrong_snapshot_version_is_refused(tmp_path):
    adapter = _adapter(tmp_path, snapshot_version="canonical_v9")
    with pytest.raises(RegistrationError):
        await register_canonical_entities(
            MemoryUnitOfWork(), adapter,
            expected_snapshot_version="canonical_v1")


async def test_matching_expected_snapshot_version_is_accepted(tmp_path):
    adapter = _adapter(tmp_path)
    report, _ = await _register(
        adapter, expected_snapshot_version="canonical_v1")
    assert report.registered == 4


async def test_wrong_rules_version_is_refused(tmp_path):
    adapter = _adapter(tmp_path, rules_version="0.9.0")
    with pytest.raises(RegistrationError):
        await register_canonical_entities(
            MemoryUnitOfWork(), adapter,
            rules_version=VERIFICATION_RULES_VERSION)


async def test_artifact_rules_must_match_the_frozen_gate_version(tmp_path):
    adapter = _adapter(tmp_path)
    assert adapter.rules_version == VERIFICATION_RULES_VERSION
    with pytest.raises(RegistrationError):
        await register_canonical_entities(
            MemoryUnitOfWork(), adapter, rules_version="1.0.1")


async def test_empty_snapshot_imports_nothing(tmp_path):
    from app.services.verification.adapters.snapshot import SnapshotAdapter

    adapter = SnapshotAdapter(_write_snapshot(tmp_path, {
        "records": [],
        "snapshot_version": "canonical_v1",
        "verification_rule_version": VERIFICATION_RULES_VERSION,
    }))
    report, uow = await _register(adapter)
    assert report.considered == 0
    assert report.registered == 0


async def test_write_failure_leaves_no_partial_state(tmp_path):
    """A failing write rolls the whole import back."""

    class _ExplodingEntities:
        def __init__(self, inner):
            self._inner = inner
            self.calls = 0

        async def get_entity(self, entity_id, *, role="service"):
            return await self._inner.get_entity(entity_id, role=role)

        async def save_entity(self, row, *, role="service"):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("injected write failure")
            return await self._inner.save_entity(row, role=role)

        async def save_alias(self, row, *, role="service"):
            return await self._inner.save_alias(row, role=role)

    uow = MemoryUnitOfWork()
    original = uow.entities
    exploding = _ExplodingEntities(original)
    uow.entities = exploding
    with pytest.raises(RuntimeError):
        await register_canonical_entities(uow, _adapter(tmp_path))
    # Transaction rollback restored the pre-import state.
    assert await original.list_entities(role="service") == []
    assert await original.list_aliases(role="service") == []


# -- entity type preservation and no inference ------------------------


async def test_salt_is_not_stored_as_a_molecule(tmp_path):
    _, uow = await _register(_adapter(tmp_path))
    rows = await uow.entities.list_entities(role="service")
    benzoate = next(
        row for row in rows
        if row["preferred_name"] == "sodium benzoate")
    # The approved representation type is preserved verbatim; the
    # registry-facing class column stays unset rather than guessed.
    assert benzoate["representation_type"] == "salt"
    assert benzoate["chemical_class"] is None


def test_non_molecular_record_cannot_carry_molecular_fields(tmp_path):
    """A mixture is rejected if it claims a molecule formula."""
    from app.services.verification.adapters.snapshot import SnapshotError

    def add_formula(payload):
        payload["records"][0]["representation_type"] = "mixture"
        payload["records"][0]["fields"]["formula"] = {"value": "C6H8O7"}

    with pytest.raises(SnapshotError):
        _adapter(tmp_path, add_formula)


async def test_missing_fields_stay_null(tmp_path):
    def strip_fields(payload):
        payload["records"][0]["fields"] = {}
        payload["records"][0]["identifiers"] = [
            {"id_type": "e_number", "value": "E330"}
        ]

    _, uow = await _register(_adapter(tmp_path, strip_fields))
    row = next(
        r for r in await uow.entities.list_entities(role="service")
        if r["preferred_name"] == "citric acid")
    # Absent in the source -> absent in the database. No inference.
    for column in ("formula", "molecular_weight", "inchi", "inchikey",
                   "smiles", "pubchem_cid", "structure_status",
                   "chemical_class"):
        assert row[column] is None
    assert row["molecular_weight_unit"] is None


def test_row_projection_does_not_invent_values(tmp_path):
    from app.services.verification.adapters.snapshot import SnapshotAdapter

    adapter = SnapshotAdapter(str(SNAPSHOT_PATH))
    entity = adapter.canonical_entities()[0]
    row = entity_row_for(
        entity, snapshot_version="canonical_v1", rules_version="1.0.0")
    source_fields = {item.field for item in entity.fields}
    for field in ("formula", "inchi", "inchikey", "smiles"):
        if field not in source_fields:
            assert row[field] is None
    assert row["preferred_name"] == entity.preferred_name


# -- provenance --------------------------------------------------------


async def test_provenance_is_persisted(tmp_path):
    _, uow = await _register(_adapter(tmp_path))
    row = next(
        r for r in await uow.entities.list_entities(role="service")
        if r["preferred_name"] == "citric acid")
    meta = row["metadata"]
    assert meta["snapshot_version"] == "canonical_v1"
    assert meta["rules_version"] == VERIFICATION_RULES_VERSION
    assert meta["verification_status"] == "verified"
    assert meta["verified_at"]
    assert meta["imported_by"] == "canonical-registration-import"
    provenance = meta["provenance"]
    assert provenance["source_id"] == "PUBCHEM"
    assert provenance["record_locator"].startswith("https://pubchem")
    assert provenance["retrieved_at"]
    assert provenance["source_class"]
    assert provenance["license_note"]
    # Identifiers keep their own provenance notes.
    assert all("provenance_note" in item for item in meta["identifiers"])


async def test_aliases_are_registered_with_verified_flag(tmp_path):
    _, uow = await _register(_adapter(tmp_path))
    aliases = await uow.entities.list_aliases(role="service")
    assert aliases
    assert all(item["verified"] for item in aliases)
    assert all(item["alias_type"] == "name" for item in aliases)
    assert all(item["source_id"] is None for item in aliases)
    # No alias duplicates a preferred name.
    entities = {row["id"]: row for row in
                await uow.entities.list_entities(role="service")}
    for alias in aliases:
        parent = entities[alias["chemical_entity_id"]]
        assert alias["alias"].lower() != parent["preferred_name"].lower()


# -- registry integration ----------------------------------------------


async def test_registry_is_projected_from_registered_entities(tmp_path):
    _, uow = await _register(_adapter(tmp_path))
    registry = await load_registry_from_repository(
        uow.entities, version="1")
    assert registry.registry_id == "canonical_registry"
    hits = registry.lookup_exact_name("citric acid")
    assert len(hits) == 1
    assert hits[0].entity_class == "single_molecule"
    assert hits[0].source == "PUBCHEM"
    assert "330" in "".join(hits[0].identifiers)
    # Aliases are searchable.
    assert registry.lookup_exact_name("Citric Acid")
    assert registry.lookup_identifier("e330")
    # A registry ref is registry-local, never the entity UUID.
    assert not hits[0].ref.startswith(str(
        "2671a263"))


async def test_unregistered_name_resolves_nothing(tmp_path):
    _, uow = await _register(_adapter(tmp_path))
    registry = await load_registry_from_repository(uow.entities)
    assert registry.lookup_exact_name("unobtainium") == []
    assert registry.lookup_identifier("E999") == []


async def test_empty_registry_resolves_nothing():
    registry = empty_registry()
    assert registry.lookup_exact_name("citric acid") == []
    assert list(registry.iter_names()) == []


async def test_registry_reflects_live_registration_only(tmp_path):
    """Deleting a row from the projection removes it from lookup."""
    _, uow = await _register(_adapter(tmp_path))
    before = await load_registry_from_repository(uow.entities)
    assert before.lookup_exact_name("glycerol")
    uow._store.table("chemical_entities").pop(
        "763389d0-3732-47dd-ad27-2c62a50e95b8")
    after = await load_registry_from_repository(uow.entities)
    assert not after.lookup_exact_name("glycerol")
    assert after.lookup_exact_name("citric acid")


def test_build_registry_representation_type_drives_entity_class():
    registry = build_registry(
        [
            {"id": "11111111-1111-4111-8111-111111111111",
             "preferred_name": "blend", "representation_type": "mixture",
             "metadata": {"provenance": {"source_id": "SRC"},
                          "identifiers": []}},
            {"id": "22222222-2222-4222-8222-222222222222",
             "preferred_name": "resin", "representation_type": "material",
             "metadata": {}},
        ],
        [
            {"chemical_entity_id": "11111111-1111-4111-8111-111111111111",
             "alias": "Blend 100"},
        ],
        version="2",
    )
    assert registry.lookup_exact_name("blend")[0].entity_class == "mixture"
    assert registry.lookup_exact_name("resin")[0].entity_class == "material"
    assert registry.lookup_alias("blend 100")[0].preferred_name == "blend"
    assert registry.version == "2"


# -- nothing new is invented ------------------------------------------


async def test_import_does_not_touch_product_or_scan_tables(tmp_path):
    _, uow = await _register(_adapter(tmp_path))
    for table in ("products", "scans", "roles", "claims",
                  "verification_decisions", "reviews"):
        assert uow._store.table(table) == {}


def test_snapshot_artifact_is_never_rewritten(tmp_path):
    """Loading and reading records has no write side effect."""
    before = copy.deepcopy(_payload())
    adapter = _adapter(tmp_path)
    entities = adapter.canonical_entities()
    assert len(entities) == 4
    assert _payload() == before
    # The adapter exposes copies, not its internal list.
    entities.clear()
    assert len(adapter.canonical_entities()) == 4
