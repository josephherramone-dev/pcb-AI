"""Schematic geometry shared by the KiCad writer and the browser preview.

Connectivity is expressed with KiCad *local net labels*: every connected pin
gets a short wire stub leading away from the symbol body and a label carrying
the net name at the end of the stub. Labels with equal names on one sheet are
connected by KiCad. Because the preview and the ``.kicad_sch`` writer use the
same function, the preview cannot show a connection that the file lacks - and
the generated file is then cross-checked against KiCad's own netlist export.

Coordinate conventions
  * Library symbol coordinates have the Y axis pointing up.
  * Schematic coordinates have the Y axis pointing down (KiCad file convention).
  * Symbol rotation is counter-clockwise as seen on screen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.design.model import Component, DesignDocument
from app.library.service import LibraryService
from app.library.symbols import PinDef, SymbolDef

STUB_MM = 2.54


def _r(v: float) -> float:
    return round(v + 0.0, 4)


def lib_to_sheet(comp: Component, x: float, y: float) -> tuple[float, float]:
    """Transform a library-space point into absolute schematic coordinates."""
    lx, ly = x, -y  # flip to Y-down
    a = math.radians(comp.schematic.rotation)
    c, s = round(math.cos(a), 12), round(math.sin(a), 12)
    rx = lx * c + ly * s
    ry = -lx * s + ly * c
    return _r(comp.schematic.x + rx), _r(comp.schematic.y + ry)


def pin_outward(comp: Component, pin: PinDef) -> tuple[float, float]:
    """Unit vector (schematic coords) pointing from the pin's connection point away from the body."""
    a = math.radians(pin.angle)
    dx, dy = -math.cos(a), math.sin(a)  # outward in Y-down local coordinates
    r = math.radians(comp.schematic.rotation)
    c, s = round(math.cos(r), 12), round(math.sin(r), 12)
    return _r(dx * c + dy * s), _r(-dx * s + dy * c)


def label_orientation(direction: tuple[float, float]) -> tuple[int, str]:
    """KiCad label angle and horizontal justification for a stub direction."""
    dx, dy = direction
    if abs(dx) >= abs(dy):
        return (0, "left") if dx > 0 else (180, "right")
    return (90, "left") if dy < 0 else (270, "right")


@dataclass
class PinGeom:
    ref: str
    number: str
    name: str
    electrical_type: str
    x: float
    y: float
    outward: tuple[float, float]
    net: str | None
    no_connect: bool


@dataclass
class Stub:
    net: str
    x1: float
    y1: float
    x2: float
    y2: float
    label_angle: int
    label_justify: str


@dataclass
class SchematicLayout:
    pins: list[PinGeom]
    stubs: list[Stub]
    no_connects: list[tuple[float, float]]
    symbols: dict[str, SymbolDef]


def visible_pins(symbol: SymbolDef) -> list[PinDef]:
    """Pins of unit 1 plus common (unit 0) pins. Multi-unit parts are not supported yet."""
    return [p for p in symbol.pins if p.unit in (0, 1)]


def compute_layout(doc: DesignDocument, library: LibraryService) -> SchematicLayout:
    pin_net: dict[tuple[str, str], str] = {}
    for net in doc.nets:
        for p in net.pins:
            pin_net[(p.ref, p.pin)] = net.name
    nc = {(p.ref, p.pin) for p in doc.no_connects}

    pins: list[PinGeom] = []
    stubs: list[Stub] = []
    ncs: list[tuple[float, float]] = []
    symbols: dict[str, SymbolDef] = {}
    for comp in doc.components:
        symbol = library.resolve(comp.part_id).symbol
        symbols[comp.lib_symbol] = symbol
        for pin in visible_pins(symbol):
            x, y = lib_to_sheet(comp, pin.x, pin.y)
            out = pin_outward(comp, pin)
            net = pin_net.get((comp.ref, pin.number))
            is_nc = (comp.ref, pin.number) in nc
            pins.append(PinGeom(comp.ref, pin.number, pin.name, pin.electrical_type, x, y, out, net, is_nc))
            if net:
                x2, y2 = _r(x + out[0] * STUB_MM), _r(y + out[1] * STUB_MM)
                angle, justify = label_orientation(out)
                stubs.append(Stub(net, x, y, x2, y2, angle, justify))
            elif is_nc:
                ncs.append((x, y))
    return SchematicLayout(pins=pins, stubs=stubs, no_connects=ncs, symbols=symbols)
