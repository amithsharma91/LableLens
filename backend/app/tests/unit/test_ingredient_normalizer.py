"""Deterministic tests for Stage-4 syntactic normalization.

Covers the review-gate list: whitespace, case, unicode, E/INS
codes, percentages, raw preservation, nesting, OCR-typo handling,
umbrella terms, mixtures, botanicals, fragrance/flavour, empty and
malformed input, idempotency -- plus the scientific-safety guard
proving Stage 4 invents no chemistry, identity, or evidence.
"""

import json

from app.services.ingredient_normalizer import (
    normalize_label_text,
    normalize_node,
    normalize_result,
)
from app.services.ingredient_parser import parse_label_ingredients


def test_01_whitespace_normalization():
    r = normalize_label_text("  Citric    Acid  ,   Water ")
    assert [n.normalized_text for n in r.nodes] == [
        "citric acid",
        "water",
    ]


def test_02_case_normalization():
    r = normalize_label_text("SODIUM BENZOATE, Citric Acid")
    assert [n.normalized_text for n in r.nodes] == [
        "sodium benzoate",
        "citric acid",
    ]


def test_03_unicode_whitespace():
    r = normalize_label_text("Citric Acid,\u2003Water")
    assert [n.normalized_text for n in r.nodes] == [
        "citric acid",
        "water",
    ]


def test_04_e_number_normalization():
    r = normalize_label_text("Citric Acid (E330), Water")
    assert r.nodes[0].identifier == "E 330"
    assert r.nodes[0].normalized_text == "citric acid E 330"


def test_05_ins_normalization():
    r = normalize_label_text("Stabilizer (INS471), Salt")
    assert r.nodes[0].identifier == "INS 471"
    assert r.nodes[0].normalized_text == "stabilizer INS 471"
    # Bare code without parens reaches the same canonical form.
    r2 = normalize_label_text("INS471")
    assert r2.nodes[0].identifier == "INS 471"
    assert r2.nodes[0].normalized_text == "INS 471"


def test_06_percentage_preservation():
    r = normalize_label_text("Citric Acid ( 10 % ), Water")
    assert r.nodes[0].percentage == 10.0
    assert r.nodes[0].normalized_text == "citric acid"
    assert r.nodes[1].percentage is None


def test_07_raw_text_preservation():
    raw = "  SODIUM   BENZOATE (E211) "
    r = normalize_label_text(raw)
    assert r.raw_text == raw
    assert r.nodes[0].raw_text == "SODIUM   BENZOATE (E211)"
    assert r.nodes[0].normalized_text == "sodium benzoate E 211"
    assert r.nodes[0].parser_node_id


def test_08_nested_parent_preservation():
    r = normalize_label_text("Peanut Butter (Peanut, Salt)")
    assert len(r.nodes) == 1
    pb = r.nodes[0]
    assert pb.normalized_text == "peanut butter"
    assert [c.normalized_text for c in pb.children] == [
        "peanut",
        "salt",
    ]
    assert all(c.parent_id == pb.id for c in pb.children)
    assert [c.depth for c in pb.children] == [1, 1]
    assert [c.position for c in pb.children] == [0, 1]


def test_09_ocr_typo_preservation():
    # "Sodlum" must NOT silently become "sodium": no lexicon at
    # this layer, so the typo is preserved as-is.
    r = normalize_label_text("Sodlum Benzoate, Water")
    assert r.nodes[0].normalized_text == "sodlum benzoate"
    assert r.nodes[0].raw_text == "Sodlum Benzoate"
    # A buried-digit artefact is flagged but still preserved.
    r2 = normalize_label_text("glycer1n, water")
    assert r2.nodes[0].normalized_text == "glycer1n"
    assert "possible_ocr_variation" in r2.nodes[0].warnings
    assert r2.nodes[0].status == "partial"


def test_10_ambiguous_umbrella_terms():
    r = normalize_label_text("natural flavour, colour, spices")
    assert [n.normalized_text for n in r.nodes] == [
        "natural flavour",
        "colour",
        "spices",
    ]
    # No resolution happened: nothing mapped to a molecule.
    assert all(n.identifier is None for n in r.nodes)


def test_11_mixtures():
    r = normalize_label_text(
        "peanut butter (peanut, salt), lecithin"
    )
    assert r.nodes[0].normalized_text == "peanut butter"
    assert r.nodes[1].normalized_text == "lecithin"
    assert r.nodes[1].percentage is None


def test_12_botanical_extract_terminology():
    r = normalize_label_text("Aloe Vera Extract, Water")
    assert r.nodes[0].normalized_text == "aloe vera extract"


def test_13_fragrance_flavour_terminology():
    r = normalize_label_text("Fragrance, Natural Flavouring")
    assert [n.normalized_text for n in r.nodes] == [
        "fragrance",
        "natural flavouring",
    ]


def test_14_empty_input():
    r = normalize_label_text("   ")
    assert r.nodes == []
    assert r.status == "failed"
    assert "no_parser_nodes_to_normalize" in r.limitations


def test_15_malformed_parser_nodes():
    parse = parse_label_ingredients("A (B, C, D")
    r = normalize_result(parse)
    # Nothing lost: observation kept, uncertainty marked.
    assert len(r.all_nodes()) >= 1
    assert r.status in ("partial", "failed")
    flat_warns = [w for n in r.all_nodes() for w in n.warnings]
    assert any("uncertain_parse" in w for w in flat_warns)
    # A fabricated empty node fails instead of inventing content.
    from app.services.ingredient_parser import IngredientNode

    bad = normalize_node(IngredientNode(raw_text="", name=""))
    assert bad.status == "failed"
    assert bad.normalized_text == ""


def test_16_idempotency():
    texts = [
        "  SODIUM   BENZOATE (E211) ",
        "Stabilizer (INS471), Salt (2%)",
        "Peanut Butter (83%) (Peanut (68%), Salt)",
        "glycer1n, water",
        "INS471",
    ]
    for text in texts:
        first = normalize_label_text(text)
        for node in first.all_nodes():
            second = normalize_label_text(node.normalized_text)
            assert len(second.nodes) == 1, text
            assert (
                second.nodes[0].normalized_text
                == node.normalized_text
            ), text


def test_alias_stays_text_not_identity():
    # "vitamin C" is recorded as text; alias->identity mapping is
    # entity resolution's job, not normalization's.
    r = normalize_label_text("Ascorbic Acid, Vitamin C")
    assert [n.normalized_text for n in r.nodes] == [
        "ascorbic acid",
        "vitamin c",
    ]


def test_safety_no_chemistry_no_identity_no_evidence():
    """Stage-4 regression guard: normalization invents nothing."""
    r = normalize_label_text(
        "Peanut Butter (Peanut (68%), Salt), "
        "Lecithin, Fragrance, Citric Acid (E330)"
    )
    forbidden = {
        "chemical_entity_id",
        "chemicalentityid",
        "smiles",
        "inchi",
        "inchikey",
        "cas",
        "cas_number",
        "formula",
        "molecular_formula",
        "molecular_weight",
        "molecularweight",
        "evidence",
        "verified",
        "verification",
        "role",
        "safety",
    }
    payload = json.dumps(r.to_dict()).lower()
    for node in r.all_nodes():
        keys = {k.lower() for k in node.to_dict()}
        assert not (keys & forbidden), keys & forbidden
    for token in (
        "chemical_entity",
        "smiles",
        "inchi",
        "verified",
        "evidence",
    ):
        assert token not in payload
    # Provenance points back to observation, not to a source claim.
    for node in r.all_nodes():
        assert node.provenance["parser_node_id"] == (
            node.parser_node_id
        )
        assert "source" not in node.provenance or (
            node.provenance.get("source") == "label_text"
        )


def test_result_json_serializable():
    r = normalize_label_text("A (B (10%), C (INS 471)), D")
    json.dumps(r.to_dict())
