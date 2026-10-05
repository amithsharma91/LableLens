"""Systematic-name syntax preservation (Stage 14).

Locants (`propane-1,2,3-triol`) are punctuation syntax, not item
separators and not additive codes. These tests pin the syntactic
contract: chemically meaningful hyphens/commas survive parsing and
normalization intact, while real additive codes keep working.

No chemistry knowledge is asserted here -- only that text is not
damaged and codes are not hallucinated from word endings.
"""

from app.services.ingredient_normalizer import normalize_label_text
from app.services.ingredient_parser import parse_label_ingredients


def _one(text: str):
    parsed = parse_label_ingredients(text)
    assert len(parsed.nodes) == 1, parsed
    return parsed.nodes[0]


def test_locant_name_survives_parsing_intact():
    node = _one("propane-1,2,3-triol")
    assert node.name == "propane-1,2,3-triol"
    assert node.identifier is None
    assert node.classification == "ingredient"


def test_locant_variants_survive_parsing_intact():
    for text in (
        "butane-1,4-diol",
        "2-methylpropane",
        "2-hydroxypropane-1,2,3-tricarboxylic acid",
        "ethane-1,2-diol",
    ):
        node = _one(text)
        assert node.identifier is None, text
        assert node.name.replace(" ", "") == text.replace(" ", ""), text


def test_word_ending_in_e_is_not_an_additive_code():
    # The old trailing-id pattern read the final "e-1" of "propane-1"
    # as E1. A code tag must start at a token boundary.
    node = _one("propane-1")
    assert node.name == "propane-1"
    assert node.identifier is None


def test_rinse_471_is_not_an_additive_code():
    node = _one("Rinse 471")
    assert node.identifier is None
    assert node.name == "Rinse 471"


def test_locant_name_survives_normalization_intact():
    result = normalize_label_text("propane-1,2,3-triol")
    node = result.all_nodes()[0]
    assert node.raw_text == "propane-1,2,3-triol"
    assert node.normalized_text == "propane-1,2,3-triol"
    assert node.identifier is None


def test_ocr_whitespace_around_hyphen_is_preserved_literally():
    result = normalize_label_text("propane -1,2,3-triol")
    node = result.all_nodes()[0]
    assert node.raw_text == "propane -1,2,3-triol"
    assert node.normalized_text == "propane -1,2,3-triol"
    assert node.identifier is None


def test_locant_inside_nesting_survives():
    parsed = parse_label_ingredients("Blend (propane-1,2,3-triol, water)")
    assert len(parsed.nodes) == 1
    parent = parsed.nodes[0]
    assert parent.name == "Blend"
    assert [c.name for c in parent.children] == [
        "propane-1,2,3-triol", "water"]
    assert all(c.identifier is None for c in parent.children)


def test_real_additive_codes_still_detected():
    parsed = parse_label_ingredients("Citric Acid (E330)")
    assert parsed.nodes[0].identifier == "E330"
    assert parsed.nodes[0].name == "Citric Acid"
    assert _one("E330").identifier == "E330"
    assert _one("Stabilizer INS471").identifier == "INS471"
    assert _one("Stabilizer INS471").name == "Stabilizer"
    assert _one("Acid E 330").identifier == "E330"
    # CI codes were never detected in trailing position (the parser
    # only recognizes INS/E there); that scope is unchanged.
    assert _one("Color-CI15985").identifier is None


def test_real_codes_still_normalized_with_spacing():
    result = normalize_label_text("Citric Acid (E330)")
    node = result.all_nodes()[0]
    assert node.identifier == "E 330"
    assert node.normalized_text == "citric acid E 330"
    result = normalize_label_text("Stabilizer INS471")
    node = result.all_nodes()[0]
    assert node.identifier == "INS 471"


def test_stage13_label_segmentation_unchanged():
    cases = {
        # raw label text -> expected top-level node count
        "pledse recycle cans, cartons cts ainer fructose corn syrup "
        "1 can phosphoric acid, natural carbonated water, high caramel "
        "color, flavors, caffeine,": 6,
        "Water, Alcohol (21.6%), Sorbitol, Poloxamer 407, Benzoic Acid, "
        "Sodium Saccharin, Sodium Benzoate, Flavor, Green 3": 9,
        "alcohol, citric acid, FD&C Blue No. 1, FD&C Red No. 40, flavor, "
        "glycerin, propylene glycol, purified water, saccharin sodium, "
        "sodium benzoate, sodium citrate, sorbitol, sucralose, xanthan "
        "gum": 14,
    }
    for raw, count in cases.items():
        parsed = parse_label_ingredients(raw)
        assert len(parsed.nodes) == count, raw
        normalized = normalize_label_text(raw)
        assert len(normalized.nodes) == count, raw
