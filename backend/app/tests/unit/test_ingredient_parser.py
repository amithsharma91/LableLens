"""Deterministic tests for the canonical hierarchical parser.

Covers brief §17 Cases A-J plus structural guarantees:
top-level/nested counts, parent-child links, order, percentages,
identifiers, raw-text preservation, and chemistry-free output.
"""

from app.services.ingredient_parser import parse_label_ingredients


def _names(result):
    return [n.name for n in result.nodes]


def test_case_a_flat_list():
    r = parse_label_ingredients("A, B, C")
    assert _names(r) == ["A", "B", "C"]
    assert all(n.depth == 0 for n in r.nodes)
    assert [n.position for n in r.nodes] == [0, 1, 2]
    assert all(n.children == [] for n in r.nodes)
    assert r.status == "complete"


def test_case_b_single_nesting():
    r = parse_label_ingredients("A (B, C), D")
    assert len(r.nodes) == 2
    a, d = r.nodes
    assert a.name == "A" and d.name == "D"
    assert [c.name for c in a.children] == ["B", "C"]
    assert all(c.depth == 1 for c in a.children)
    assert all(c.parent_id == a.id for c in a.children)
    assert [c.position for c in a.children] == [0, 1]
    assert d.children == []


def test_case_c_deep_nesting():
    r = parse_label_ingredients("A (B (C, D), E), F")
    assert len(r.nodes) == 2
    a, f = r.nodes
    assert [c.name for c in a.children] == ["B", "E"]
    b = a.children[0]
    assert [c.name for c in b.children] == ["C", "D"]
    assert b.children[0].depth == 2
    assert b.children[0].parent_id == b.id
    assert f.name == "F" and f.children == []


def test_case_d_percentages():
    r = parse_label_ingredients("A (10%), B (20%)")
    assert len(r.nodes) == 2
    assert r.nodes[0].percentage == 10.0
    assert r.nodes[1].percentage == 20.0
    assert r.nodes[0].name == "A"
    assert all(n.children == [] for n in r.nodes)


def test_case_e_additive_identifier():
    r = parse_label_ingredients("A (INS 471), B")
    assert len(r.nodes) == 2
    assert r.nodes[0].identifier == "INS471"
    assert r.nodes[0].name == "A"
    assert r.nodes[0].classification == "additive"
    assert r.nodes[1].identifier is None


def test_case_f_nested_percentage_and_identifier():
    r = parse_label_ingredients("A (B (10%), C (INS 471)), D")
    assert len(r.nodes) == 2
    a = r.nodes[0]
    assert [c.name for c in a.children] == ["B", "C"]
    assert a.children[0].percentage == 10.0
    assert a.children[1].identifier == "INS471"


def test_case_g_multiline_ocr():
    r = parse_label_ingredients("Ingredients:\nA,\n  B  ,\nC\n")
    # Header stripped; three ingredients survive in order.
    assert [n.normalized_name for n in r.nodes] == ["a", "b", "c"]
    assert r.status == "complete"


def test_case_h_malformed_unbalanced():
    r = parse_label_ingredients("A (B, C, D")
    # Must not crash; observation preserved; issue recorded.
    assert len(r.all_nodes()) >= 1
    assert r.raw_text == "A (B, C, D"
    assert r.status == "partial"
    assert any(
        "unbalanced" in lim or "stray" in lim
        for lim in r.limitations
    )


def test_case_i_quoted_commas():
    r = parse_label_ingredients('A ("B, C"), D')
    assert len(r.nodes) == 2
    assert len(r.nodes[0].children) == 1
    assert r.nodes[0].children[0].normalized_name == "b, c"


def test_case_j_realistic_food_label():
    text = (
        "Peanut Butter (83%) "
        "(Peanut (68%), Jaggery Powder (14%), "
        "Stabilizer (INS471), Salt), "
        "Whey Protein Concentrate (10%), "
        "Dark Chocolate (7%) "
        "(Cocoa Powder, Cocoa Butter, Natural Flavouring)"
    )
    r = parse_label_ingredients(text)
    assert len(r.nodes) == 3
    pb, whey, choc = r.nodes
    assert pb.name == "Peanut Butter"
    assert pb.percentage == 83.0
    assert [c.name for c in pb.children] == [
        "Peanut",
        "Jaggery Powder",
        "Stabilizer",
        "Salt",
    ]
    assert pb.children[0].percentage == 68.0
    assert pb.children[1].percentage == 14.0
    assert pb.children[2].identifier == "INS471"
    assert whey.name == "Whey Protein Concentrate"
    assert whey.percentage == 10.0
    assert choc.name == "Dark Chocolate"
    assert choc.percentage == 7.0
    assert [c.name for c in choc.children] == [
        "Cocoa Powder",
        "Cocoa Butter",
        "Natural Flavouring",
    ]


def test_square_brackets_and_semicolons():
    r = parse_label_ingredients("A [B; C]; D")
    assert len(r.nodes) == 2
    assert [c.name for c in r.nodes[0].children] == ["B", "C"]


def test_raw_text_preservation():
    text = "Sodiurn Benzoate (E211), Water"
    r = parse_label_ingredients(text)
    assert r.raw_text == text
    assert r.nodes[0].raw_text == "Sodiurn Benzoate (E211)"
    # Syntactic normalization only: typo preserved, not "fixed".
    assert r.nodes[0].normalized_name == "sodiurn benzoate"
    assert r.nodes[0].identifier == "E211"


def test_no_chemistry_invention():
    r = parse_label_ingredients(
        "peanut butter (peanut, salt), natural flavouring"
    )
    for n in r.all_nodes():
        assert n.match_status == "unresolved"
        assert n.verification_status == "unverified"
        d = n.to_dict()
        assert "smiles" not in d
        assert "formula" not in d
        assert "cas" not in d


def test_order_and_positions_preserved():
    r = parse_label_ingredients("Z, A (Y, B), M")
    assert _names(r) == ["Z", "A", "M"]
    assert [c.name for c in r.nodes[1].children] == ["Y", "B"]
    assert [c.position for c in r.nodes[1].children] == [0, 1]


def test_empty_input_is_partial_not_crash():
    r = parse_label_ingredients("   ")
    assert r.nodes == []
    assert r.status == "partial"
