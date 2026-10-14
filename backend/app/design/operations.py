"""Versioned, validated design operations.

Every change to a design - from the UI or from the AI assistant - is expressed
as a list of typed operations. :func:`apply_operations` validates each one
against the current design and the KiCad libraries and either returns a new
design document or raises :class:`OperationError`. The input document is never
mutated. Applying operations is the only way to create a new revision.
"""

from __future__ import annotations

import math
import uuid
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.design.model import (
    NET_RE,
    REF_RE,
    SCHEMATIC_GRID_MM,
    Component,
    DesignDocument,
    Net,
    PcbPlacement,
    PinRef,
    Point,
    SchematicPlacement,
    Track,
    Via,
)
from app.library.service import LibraryService, PartUnavailable

MAX_COORD = 2000.0  # mm, sanity bound for coordinates


class OperationError(ValueError):
    def __init__(self, index: int, op: str, message: str):
        super().__init__(f"operation #{index + 1} ({op}): {message}")
        self.index = index
        self.op = op
        self.message = message

    def to_dict(self) -> dict:
        return {"index": self.index, "op": self.op, "message": self.message}


class _Op(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddComponent(_Op):
    op: Literal["add_component"]
    part_id: str
    ref: str | None = None
    value: str | None = None
    x: float
    y: float
    rotation: Literal[0, 90, 180, 270] = 0
    pcb_x: float | None = None
    pcb_y: float | None = None


class RemoveComponent(_Op):
    op: Literal["remove_component"]
    ref: str


class SetValue(_Op):
    op: Literal["set_value"]
    ref: str
    value: str


class MoveSymbol(_Op):
    op: Literal["move_symbol"]
    ref: str
    x: float
    y: float
    rotation: Literal[0, 90, 180, 270] | None = None


class MoveFootprint(_Op):
    op: Literal["move_footprint"]
    ref: str
    x: float
    y: float
    rotation: float | None = None


class Connect(_Op):
    op: Literal["connect"]
    net: str
    pins: list[PinRef] = Field(min_length=1)


class Disconnect(_Op):
    op: Literal["disconnect"]
    pins: list[PinRef] = Field(min_length=1)


class RenameNet(_Op):
    op: Literal["rename_net"]
    name: str
    new_name: str


class DeleteNet(_Op):
    op: Literal["delete_net"]
    name: str


class SetNoConnect(_Op):
    op: Literal["set_no_connect"]
    pin: PinRef
    enabled: bool = True


class AddTrack(_Op):
    op: Literal["add_track"]
    net: str
    layer: Literal["F.Cu", "B.Cu"] = "F.Cu"
    width: float | None = None
    points: list[Point] = Field(min_length=2)


class DeleteTrack(_Op):
    op: Literal["delete_track"]
    id: str


class AddVia(_Op):
    op: Literal["add_via"]
    net: str
    x: float
    y: float


class DeleteVia(_Op):
    op: Literal["delete_via"]
    id: str


class SetBoard(_Op):
    op: Literal["set_board"]
    width: float
    height: float
    origin_x: float | None = None
    origin_y: float | None = None


class SetRules(_Op):
    op: Literal["set_rules"]
    clearance: float | None = None
    track_width: float | None = None
    via_diameter: float | None = None
    via_drill: float | None = None


class SetTitle(_Op):
    op: Literal["set_title"]
    title: str = Field(max_length=200)


class LoadTemplate(_Op):
    op: Literal["load_template"]
    template_id: str


Operation = Annotated[
    Union[
        AddComponent, RemoveComponent, SetValue, MoveSymbol, MoveFootprint, Connect, Disconnect,
        RenameNet, DeleteNet, SetNoConnect, AddTrack, DeleteTrack, AddVia, DeleteVia, SetBoard,
        SetRules, SetTitle, LoadTemplate,
    ],
    Field(discriminator="op"),
]

OperationList = TypeAdapter(list[Operation])

DESTRUCTIVE_OPS = {"remove_component", "delete_net", "delete_track", "delete_via", "load_template"}


def parse_operations(raw: list[dict]) -> list:
    return OperationList.validate_python(raw)


def is_destructive(op, design: DesignDocument) -> bool:
    if op.op == "load_template":
        return bool(design.components)
    return op.op in DESTRUCTIVE_OPS


def snap(v: float, grid: float = SCHEMATIC_GRID_MM) -> float:
    return round(round(v / grid) * grid, 4)


def _check_coord(v: float, what: str) -> None:
    if not math.isfinite(v) or abs(v) > MAX_COORD:
        raise ValueError(f"{what} {v!r} is out of range (|v| <= {MAX_COORD} mm)")


def next_ref(design: DesignDocument, prefix: str) -> str:
    used = {c.ref for c in design.components}
    i = 1
    while f"{prefix}{i}" in used:
        i += 1
    return f"{prefix}{i}"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def auto_pcb_position(design: DesignDocument) -> tuple[float, float]:
    """Simple grid placement inside the board for newly added footprints.

    This is a convenience starting point, not a placement optimiser.
    """
    b = design.board
    occupied = [(c.pcb.x, c.pcb.y) for c in design.components if c.pcb]
    pitch = 8.0
    cols = max(1, int((b.width - 6) // pitch) + 1)
    rows = max(1, int((b.height - 6) // pitch) + 1)
    for r in range(rows):
        for col in range(cols):
            x = b.origin.x + 5 + col * pitch
            y = b.origin.y + 5 + r * pitch
            if all(math.hypot(x - ox, y - oy) > pitch * 0.75 for ox, oy in occupied):
                return round(x, 3), round(y, 3)
    return round(b.origin.x + b.width / 2, 3), round(b.origin.y + b.height / 2, 3)


def apply_operations(design: DesignDocument, ops: list, library: LibraryService) -> DesignDocument:
    doc = design.model_copy(deep=True)
    for i, op in enumerate(ops):
        try:
            doc = _apply_one(doc, op, library)
        except OperationError:
            raise
        except (ValueError, PartUnavailable, KeyError) as e:
            raise OperationError(i, op.op, str(e).strip("'\"")) from e
    # Final structural validation of the resulting document.
    return DesignDocument.model_validate(doc.model_dump())


def _require_component(doc: DesignDocument, ref: str) -> Component:
    c = doc.component(ref)
    if c is None:
        raise ValueError(f"component {ref!r} does not exist")
    return c


def _require_pin(doc: DesignDocument, library: LibraryService, pin: PinRef) -> None:
    comp = _require_component(doc, pin.ref)
    symbol = library.resolve(comp.part_id).symbol
    if symbol.pin(pin.pin) is None:
        valid = ", ".join(sorted({p.number for p in symbol.pins}, key=_natural))
        raise ValueError(f"{comp.lib_symbol} ({pin.ref}) has no pin {pin.pin!r}; valid pins: {valid}")


def _natural(s: str):
    return (0, int(s)) if s.isdigit() else (1, s)


def _apply_one(doc: DesignDocument, op, library: LibraryService) -> DesignDocument:
    kind = op.op

    if kind == "add_component":
        resolved = library.resolve(op.part_id)
        part = resolved.part
        ref = op.ref or next_ref(doc, part.ref_prefix)
        if not REF_RE.match(ref):
            raise ValueError(f"invalid reference designator {ref!r}")
        if not ref.startswith(part.ref_prefix) or not ref[len(part.ref_prefix):].isdigit():
            raise ValueError(f"reference {ref!r} must use prefix {part.ref_prefix!r} followed by a number")
        if doc.component(ref):
            raise ValueError(f"reference {ref!r} is already used")
        if op.value is not None and not part.value_editable and op.value != part.default_value:
            raise ValueError(f"value of {part.id} is fixed to {part.default_value!r}")
        _check_coord(op.x, "x")
        _check_coord(op.y, "y")
        pcb = None
        if part.on_board:
            if op.pcb_x is not None and op.pcb_y is not None:
                _check_coord(op.pcb_x, "pcb_x")
                _check_coord(op.pcb_y, "pcb_y")
                px, py = op.pcb_x, op.pcb_y
            else:
                px, py = auto_pcb_position(doc)
            pcb = PcbPlacement(x=px, y=py)
        doc.components.append(
            Component(
                ref=ref,
                part_id=part.id,
                lib_symbol=part.lib_symbol,
                footprint=part.footprint,
                value=(op.value or part.default_value).strip()[:64] or part.default_value,
                in_bom=part.in_bom,
                on_board=part.on_board,
                schematic=SchematicPlacement(x=snap(op.x), y=snap(op.y), rotation=op.rotation),
                pcb=pcb,
            )
        )
        return doc

    if kind == "remove_component":
        _require_component(doc, op.ref)
        doc.components = [c for c in doc.components if c.ref != op.ref]
        for n in doc.nets:
            n.pins = [p for p in n.pins if p.ref != op.ref]
        doc.nets = [n for n in doc.nets if n.pins or _net_has_copper(doc, n.name)]
        doc.no_connects = [p for p in doc.no_connects if p.ref != op.ref]
        return doc

    if kind == "set_value":
        comp = _require_component(doc, op.ref)
        part = library.resolve(comp.part_id).part
        if not part.value_editable:
            raise ValueError(f"value of {comp.ref} ({part.id}) is fixed")
        value = op.value.strip()
        if not value or len(value) > 64:
            raise ValueError("value must be 1-64 characters")
        comp.value = value
        return doc

    if kind == "move_symbol":
        comp = _require_component(doc, op.ref)
        _check_coord(op.x, "x")
        _check_coord(op.y, "y")
        comp.schematic.x, comp.schematic.y = snap(op.x), snap(op.y)
        if op.rotation is not None:
            comp.schematic.rotation = op.rotation
        return doc

    if kind == "move_footprint":
        comp = _require_component(doc, op.ref)
        if not comp.on_board or comp.pcb is None:
            raise ValueError(f"{op.ref} has no footprint on the board")
        _check_coord(op.x, "x")
        _check_coord(op.y, "y")
        comp.pcb.x, comp.pcb.y = round(op.x, 4), round(op.y, 4)
        if op.rotation is not None:
            comp.pcb.rotation = round(op.rotation % 360, 3)
        return doc

    if kind == "connect":
        if not NET_RE.match(op.net):
            raise ValueError(f"invalid net name {op.net!r}")
        net = doc.net(op.net)
        if net is None:
            net = Net(name=op.net)
            doc.nets.append(net)
        for pin in op.pins:
            _require_pin(doc, library, pin)
            existing = doc.net_of_pin(pin.ref, pin.pin)
            if existing is not None and existing.name != op.net:
                raise ValueError(f"pin {pin} is already connected to net {existing.name!r}; disconnect it first")
            if any(nc.key() == pin.key() for nc in doc.no_connects):
                raise ValueError(f"pin {pin} is marked as no-connect")
            if existing is None:
                net.pins.append(PinRef(ref=pin.ref, pin=pin.pin))
        return doc

    if kind == "disconnect":
        for pin in op.pins:
            net = doc.net_of_pin(pin.ref, pin.pin)
            if net is None:
                raise ValueError(f"pin {pin} is not connected to any net")
            net.pins = [p for p in net.pins if p.key() != pin.key()]
        doc.nets = [n for n in doc.nets if n.pins or _net_has_copper(doc, n.name)]
        return doc

    if kind == "rename_net":
        net = doc.net(op.name)
        if net is None:
            raise ValueError(f"net {op.name!r} does not exist")
        if not NET_RE.match(op.new_name):
            raise ValueError(f"invalid net name {op.new_name!r}")
        if doc.net(op.new_name):
            raise ValueError(f"net {op.new_name!r} already exists")
        net.name = op.new_name
        for t in doc.tracks:
            if t.net == op.name:
                t.net = op.new_name
        for v in doc.vias:
            if v.net == op.name:
                v.net = op.new_name
        return doc

    if kind == "delete_net":
        if doc.net(op.name) is None:
            raise ValueError(f"net {op.name!r} does not exist")
        doc.nets = [n for n in doc.nets if n.name != op.name]
        doc.tracks = [t for t in doc.tracks if t.net != op.name]
        doc.vias = [v for v in doc.vias if v.net != op.name]
        return doc

    if kind == "set_no_connect":
        _require_pin(doc, library, op.pin)
        if op.enabled:
            net = doc.net_of_pin(op.pin.ref, op.pin.pin)
            if net is not None:
                raise ValueError(f"pin {op.pin} is connected to net {net.name!r}")
            if not any(nc.key() == op.pin.key() for nc in doc.no_connects):
                doc.no_connects.append(PinRef(ref=op.pin.ref, pin=op.pin.pin))
        else:
            doc.no_connects = [nc for nc in doc.no_connects if nc.key() != op.pin.key()]
        return doc

    if kind == "add_track":
        if doc.net(op.net) is None:
            raise ValueError(f"net {op.net!r} does not exist")
        width = op.width if op.width is not None else doc.board.rules.track_width
        if not (0.05 <= width <= 10):
            raise ValueError("track width must be between 0.05 and 10 mm")
        pts = op.points
        for p in pts:
            _check_coord(p.x, "x")
            _check_coord(p.y, "y")
        for a, b in zip(pts, pts[1:], strict=False):
            if math.hypot(a.x - b.x, a.y - b.y) < 1e-6:
                continue
            doc.tracks.append(
                Track(id=_new_id("trk"), net=op.net, layer=op.layer, width=round(width, 4),
                      start=Point(x=round(a.x, 4), y=round(a.y, 4)), end=Point(x=round(b.x, 4), y=round(b.y, 4)))
            )
        return doc

    if kind == "delete_track":
        if not any(t.id == op.id for t in doc.tracks):
            raise ValueError(f"track {op.id!r} does not exist")
        doc.tracks = [t for t in doc.tracks if t.id != op.id]
        return doc

    if kind == "add_via":
        if doc.net(op.net) is None:
            raise ValueError(f"net {op.net!r} does not exist")
        _check_coord(op.x, "x")
        _check_coord(op.y, "y")
        r = doc.board.rules
        doc.vias.append(Via(id=_new_id("via"), net=op.net, at=Point(x=round(op.x, 4), y=round(op.y, 4)),
                            diameter=r.via_diameter, drill=r.via_drill))
        return doc

    if kind == "delete_via":
        if not any(v.id == op.id for v in doc.vias):
            raise ValueError(f"via {op.id!r} does not exist")
        doc.vias = [v for v in doc.vias if v.id != op.id]
        return doc

    if kind == "set_board":
        if not (5 <= op.width <= 500 and 5 <= op.height <= 500):
            raise ValueError("board width and height must be between 5 and 500 mm")
        doc.board.width, doc.board.height = op.width, op.height
        if op.origin_x is not None:
            _check_coord(op.origin_x, "origin_x")
            doc.board.origin.x = op.origin_x
        if op.origin_y is not None:
            _check_coord(op.origin_y, "origin_y")
            doc.board.origin.y = op.origin_y
        return doc

    if kind == "set_rules":
        r = doc.board.rules
        for field in ("clearance", "track_width", "via_diameter", "via_drill"):
            v = getattr(op, field)
            if v is not None:
                if not (0.05 <= v <= 5):
                    raise ValueError(f"{field} must be between 0.05 and 5 mm")
                setattr(r, field, v)
        if r.via_drill >= r.via_diameter:
            raise ValueError("via drill must be smaller than via diameter")
        return doc

    if kind == "set_title":
        doc.title = op.title.strip()
        return doc

    if kind == "load_template":
        from app.templates.circuits import build_template

        return build_template(op.template_id, library)

    raise ValueError(f"unsupported operation {kind!r}")


def _net_has_copper(doc: DesignDocument, net: str) -> bool:
    return any(t.net == net for t in doc.tracks) or any(v.net == net for v in doc.vias)
