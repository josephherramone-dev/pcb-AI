from app.library import sexpr
from app.library.catalog import all_parts
from app.library.symbols import SymbolNotFound


def test_parse_and_dump_roundtrip():
    text = '(kicad_sch (version 20230121) (title "A \\"quoted\\" name") (hide yes) (effects (font (size 1.27 1.27)) hide))'
    tree = sexpr.parse(text)
    assert sexpr.tag(tree) == "kicad_sch"
    assert sexpr.child(tree, "title")[1] == 'A "quoted" name'
    again = sexpr.parse(sexpr.dumps(tree))
    assert again == tree
    assert sexpr.has_flag(tree, "hide")
    assert sexpr.is_hidden(tree)


def test_unbalanced_input_is_rejected():
    import pytest

    with pytest.raises(sexpr.SExprError):
        sexpr.parse("(a (b)")


def test_every_curated_part_resolves(library):
    for part in all_parts():
        resolved = library.resolve(part.id)
        assert resolved.symbol.pins, part.id
        assert resolved.symbol.unit_count == 1, f"{part.id}: multi-unit symbols are not supported yet"


def test_symbol_pins_map_to_footprint_pads(library):
    """Every pin of every placeable part must exist as a pad on its footprint."""
    for part in all_parts():
        resolved = library.resolve(part.id)
        if resolved.footprint is None:
            assert not part.on_board
            continue
        pins = {p.number for p in resolved.symbol.pins}
        missing = pins - resolved.footprint.pad_numbers
        assert not missing, f"{part.id}: pins {missing} have no pad on {part.footprint}"


def test_derived_symbol_is_flattened(library):
    ams = library.symbols.get("Regulator_Linear:AMS1117-3.3")
    assert {p.number for p in ams.pins} == {"1", "2", "3"}
    assert sexpr.child(ams.node, "extends") is None
    assert ams.node[1] == "Regulator_Linear:AMS1117-3.3"
    assert all(str(s[1]).startswith("AMS1117-3.3_") for s in sexpr.children(ams.node, "symbol"))
    assert "AMS1117" in ams.properties["Value"]


def test_unknown_symbol(library):
    import pytest

    with pytest.raises(SymbolNotFound):
        library.symbols.get("Device:DoesNotExist")


def test_part_search(library):
    hits = library.list_parts("regulator")
    assert [h["id"] for h in hits] == ["ams1117_3v3"]
    assert hits[0]["datasheet"].startswith("http")
