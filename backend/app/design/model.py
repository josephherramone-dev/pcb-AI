"""Canonical design document.

This model holds *design intent* and application metadata. Electrical meaning is
expressed exclusively through KiCad identifiers: library symbol ids, footprint
ids and pin numbers taken from KiCad's libraries. Native KiCad files are
generated from this document and KiCad itself is the judge of validity
(netlist export, ERC, DRC). All coordinates are millimetres in KiCad's
absolute coordinate system (Y axis pointing down).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DESIGN_SCHEMA_VERSION = 1
SCHEMATIC_GRID_MM = 1.27

REF_RE = re.compile(r"^#?[A-Z]{1,4}[0-9]{1,4}$")
NET_RE = re.compile(r"^[A-Za-z0-9_+\-.]{1,40}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PinRef(StrictModel):
    ref: str
    pin: str

    def key(self) -> tuple[str, str]:
        return (self.ref, self.pin)

    def __str__(self) -> str:
        return f"{self.ref}.{self.pin}"


class SchematicPlacement(StrictModel):
    x: float
    y: float
    rotation: Literal[0, 90, 180, 270] = 0


class PcbPlacement(StrictModel):
    x: float
    y: float
    rotation: float = 0.0
    side: Literal["front"] = "front"  # back-side placement is not supported yet


class Component(StrictModel):
    ref: str
    part_id: str
    lib_symbol: str
    footprint: str | None
    value: str
    in_bom: bool = True
    on_board: bool = True
    schematic: SchematicPlacement
    pcb: PcbPlacement | None = None
    properties: dict[str, str] = Field(default_factory=dict)

    @field_validator("ref")
    @classmethod
    def _ref(cls, v: str) -> str:
        if not REF_RE.match(v):
            raise ValueError(f"invalid reference designator {v!r}")
        return v


class Net(StrictModel):
    name: str
    pins: list[PinRef] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NET_RE.match(v):
            raise ValueError(
                f"invalid net name {v!r}: use 1-40 characters from A-Z a-z 0-9 _ + - ."
            )
        return v


class Point(StrictModel):
    x: float
    y: float


class Track(StrictModel):
    id: str
    net: str
    layer: Literal["F.Cu", "B.Cu"]
    width: float
    start: Point
    end: Point


class Via(StrictModel):
    id: str
    net: str
    at: Point
    diameter: float = 0.6
    drill: float = 0.3


class DesignRules(StrictModel):
    clearance: float = 0.2
    track_width: float = 0.25
    via_diameter: float = 0.6
    via_drill: float = 0.3


class Board(StrictModel):
    origin: Point = Field(default_factory=lambda: Point(x=100.0, y=80.0))
    width: float = 50.0
    height: float = 40.0
    copper_layers: Literal[2] = 2
    rules: DesignRules = Field(default_factory=DesignRules)

    def outline(self) -> list[tuple[float, float]]:
        x0, y0 = self.origin.x, self.origin.y
        return [(x0, y0), (x0 + self.width, y0), (x0 + self.width, y0 + self.height), (x0, y0 + self.height)]


class DesignDocument(StrictModel):
    schema_version: int = DESIGN_SCHEMA_VERSION
    title: str = ""
    components: list[Component] = Field(default_factory=list)
    nets: list[Net] = Field(default_factory=list)
    no_connects: list[PinRef] = Field(default_factory=list)
    board: Board = Field(default_factory=Board)
    tracks: list[Track] = Field(default_factory=list)
    vias: list[Via] = Field(default_factory=list)

    # --- lookups ---------------------------------------------------------
    def component(self, ref: str) -> Component | None:
        return next((c for c in self.components if c.ref == ref), None)

    def net(self, name: str) -> Net | None:
        return next((n for n in self.nets if n.name == name), None)

    def net_of_pin(self, ref: str, pin: str) -> Net | None:
        for n in self.nets:
            for p in n.pins:
                if p.ref == ref and p.pin == pin:
                    return n
        return None
