"""Schematic render model for the browser.

Symbol graphics come straight from the KiCad library (library coordinates,
Y up); the client applies each component's placement transform. Wires, labels
and pin positions come from :mod:`app.kicad.schematic_layout`, the same code
that writes the ``.kicad_sch`` file.
"""

from __future__ import annotations

from app.design.model import DesignDocument
from app.kicad.schematic_layout import compute_layout, lib_to_sheet, visible_pins
from app.library import sexpr
from app.library.service import LibraryService


def symbol_render(symbol) -> dict:
    return {
        "lib_id": symbol.lib_id,
        "graphics": [g for g in symbol.graphics if g["unit"] in (0, 1)],
        "pins": [
            {"number": p.number, "name": p.name, "electrical_type": p.electrical_type, "x": p.x, "y": p.y,
             "angle": p.angle, "length": p.length, "hidden": p.hidden}
            for p in visible_pins(symbol)
        ],
        "pin_names_hidden": symbol.pin_names_hidden,
        "pin_numbers_hidden": symbol.pin_numbers_hidden,
        "pin_name_offset": symbol.pin_name_offset,
        "is_power": symbol.is_power,
    }


def render_schematic(design: DesignDocument, library: LibraryService) -> dict:
    layout = compute_layout(design, library)
    components = []
    for comp in design.components:
        symbol = layout.symbols[comp.lib_symbol]
        lib_props = {str(p[1]): p for p in sexpr.children(symbol.node, "property")}
        fields = []
        for name, val in (("Reference", comp.ref), ("Value", comp.value)):
            lp = lib_props.get(name)
            at = sexpr.child(lp, "at") if lp else None
            x, y = lib_to_sheet(comp, sexpr.num(at, 1), sexpr.num(at, 2)) if at else (comp.schematic.x,
                                                                                     comp.schematic.y)
            hidden = bool(lp is not None and sexpr.is_hidden(lp)) or (symbol.is_power and name == "Reference")
            angle = ((sexpr.num(at, 3) if at else 0) + comp.schematic.rotation) % 180
            fields.append({"name": name, "value": val, "x": x, "y": y, "angle": angle, "hidden": hidden})
        components.append({
            "ref": comp.ref, "part_id": comp.part_id, "lib_symbol": comp.lib_symbol, "value": comp.value,
            "footprint": comp.footprint, "x": comp.schematic.x, "y": comp.schematic.y,
            "rotation": comp.schematic.rotation, "in_bom": comp.in_bom, "on_board": comp.on_board,
            "fields": fields,
        })
    return {
        "page": {"width": 297.0, "height": 210.0, "paper": "A4"},
        "symbols": {lib_id: symbol_render(s) for lib_id, s in layout.symbols.items()},
        "components": components,
        "pins": [
            {"ref": p.ref, "number": p.number, "name": p.name, "electrical_type": p.electrical_type,
             "x": p.x, "y": p.y, "net": p.net, "no_connect": p.no_connect}
            for p in layout.pins
        ],
        "wires": [{"net": s.net, "x1": s.x1, "y1": s.y1, "x2": s.x2, "y2": s.y2} for s in layout.stubs],
        "labels": [{"net": s.net, "x": s.x2, "y": s.y2, "angle": s.label_angle, "justify": s.label_justify}
                   for s in layout.stubs],
        "no_connects": [{"x": x, "y": y} for x, y in layout.no_connects],
        "nets": [{"name": n.name, "pins": [{"ref": p.ref, "pin": p.pin} for p in n.pins]} for n in design.nets],
    }
