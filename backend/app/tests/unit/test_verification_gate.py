"""Unit tests for the frozen gate V1-V7 (pure functions only).

All registry content here is synthetic (``SYNTHETIC_FIXTURE_SOURCE``)
and exercises gate *logic*, never real chemistry.
"""

from app.services.verification.gate import (
    VERIFICATION_RULES_VERSION,
    derive_name_key,
    evaluate_gate,
    filter_admissible,
    v1_admissible_candidate,
    v2_sources_available,
    v3_identity_agreement,
    v4_identifiers,
    v5_entity_type,
    v6_source_appropriateness,
    v7_context,
    validate_cas_format,
    validate_inchikey_format,
    validate_inchi_format,
    validate_pubchem_cid_format,
)
from app.services.verification.models import (
    FAIL,
    PASS,
    UNKNOWN,
    CanonicalEntity,
    Identifier,
    SourceMetadata,
    SourceRecord,
)

SYNTH = "SYNTHETIC_FIXTURE_SOURCE"


def _record(
    eid="ENT-1",
    name="test substance",
    rep="single_molecule",
    ids=(),
    names=(),
    contexts=(),
    cls="A",
):
    meta = SourceMetadata(
        source_id=SYNTH,
        record_locator="synth:" + eid,
        source_version="synth-1",
        retrieved_at="2026-10-05",
        license_note="synthetic fixture, not evidence",
        source_class=cls,
    )
    return SourceRecord(
        entity=CanonicalEntity(
            entity_id=eid,
            preferred_name=name,
            entity_type="chemical_entity",
            representation_type=rep,
            identifiers=tuple(
                Identifier(
                    id_type=t, value=v, provenance_note="synthetic"
                )
                for t, v in ids
            ),
            names=tuple(names),
            fields=(),
            contexts=tuple(contexts),
            verification_status="verified",
            snapshot_version="synth",
            verified_at="2026-10-05",
            last_checked="2026-10-05",
            source=meta,
        ),
        source=meta,
    )


def test_rules_version_pinned():
    assert VERIFICATION_RULES_VERSION == "1.0.0"


# --- V1 -----------------------------------------------------------------

def test_v1_exact_match_pass():
    assert v1_admissible_candidate("exact_match").result == PASS


def test_v1_unresolved_and_candidate_fail():
    assert v1_admissible_candidate("unresolved").result == FAIL
    assert v1_admissible_candidate("candidate").result == FAIL


def test_v1_ambiguous_needs_human():
    assert v1_admissible_candidate("ambiguous").result == FAIL
    ok = v1_admissible_candidate("ambiguous", human_disambiguation=True)
    assert ok.result == PASS


# --- V2 -----------------------------------------------------------------

def test_v2_present_and_absent():
    assert v2_sources_available([_record()]).result == PASS
    assert v2_sources_available([]).result == FAIL


# --- V3 -----------------------------------------------------------------

def test_v3_no_agreement_fail():
    from app.services.verification.gate import name_agreeing

    rec = _record(name="other substance")
    assert name_agreeing("test substance", [rec]) == []
    res = evaluate_gate(
        resolution_status="exact_match",
        normalized_text="test substance",
        candidate_identifier=None,
        candidate_type="single_molecule",
        records=[rec],
    )
    assert [g.result for g in res][2] == FAIL


def test_v3_single_source_unknown_not_pass():
    rec = _record(name="test substance")
    out = v3_identity_agreement([rec], dual_agreement=False)
    assert out.result == UNKNOWN


def test_v3_dual_agreement_pass():
    rec = _record(name="test substance")
    out = v3_identity_agreement([rec], dual_agreement=True)
    assert out.result == PASS


def test_v3_two_sources_pass():
    recs = [
        _record(eid="ENT-1", name="test substance"),
        _record(eid="ENT-2", name="test substance"),
    ]
    assert v3_identity_agreement(recs, dual_agreement=False).result == PASS


# --- V4 -----------------------------------------------------------------

def test_cas_checksum_valid_and_invalid():
    assert validate_cas_format("77-92-9") is True
    assert validate_cas_format("64-17-5") is True
    assert validate_cas_format("77-92-8") is False
    assert validate_cas_format("not-a-cas") is False
    assert validate_cas_format("") is False


def test_cas_valid_does_not_prove_identity():
    """Checksum PASS plus zero agreeing records still FAILs V4."""
    rec = _record(name="other substance")
    out = v4_identifiers("77-92-9", [rec], name_hit_ids=frozenset())
    assert out.result == FAIL


def test_v4_malformed_cas_fail():
    rec = _record(name="test substance")
    out = v4_identifiers("77-92-8", [rec], name_hit_ids=frozenset())
    assert out.result == FAIL


def test_v4_dual_agreement_pass():
    rec = _record(
        eid="ENT-9", name="test substance", ids=[("e_number", "E330")]
    )
    out = v4_identifiers("E 330", [rec], name_hit_ids=frozenset({"ENT-9"}))
    assert out.result == PASS


def test_v4_claimed_elsewhere_fail():
    rec = _record(
        eid="ENT-9", name="other substance", ids=[("e_number", "E330")]
    )
    out = v4_identifiers("E 330", [rec], name_hit_ids=frozenset({"ENT-1"}))
    assert out.result == FAIL


def test_v4_absent_molecular_unknown():
    rec = _record(name="test substance")
    out = v4_identifiers(None, [rec], name_hit_ids=frozenset())
    assert out.result == UNKNOWN


def test_v4_absent_non_molecular_vacuous_pass():
    rec = _record(name="test blend", rep="mixture")
    out = v4_identifiers(None, [rec], name_hit_ids=frozenset())
    assert out.result == PASS


def test_identifier_format_validators():
    assert validate_inchikey_format("KRKNYBCHXYNGOX-UHFFFAOYSA-N") is True
    assert validate_inchikey_format("TOOSHORT") is False
    assert validate_inchi_format("InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3")
    assert not validate_inchi_format("C2H6O")
    assert validate_pubchem_cid_format("311") is True
    assert validate_pubchem_cid_format("0") is False
    assert validate_pubchem_cid_format("31A") is False


# --- V5 -----------------------------------------------------------------

def test_v5_agree_mismatch_unknown():
    rec = _record(rep="single_molecule")
    assert v5_entity_type("single_molecule", [rec]).result == PASS
    assert v5_entity_type("mixture", [rec]).result == FAIL
    assert v5_entity_type("unknown", [rec]).result == UNKNOWN
    assert v5_entity_type(None, [rec]).result == UNKNOWN


def test_v5_molecule_vs_mixture_fails():
    rec = _record(rep="mixture")
    assert v5_entity_type("single_molecule", [rec]).result == FAIL


# --- V6 -----------------------------------------------------------------

def test_v6_appropriateness_and_filter():
    good = _record(eid="ENT-1", cls="A")
    weak = _record(eid="ENT-2", cls="E")
    assert v6_source_appropriateness([good, weak]).result == PASS
    assert filter_admissible([good, weak]) == [good]
    assert v6_source_appropriateness([weak]).result == FAIL
    assert v6_source_appropriateness([]).result == FAIL


# --- V7 -----------------------------------------------------------------

def test_v7_context_rules():
    rec = _record()
    assert v7_context([rec]).result == PASS
    scoped = _record(contexts=["food"])
    assert v7_context([scoped]).result == UNKNOWN
    assert v7_context([scoped], context="food").result == PASS
    assert v7_context([scoped], context="cosmetics").result == FAIL


# --- Parity + full gate --------------------------------------------------

def test_derive_name_key_parity_contract():
    assert derive_name_key("stabilizer INS 471", "INS 471") == "stabilizer"
    assert derive_name_key("INS 471", "INS 471") == ""
    assert derive_name_key("citric acid", None) == "citric acid"
    assert derive_name_key("citric acid E 330", "E 330") == "citric acid"


def test_evaluate_gate_all_pass_synthetic():
    rec = _record(
        eid="ENT-9",
        name="test substance",
        ids=[("e_number", "E330")],
    )
    results = evaluate_gate(
        resolution_status="exact_match",
        normalized_text="test substance E 330",
        candidate_identifier="E 330",
        candidate_type="single_molecule",
        records=[rec],
    )
    assert [g.result for g in results] == [PASS] * 7


def test_unknown_never_counts_as_pass():
    rec = _record(name="test substance")
    results = evaluate_gate(
        resolution_status="exact_match",
        normalized_text="test substance",
        candidate_identifier=None,
        candidate_type="single_molecule",
        records=[rec],
    )
    verdicts = [g.result for g in results]
    assert UNKNOWN in verdicts  # V3 and V4 stay UNKNOWN
    assert not all(v == PASS for v in verdicts)
