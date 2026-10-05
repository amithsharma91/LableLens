"""Mocked end-to-end evidence integration (no live network).

Proves the Stage-8 chain without bypassing Stage-7:

    Stage-5 candidate -> provider evidence (+ snapshot)
      -> evidence evaluation -> frozen V1-V7 -> decision
"""

import json
from pathlib import Path

from app.services.entity_resolver import (
    Candidate,
    InMemoryRegistry,
    RegistryEntry,
    Resolution,
    resolve_node,
)
from app.services.ingredient_normalizer import normalize_label_text
from app.services.verification.adapters.base import VerificationSource
from app.services.verification.adapters.chebi import ChebiAdapter
from app.services.verification.adapters.http import HttpClient, RateLimiter
from app.services.verification.adapters.pubchem import PubChemAdapter
from app.services.verification.adapters.snapshot import SnapshotAdapter
from app.services.verification.evidence import CombinedAdapter
from app.services.verification.models import (
    CanonicalEntity,
    FieldEvidence,
    SourceMetadata,
    SourceRecord,
)
from app.services.verification.orchestrator import verify_candidate

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "snapshots" / "canonical_v1.json"
)


class FakeTransport:
    def __init__(self):
        self.routes = []
        self.calls = []

    def add(self, needle, status, content_type, body):
        self.routes.append((needle, status, content_type, body))

    def __call__(self, url, timeout):
        self.calls.append(url)
        for needle, status, content_type, body in self.routes:
            if needle in url:
                if isinstance(body, BaseException):
                    raise body
                return status, content_type, (
                    body if isinstance(body, bytes) else json.dumps(body).encode()
                )
        return 404, "application/json", b'{"Fault": {}}'


def _stage5_registry():
    return InMemoryRegistry(
        [
            RegistryEntry(
                ref="T8-001",
                preferred_name="citric acid",
                display_name="Citric Acid (integration fixture)",
                identifiers=["E330"],
                entity_class="single_molecule",
                source="synthetic_test_fixture",
            ),
        ],
        registry_id="stage8_test_registry",
        version="t8",
    )


def _resolve(text):
    norm = normalize_label_text(text)
    assert len(norm.nodes) == 1, text
    return resolve_node(norm.nodes[0], _stage5_registry())


def _pubchem_props(**overrides):
    payload = {
        "CID": 311,
        "MolecularFormula": "C6H8O7",
        "MolecularWeight": "192.12",
        "SMILES": "C(C(=O)O)C(CC(=O)O)(C(=O)O)O",
        "InChI": "InChI=1S/C6H8O7/c7-3(8)1-6(13,5(11)12)2-4(9)10/h13H",
        "InChIKey": "KRKNYBCHXYNGOX-UHFFFAOYSA-N",
        "IUPACName": "2-hydroxypropane-1,2,3-tricarboxylic acid",
        "Title": "Citric Acid",
    }
    payload.update(overrides)
    return {"PropertyTable": {"Properties": [payload]}}


def _pubchem_client(transport):
    return HttpClient(
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        transport=transport,
        limiter=RateLimiter(min_interval=0),
        sleeper=lambda s: None,
    )


def _pubchem_adapter(transport, **kwargs):
    kwargs.setdefault("date_provider", lambda: "2026-10-05")
    return PubChemAdapter(_pubchem_client(transport), **kwargs)


def _routes_citric(transport):
    transport.add("compound/name/citric", 200, "application/json",
                  json.dumps(_pubchem_props()).encode())
    transport.add("compound/cid/311/synonyms", 200, "application/json",
                  json.dumps({"InformationList": {"Information": [
                      {"Synonym": ["Citric Acid", "E330", "INS-330"]}]}}).encode())


class _StaticProvider(VerificationSource):
    def __init__(self, records):
        super().__init__()
        self._records = list(records)

    def lookup_identity(self, resolution):
        return list(self._records)


def _static_record(eid, name, rep="single_molecule", fields=()):
    meta = SourceMetadata(
        source_id="SYNTH", record_locator="synth:" + eid,
        source_version="s", retrieved_at="2026-10-05",
        license_note="synthetic", source_class="A",
    )
    return SourceRecord(
        entity=CanonicalEntity(
            entity_id=eid, preferred_name=name, entity_type="chemical_entity",
            representation_type=rep, identifiers=(), names=(), fields=tuple(fields),
            contexts=(), verification_status="verified", snapshot_version="s",
            verified_at="2026-10-05", last_checked="2026-10-05", source=meta,
        ),
        source=meta,
    )


def test_snapshot_plus_pubchem_agreement_verifies():
    transport = FakeTransport()
    _routes_citric(transport)
    combined = CombinedAdapter(
        [SnapshotAdapter(SNAPSHOT_PATH), _pubchem_adapter(transport)]
    )
    decision = verify_candidate(_resolve("Citric Acid (E330)"), combined)
    assert decision.status == "verified"
    assert decision.identity_confidence == "HIGH"
    providers = {s.source_id for s in decision.source_refs}
    assert {"PUBCHEM"} <= providers


def test_two_source_name_agreement_still_needs_identifier():
    """Honesty check: Bare names stay provisional even with two
    agreeing providers -- corroboration requires the identifier."""
    transport = FakeTransport()
    _routes_citric(transport)
    combined = CombinedAdapter(
        [SnapshotAdapter(SNAPSHOT_PATH), _pubchem_adapter(transport)]
    )
    decision = verify_candidate(_resolve("citric acid"), combined)
    assert decision.status == "provisional"
    assert decision.entity_id is None


def test_formula_disagreement_is_conflicted():
    transport = FakeTransport()
    transport.add("compound/name/citric", 200, "application/json",
                  json.dumps(_pubchem_props(
                      MolecularFormula="C7H6O2",
                      InChIKey="DIFFERENTKEYAAAAAAAAA-B")).encode())
    transport.add("compound/cid/311/synonyms", 200, "application/json",
                  json.dumps({"InformationList": {"Information": [
                      {"Synonym": ["Citric Acid", "E330"]}]}}).encode())
    combined = CombinedAdapter(
        [SnapshotAdapter(SNAPSHOT_PATH), _pubchem_adapter(transport)]
    )
    decision = verify_candidate(_resolve("Citric Acid (E330)"), combined)
    assert decision.status == "conflicted"
    assert decision.identity_confidence == "CONFLICTED"


def _chebi_client(transport):
    return HttpClient(
        "https://www.ebi.ac.uk",
        transport=transport,
        limiter=RateLimiter(min_interval=0),
        sleeper=lambda s: None,
    )


def _chebi_es_hit(**overrides):
    source = {
        "chebi_accession": "CHEBI:30769",
        "name": "citric acid",
        "ascii_name": "citric acid",
        "smiles": "O=C(O)CC(O)(CC(=O)O)C(=O)O",
        "formula": "C6H8O7",
        "inchikey": "KRKNYBCHXYNGOX-UHFFFAOYSA-N",
        "inchi": "InChI=1S/C6H8O7/c7-3(8)1-6(13,5(11)12)2-4(9)10/h13H",
        "mass": 192.123,
    }
    source.update(overrides)
    return {"_id": "30769", "_score": 75.0, "_source": source}


def _chebi_detail():
    return {
        "id": 30769,
        "chebi_accession": "CHEBI:30769",
        "name": "citric acid",
        "names": {"SYNONYM": [
            {"name": "E330", "ascii_name": "E330"},
            {"name": "INS-330", "ascii_name": "INS-330"},
        ]},
    }


def test_triple_provider_agreement_verifies():
    transport = FakeTransport()
    _routes_citric(transport)
    transport.add("es_search", 200, "application/json",
                  json.dumps([_chebi_es_hit()]).encode())
    transport.add("/compound/30769/", 200, "application/json",
                  json.dumps(_chebi_detail()).encode())
    combined = CombinedAdapter(
        [
            SnapshotAdapter(SNAPSHOT_PATH),
            _pubchem_adapter(transport),
            ChebiAdapter(_chebi_client(transport),
                         date_provider=lambda: "2026-10-05"),
        ]
    )
    decision = verify_candidate(_resolve("Citric Acid (E330)"), combined)
    assert decision.status == "verified"
    providers = {s.source_id for s in decision.source_refs}
    assert {"PUBCHEM", "CHEBI"} <= providers


def test_salt_vs_free_acid_does_not_verify():
    provider = _StaticProvider([
        _static_record("SYN-ACID", "benzoic acid", fields=(
            FieldEvidence(field="formula", value="C7H6O2", unit=None,
                          source=_static_record("x", "y").source),
        ))
    ])
    res = Resolution(
        raw_text="sodium benzoate",
        normalized_text="sodium benzoate",
        status="exact_match",
        candidates=[
            Candidate(
                candidate_ref="T8-S", display_name="sodium benzoate",
                candidate_type="salt", source="synthetic_test_fixture",
                match_method="exact_normalized_name", match_score=0.95,
                reason="synthetic",
            )
        ],
    )
    decision = verify_candidate(res, provider)
    assert decision.status == "unverified"
    assert decision.entity_id is None


def test_mixture_candidate_not_forced_into_molecule():
    provider = _StaticProvider([
        _static_record("SYN-M", "test blend", rep="single_molecule",
                       fields=(
                           FieldEvidence(field="formula", value="C1",
                                         unit=None,
                                         source=_static_record(
                                             "x", "y").source),
                       ))
    ])
    res = Resolution(
        raw_text="test blend",
        normalized_text="test blend",
        status="exact_match",
        candidates=[
            Candidate(
                candidate_ref="T8-M", display_name="test blend",
                candidate_type="mixture", source="synthetic_test_fixture",
                match_method="exact_normalized_name", match_score=0.95,
                reason="synthetic",
            )
        ],
    )
    decision = verify_candidate(res, provider)
    assert decision.status == "unverified"
    assert all(c.field == "identity" for c in decision.claims)


def test_bogus_verified_flag_in_payload_ignored():
    transport = FakeTransport()
    payload = _pubchem_props()
    payload["PropertyTable"]["Properties"][0]["verified"] = True
    payload["PropertyTable"]["Properties"][0]["confidence"] = 99.9
    transport.add("compound/name/citric", 200, "application/json",
                  json.dumps(payload).encode())
    transport.add("compound/cid/311/synonyms", 200, "application/json",
                  json.dumps({"InformationList": {"Information": [
                      {"Synonym": ["Citric Acid", "E330"]}]}}).encode())
    combined = CombinedAdapter(
        [SnapshotAdapter(SNAPSHOT_PATH), _pubchem_adapter(transport)]
    )
    decision = verify_candidate(_resolve("Citric Acid (E330)"), combined)
    assert decision.status == "verified"  # via the gate, not the flag
    assert all(g.rule_id.startswith("V") for g in decision.gate_results)
    assert "99.9" not in json.dumps(decision.to_dict())


def test_provider_outage_surfaces_notice_and_unknown():
    from app.services.verification.adapters.http import ProviderTimeout

    transport = FakeTransport()
    transport.add("compound/name/", 0, "", ProviderTimeout("down"))
    adapter = _pubchem_adapter(transport)
    decision = verify_candidate(_resolve("citric acid"), adapter)
    assert decision.status == "unknown"
    assert any("failed" in w for w in decision.warnings)


def test_adapter_notices_reach_decision():
    transport = FakeTransport()
    transport.add("compound/name/", 200, "application/json", b"{oops")
    adapter = _pubchem_adapter(transport)
    decision = verify_candidate(_resolve("citric acid"), adapter)
    assert decision.status == "unknown"
    assert decision.warnings != ()
