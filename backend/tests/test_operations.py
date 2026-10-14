import pytest

from app.design.model import DesignDocument
from app.design.operations import OperationError, apply_operations, is_destructive, parse_operations
from app.kicad.schematic_layout import compute_layout, label_orientation
from app.templates.circuits import TEMPLATES, build_template


def apply(doc, ops, library):
    return apply_operations(doc, parse_operations(ops), library)


def test_add_and_connect(library):
    doc = apply(DesignDocument(), [
        {"op": "add_component", "part_id": "resistor_0805", "x": 100, "y": 100},
        {"op": "add_component", "part_id": "resistor_0805", "x": 130, "y": 100, "value": "4k7"},
        {"op": "connect", "net": "MID", "pins": [{"ref": "R1", "pin": "2"}, {"ref": "R2", "pin": "1"}]},
    ], library)
    assert [c.ref for c in doc.components] == ["R1", "R2"]
    assert doc.component("R2").value == "4k7"
    assert doc.component("R1").schematic.x == pytest.approx(100.33)  # snapped to 1.27 mm grid
    assert {p.key() for p in doc.net("MID").pins} == {("R1", "2"), ("R2", "1")}
    assert doc.component("R1").pcb is not None


def test_input_document_is_not_mutated(library):
    doc = DesignDocument()
    apply(doc, [{"op": "add_component", "part_id": "led_0805", "x": 0, "y": 0}], library)
    assert doc.components == []


@pytest.mark.parametrize("ops, message", [
    ([{"op": "add_component", "part_id": "nope", "x": 0, "y": 0}], "unknown part"),
    ([{"op": "add_component", "part_id": "led_0805", "x": 0, "y": 0},
      {"op": "connect", "net": "N", "pins": [{"ref": "D1", "pin": "3"}]}], "has no pin '3'"),
    ([{"op": "add_component", "part_id": "led_0805", "x": 0, "y": 0, "ref": "R1"}], "must use prefix"),
    ([{"op": "add_component", "part_id": "led_0805", "x": 0, "y": 0},
      {"op": "add_component", "part_id": "led_0805", "x": 0, "y": 0, "ref": "D1"}], "already used"),
    ([{"op": "add_component", "part_id": "led_0805", "x": 0, "y": 0},
      {"op": "connect", "net": "BAD NAME", "pins": [{"ref": "D1", "pin": "1"}]}], "invalid net name"),
    ([{"op": "add_component", "part_id": "led_0805", "x": 0, "y": 0},
      {"op": "connect", "net": "A", "pins": [{"ref": "D1", "pin": "1"}]},
      {"op": "connect", "net": "B", "pins": [{"ref": "D1", "pin": "1"}]}], "already connected to net 'A'"),
    ([{"op": "add_component", "part_id": "ams1117_3v3", "x": 0, "y": 0, "value": "LM7805"}], "is fixed"),
    ([{"op": "remove_component", "ref": "X9"}], "does not exist"),
    ([{"op": "add_track", "net": "NOPE", "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]}], "does not exist"),
])
def test_invalid_operations_are_rejected(library, ops, message):
    with pytest.raises(OperationError) as exc:
        apply(DesignDocument(), ops, library)
    assert message in str(exc.value)


def test_remove_component_cleans_nets_and_is_destructive(library):
    doc = build_template("led_indicator", library)
    ops = parse_operations([{"op": "remove_component", "ref": "D1"}])
    assert is_destructive(ops[0], doc)
    out = apply_operations(doc, ops, library)
    assert out.component("D1") is None
    assert all(p.ref != "D1" for n in out.nets for p in n.pins)
    assert out.net("LED_A") is not None  # still has R1.2


def test_load_template_destructive_only_when_not_empty(library):
    op = parse_operations([{"op": "load_template", "template_id": "led_indicator"}])[0]
    assert not is_destructive(op, DesignDocument())
    assert is_destructive(op, build_template("led_indicator", library))


def test_tracks_and_rename(library):
    doc = build_template("led_indicator", library)
    doc = apply(doc, [
        {"op": "add_track", "net": "VIN", "points": [{"x": 104, "y": 88.73}, {"x": 110, "y": 88.73},
                                                     {"x": 113.09, "y": 90}]},
        {"op": "rename_net", "name": "VIN", "new_name": "VBUS"},
    ], library)
    assert len(doc.tracks) == 2
    assert all(t.net == "VBUS" for t in doc.tracks)
    assert doc.tracks[0].width == doc.board.rules.track_width


@pytest.mark.parametrize("tpl", [t.id for t in TEMPLATES])
def test_templates_build(library, tpl):
    doc = build_template(tpl, library)
    assert doc.components and doc.nets
    pins = [(p.ref, p.pin) for n in doc.nets for p in n.pins]
    assert len(pins) == len(set(pins))


def test_pin_positions_follow_rotation(library):
    # Device:R pin 1 is at library (0, 3.81) - i.e. above the origin on screen when unrotated.
    for rot, expected in [(0, (100.33, 96.52)), (90, (96.52, 100.33)), (180, (100.33, 104.14)),
                          (270, (104.14, 100.33))]:
        doc = apply(DesignDocument(), [
            {"op": "add_component", "part_id": "resistor_0805", "x": 100.33, "y": 100.33, "rotation": rot},
            {"op": "connect", "net": "N", "pins": [{"ref": "R1", "pin": "1"}]},
        ], library)
        pin1 = next(p for p in compute_layout(doc, library).pins if p.number == "1")
        assert (pin1.x, pin1.y) == pytest.approx(expected), rot


def test_label_orientation():
    assert label_orientation((1, 0)) == (0, "left")
    assert label_orientation((-1, 0)) == (180, "right")
    assert label_orientation((0, -1)) == (90, "left")
    assert label_orientation((0, 1)) == (270, "right")
