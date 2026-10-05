"""Unit tests for Stage-5 candidate entity resolution.

All registry content is explicitly synthetic (``TEST-###`` refs,
``source="synthetic_test_fixture"``). Fixtures exercise resolver
*behavior* only and are never treated as verified chemical facts --
the safety tests assert exactly that.
"""

import json

from app.services.entity_resolver import (
    Candidate,
    EntityRegistry,
    InMemoryRegistry,
    RegistryEntry,
    Resolution,
    resolve_entities,
    resolve_node,
)
from app.services.ingredient_normalizer import (
    NormalizedIngredient,
    normalize_label_text,
)

SOURCE = "synthetic_test_fixture"


def _base_entries():
    return [
        RegistryEntry(
            ref="TEST-001",
            preferred_name="sodium benzoate",
            display_name="Sodium Benzoate (synthetic fixture)",
            identifiers=["E211"],
            entity_class="salt",
            source=SOURCE,
        ),
        RegistryEntry(
            ref="TEST-002",
            preferred_name="citric acid",
            display_name="Citric Acid (synthetic fixture)",
            aliases=["2-hydroxypropane-132-tricarboxylic acid"],
            identifiers=["E330"],
            entity_class="single_molecule",
            source=SOURCE,
        ),
        RegistryEntry(
            ref="TEST-003",
            preferred_name="test emulsifier blend",
            display_name="Test Emulsifier Blend (synthetic)",
            identifiers=["INS471"],
            entity_class="mixture",
            source=SOURCE,
        ),
        RegistryEntry(
            ref="TEST-004",
            preferred_name="cocoa butter",
            display_name="Cocoa Butter (synthetic fixture)",
            entity_class="mixture",
            source=SOURCE,
        ),
        RegistryEntry(
            ref="TEST-005",
            preferred_name="fragrance",
            display_name="Fragrance (synthetic fixture)",
            entity_class="mixture",
            source=SOURCE,
        ),
    ]


def _registry(extra=None):
    return InMemoryRegistry(
        _base_entries() + list(extra or []),
        registry_id="test_fixture_registry",
        version="test-1",
    )


def _resolve_one(text, registry):
    norm = normalize_label_text(text)
    assert len(norm.nodes) == 1, text
    return resolve_node(norm.nodes[0], registry)


# --- Exact matching -------------------------------------------------

def test_exact_normalized_preferred_name():
    res = _resolve_one("Citric Acid", _registry())
    assert res.status == "exact_match"
    assert res.selected_candidate.candidate_ref == "TEST-002"
    assert res.identity_confidence == "HIGH"
    assert res.methods == ["exact_normalized_name"]


def test_exact_case_and_whitespace_differences():
    res = _resolve_one("  SODIUM   BENZOATE ", _registry())
    assert res.status == "exact_match"
    assert res.selected_candidate.candidate_ref == "TEST-001"


def test_trusted_alias_match():
    res = _resolve_one(
        "2-hydroxypropane-132-tricarboxylic acid", _registry()
    )
    assert res.status == "exact_match"
    assert res.selected_candidate.candidate_ref == "TEST-002"
    assert res.methods == ["exact_alias"]
    # Alias-level exactness is weaker than a name/identifier hit.
    assert res.identity_confidence == "MEDIUM"


def test_unregistered_alias_does_not_match():
    res = _resolve_one("vitamin C", _registry())
    assert res.status == "unresolved"
    assert res.selected_candidate is None
    assert res.alternatives == []


# --- Identifiers ----------------------------------------------------

def test_e_number_exact_mapping():
    res = _resolve_one("E330", _registry())
    assert res.status == "exact_match"
    assert res.selected_candidate.candidate_ref == "TEST-002"
    assert "exact_identifier" in res.methods
    assert res.identity_confidence == "HIGH"


def test_ins_exact_mapping():
    res = _resolve_one("INS471", _registry())
    assert res.status == "exact_match"
    assert res.selected_candidate.candidate_ref == "TEST-003"
    # Mixture-class candidate keeps its class, not a molecule.
    assert res.selected_candidate.candidate_type == "mixture"


def test_identifier_with_name_combined():
    res = _resolve_one("Citric Acid (E330)", _registry())
    assert res.status == "exact_match"
    assert res.selected_candidate.candidate_ref == "TEST-002"


def test_malformed_identifier_unresolved():
    res = _resolve_one("INS XYZ", _registry())
    assert res.status == "unresolved"
    assert res.selected_candidate is None


# --- OCR-near --------------------------------------------------------

def test_controlled_ocr_near_candidate():
    res = _resolve_one("Sodlum Benzoate", _registry())
    assert res.status == "candidate"
    assert res.selected_candidate is None  # never auto-selected
    assert len(res.alternatives) == 1
    cand = res.alternatives[0]
    assert cand.candidate_ref == "TEST-001"
    assert cand.match_method == "controlled_ocr_similarity"
    assert res.identity_confidence == "LOW"
    assert "ocr_near_candidate_only" in res.warnings
    # Original observation preserved, not rewritten.
    assert res.raw_text == "Sodlum Benzoate"
    assert res.normalized_text == "sodlum benzoate"


def test_ocr_multiple_plausible_stays_ambiguous():
    extra = [
        RegistryEntry(
            ref="TEST-006",
            preferred_name="alpha test mix",
            display_name="Alpha Test Mix (synthetic)",
            entity_class="mixture",
            source=SOURCE,
        ),
        RegistryEntry(
            ref="TEST-007",
            preferred_name="alpha test max",
            display_name="Alpha Test Max (synthetic)",
            entity_class="mixture",
            source=SOURCE,
        ),
    ]
    res = _resolve_one("alpha test mex", _registry(extra))
    assert res.status == "ambiguous"
    assert res.selected_candidate is None
    refs = {c.candidate_ref for c in res.alternatives}
    assert refs == {"TEST-006", "TEST-007"}
    assert res.identity_confidence == "LOW"


# --- Ambiguity -------------------------------------------------------

def test_two_exact_candidates_ambiguous_no_first_pick():
    extra = [
        RegistryEntry(
            ref="TEST-008",
            preferred_name="test entry one",
            display_name="Test Entry One (synthetic)",
            aliases=["test shared alias"],
            entity_class="material",
            source=SOURCE,
        ),
        RegistryEntry(
            ref="TEST-009",
            preferred_name="test entry two",
            display_name="Test Entry Two (synthetic)",
            aliases=["test shared alias"],
            entity_class="material",
            source=SOURCE,
        ),
    ]
    res = _resolve_one("test shared alias", _registry(extra))
    assert res.status == "ambiguous"
    assert res.selected_candidate is None
    assert len(res.alternatives) == 2
    # Deterministic ordering: score, then name, then ref.
    names = [c.display_name for c in res.alternatives]
    assert names == sorted(names)
    assert res.identity_confidence == "MEDIUM"
    assert "ambiguous_requires_clarification" in res.warnings


def test_alternatives_truncation_recorded():
    extra = [
        RegistryEntry(
            ref="TEST-%03d" % i,
            preferred_name="test bulk entry %d" % i,
            display_name="Test Bulk Entry %d (synthetic)" % i,
            aliases=["test common alias"],
            entity_class="material",
            source=SOURCE,
        )
        for i in range(10)
    ]
    res = _resolve_one("test common alias", _registry(extra))
    assert res.status == "ambiguous"
    assert len(res.alternatives) == 8
    assert any("alternatives_truncated" in w for w in res.warnings)


# --- Unknown ----------------------------------------------------------

def test_unknown_stays_unresolved():
    res = _resolve_one("XYZ proprietary blend", _registry())
    assert res.status == "unresolved"
    assert res.selected_candidate is None
    assert res.alternatives == []
    assert res.identity_confidence == "UNKNOWN"


def test_empty_registry_resolves_nothing():
    empty = InMemoryRegistry([], registry_id="empty", version="t")
    assert isinstance(empty, EntityRegistry)
    res = _resolve_one("Citric Acid", empty)
    assert res.status == "unresolved"


# --- Non-molecular / complex terms ------------------------------------

def test_mixture_candidate_keeps_class():
    res = _resolve_one("cocoa butter", _registry())
    assert res.status == "exact_match"
    assert res.selected_candidate.candidate_type == "mixture"


def test_fragrance_not_a_molecule():
    res = _resolve_one("Fragrance", _registry())
    assert res.status == "exact_match"
    assert res.selected_candidate.candidate_type == "mixture"


def test_trade_name_unresolved():
    res = _resolve_one("Tego Betain F 50", _registry())
    assert res.status == "unresolved"
    assert res.selected_candidate is None


def test_botanical_and_umbrella_unresolved():
    for text in ("Aloe Vera Extract", "natural flavour", "plant extract"):
        res = _resolve_one(text, _registry())
        assert res.status == "unresolved", text
        assert res.selected_candidate is None, text


# --- Provenance / tree -------------------------------------------------

def test_provenance_and_tree_links():
    norm = normalize_label_text("Peanut Butter (Peanut, Salt)")
    out = resolve_entities(norm, _registry())
    assert len(out.nodes) == 1
    top = out.nodes[0]
    assert top.parser_node_id == norm.nodes[0].parser_node_id
    assert top.normalization_id == norm.nodes[0].id
    assert top.parent_id is None
    assert len(top.children) == 2
    for res_child, norm_child in zip(top.children, norm.nodes[0].children):
        assert res_child.parser_node_id == norm_child.parser_node_id
        assert res_child.parent_id == top.normalization_id
        assert res_child.depth == norm_child.depth == 1
    prov = top.provenance
    assert prov["registry_id"] == "test_fixture_registry"
    assert prov["resolver_version"]
    assert isinstance(top, Resolution)
    assert out.raw_text == norm.raw_text


def test_parent_context_supporting_signal():
    extra = [
        RegistryEntry(
            ref="TEST-010",
            preferred_name="test child ingredient",
            display_name="Test Child Ingredient (synthetic)",
            entity_class="material",
            contexts=["test parent blend"],
            source=SOURCE,
        ),
    ]
    norm = normalize_label_text(
        "Test Parent Blend (Test Child Ingredient)"
    )
    out = resolve_entities(norm, _registry(extra))
    child = out.nodes[0].children[0]
    assert child.status == "exact_match"
    assert "contextual_candidate" in child.methods
    assert "parent_context_agreement" in (
        child.selected_candidate.reason
    )


def test_identity_confidence_independent_of_normalization():
    node = NormalizedIngredient(
        raw_text="Citric Acid",
        normalized_text="citric acid",
        status="partial",
        warnings=["possible_ocr_variation"],
    )
    res = resolve_node(node, _registry())
    assert res.status == "exact_match"
    assert res.identity_confidence == "HIGH"


def test_empty_normalized_input_unresolved():
    res = resolve_node(NormalizedIngredient(), _registry())
    assert res.status == "unresolved"
    assert "empty_normalized_text" in res.warnings


# --- Safety -------------------------------------------------------------

def test_safety_no_chemistry_no_verification():
    norm = normalize_label_text(
        "SODIUM BENZOATE, Citric Acid (E330), cocoa butter, "
        "Fragrance, XYZ proprietary blend"
    )
    out = resolve_entities(norm, _registry())
    forbidden = {
        "smiles",
        "inchi",
        "inchikey",
        "cas",
        "cas_number",
        "formula",
        "molecular_formula",
        "molecular_weight",
        "descriptor",
        "rdkit",
        "verified",
        "verification",
        "evidence",
        "role",
        "regulatory",
        "chemical_entity_id",
        "chemicalentity",
    }
    payload = json.dumps(out.to_dict()).lower()
    assert "verified" not in payload
    for node in out.all_nodes():
        assert node.status in (
            "exact_match",
            "candidate",
            "ambiguous",
            "unresolved",
        )
        assert node.selected_candidate is None or (
            node.status == "exact_match"
        )
        for cand in node.candidates:
            assert cand.candidate_ref.startswith("TEST-")
            assert "chemical" not in cand.candidate_ref.lower()
            keys = {k.lower() for k in cand.to_dict()}
            assert not (keys & forbidden), keys & forbidden


def test_candidate_is_not_verified_entity():
    res = _resolve_one("Citric Acid", _registry())
    assert isinstance(res.selected_candidate, Candidate)
    assert not hasattr(res.selected_candidate, "smiles")
    assert not hasattr(res.selected_candidate, "verification_status")


# --- Determinism / serialization -----------------------------------------

def test_determinism_identical_output():
    norm = normalize_label_text(
        "Sodlum Benzoate, test shared alias, Water"
    )
    extra = [
        RegistryEntry(
            ref="TEST-008",
            preferred_name="test entry one",
            display_name="Test Entry One (synthetic)",
            aliases=["test shared alias"],
            entity_class="material",
            source=SOURCE,
        ),
        RegistryEntry(
            ref="TEST-009",
            preferred_name="test entry two",
            display_name="Test Entry Two (synthetic)",
            aliases=["test shared alias"],
            entity_class="material",
            source=SOURCE,
        ),
    ]
    reg = _registry(extra)
    first = resolve_entities(norm, reg).to_dict()
    second = resolve_entities(norm, reg).to_dict()
    assert first == second


def test_json_serializable():
    norm = normalize_label_text("A (B, C), INS471, Sodlum Benzoate")
    out = resolve_entities(norm, _registry())
    json.dumps(out.to_dict())
    assert isinstance(out, type(out))


# --- §18 upstream regression ----------------------------------------------

def test_regression_gate_inputs():
    reg = _registry()
    expectations = {
        "SODIUM BENZOATE": ("exact_match", "TEST-001"),
        "Citric Acid": ("exact_match", "TEST-002"),
        "INS471": ("exact_match", "TEST-003"),
        "E330": ("exact_match", "TEST-002"),
        "Sodlum Benzoate": ("candidate", "TEST-001"),
        "natural flavour": ("unresolved", None),
        "plant extract": ("unresolved", None),
        "cocoa butter": ("exact_match", "TEST-004"),
        "fragrance": ("exact_match", "TEST-005"),
        "proprietary blend": ("unresolved", None),
    }
    for text, (status, ref) in expectations.items():
        res = _resolve_one(text, reg)
        assert res.status == status, text
        if status == "exact_match":
            assert res.selected_candidate is not None, text
            assert res.selected_candidate.candidate_ref == ref, text
        elif status == "candidate":
            assert res.selected_candidate is None, text
            assert res.alternatives[0].candidate_ref == ref, text
        else:
            assert res.selected_candidate is None, text
            assert res.alternatives == [], text


def test_existing_stages_still_green():
    # Upstream contract spot-check: parser + normalizer outputs feed
    # the resolver without modification of their modules.
    norm = normalize_label_text("A (B (10%), C (INS 471)), D")
    out = resolve_entities(norm, _registry())
    assert len(out.nodes) == 2
    assert out.nodes[0].children[1].identifier == "INS 471"
