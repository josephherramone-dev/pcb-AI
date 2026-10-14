"""Read schematic symbols from installed KiCad ``.kicad_sym`` libraries.

The data returned here is taken verbatim from KiCad's official library files:
pin numbers, pin names, electrical types, graphics, description and datasheet
URL. Nothing is synthesised. Derived symbols (``extends``) are flattened so they
can be embedded into a schematic's ``lib_symbols`` section, mirroring what
KiCad's own editor does when it places a derived symbol.
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.library import sexpr
from app.library.sexpr import Sym


class SymbolNotFound(LookupError):
    pass


@dataclass(frozen=True)
class PinDef:
    number: str
    name: str
    electrical_type: str
    x: float  # library coordinates, mm, Y axis pointing up
    y: float
    angle: float  # direction from connection point towards the body
    length: float
    unit: int
    hidden: bool


@dataclass
class SymbolDef:
    lib_id: str
    library: str
    name: str
    properties: dict[str, str]
    pins: list[PinDef]
    graphics: list[dict]
    unit_count: int
    is_power: bool
    pin_names_hidden: bool
    pin_numbers_hidden: bool
    pin_name_offset: float
    node: list = field(repr=False)  # flattened S-expression, named "<lib>:<name>"

    @property
    def description(self) -> str:
        return self.properties.get("Description") or self.properties.get("ki_description", "")

    @property
    def keywords(self) -> str:
        return self.properties.get("ki_keywords", "")

    @property
    def datasheet(self) -> str | None:
        ds = self.properties.get("Datasheet", "").strip()
        return None if ds in ("", "~") else ds

    def pin(self, number: str) -> PinDef | None:
        return next((p for p in self.pins if p.number == number), None)


class SymbolLibrary:
    """Lazily parses ``.kicad_sym`` files from a directory, with caching."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self.root.is_dir() and any(self.root.glob("*.kicad_sym"))

    def library_names(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.kicad_sym"))

    def get(self, lib_id: str) -> SymbolDef:
        lib, _, name = lib_id.partition(":")
        if not lib or not name:
            raise SymbolNotFound(f"invalid symbol id {lib_id!r}; expected 'Library:Symbol'")
        with self._lock:
            return _load_symbol(self.root, lib, name)


@lru_cache(maxsize=64)
def _parse_library(path: Path) -> dict[str, list]:
    tree = sexpr.parse(path.read_text(encoding="utf-8"))
    return {str(s[1]): s for s in sexpr.children(tree, "symbol")}


@lru_cache(maxsize=512)
def _load_symbol(root: Path, lib: str, name: str) -> SymbolDef:
    path = root / f"{lib}.kicad_sym"
    if not path.is_file():
        raise SymbolNotFound(f"symbol library {lib!r} not found in {root}")
    symbols = _parse_library(path)
    if name not in symbols:
        raise SymbolNotFound(f"symbol {name!r} not found in library {lib!r}")
    node = _flatten(symbols, name)
    return _build(lib, name, node)


def _flatten(symbols: dict[str, list], name: str) -> list:
    """Resolve ``(extends "Parent")`` into a standalone symbol definition."""
    node = copy.deepcopy(symbols[name])
    ext = sexpr.child(node, "extends")
    if ext is None:
        return node
    parent_name = str(ext[1])
    if parent_name not in symbols:
        raise SymbolNotFound(f"parent symbol {parent_name!r} of {name!r} not found")
    parent = _flatten(symbols, parent_name)
    child_props = {str(p[1]): p for p in sexpr.children(node, "property")}
    merged: list = [Sym("symbol"), name]
    for item in parent[2:]:
        t = sexpr.tag(item)
        if t == "property":
            pname = str(item[1])
            merged.append(child_props.pop(pname, item))
        elif t == "symbol":
            sub = copy.deepcopy(item)
            # Unit sub-symbols are named "<Parent>_<unit>_<style>"; rename them.
            suffix = str(sub[1])[len(parent_name):]
            sub[1] = name + suffix
            merged.append(sub)
        else:
            merged.append(item)
    # Properties that only exist on the derived symbol are appended.
    insert_at = max(i for i, x in enumerate(merged) if sexpr.tag(x) == "property") + 1
    for extra in child_props.values():
        merged.insert(insert_at, extra)
        insert_at += 1
    return merged


def _xy(node: list | None) -> tuple[float, float]:
    return sexpr.num(node, 1), sexpr.num(node, 2)


def _stroke_fill(node: list) -> dict:
    stroke = sexpr.child(node, "stroke")
    fill = sexpr.child(node, "fill")
    return {
        "stroke_width": sexpr.num(sexpr.child(stroke, "width")) if stroke else 0.0,
        "fill": str(sexpr.value(sexpr.child(fill, "type"), 1, "none")) if fill else "none",
    }


def _graphic(item: list, unit: int) -> dict | None:
    t = sexpr.tag(item)
    if t == "rectangle":
        sx, sy = _xy(sexpr.child(item, "start"))
        ex, ey = _xy(sexpr.child(item, "end"))
        return {"kind": "rect", "unit": unit, "x1": sx, "y1": sy, "x2": ex, "y2": ey, **_stroke_fill(item)}
    if t == "polyline":
        pts = sexpr.child(item, "pts")
        points = [list(_xy(p)) for p in sexpr.children(pts, "xy")] if pts else []
        return {"kind": "polyline", "unit": unit, "points": points, **_stroke_fill(item)}
    if t == "circle":
        cx, cy = _xy(sexpr.child(item, "center"))
        return {"kind": "circle", "unit": unit, "cx": cx, "cy": cy,
                "r": sexpr.num(sexpr.child(item, "radius")), **_stroke_fill(item)}
    if t == "arc":
        s = _xy(sexpr.child(item, "start"))
        m = _xy(sexpr.child(item, "mid"))
        e = _xy(sexpr.child(item, "end"))
        return {"kind": "arc", "unit": unit, "start": list(s), "mid": list(m), "end": list(e), **_stroke_fill(item)}
    if t == "text":
        x, y = _xy(sexpr.child(item, "at"))
        return {"kind": "text", "unit": unit, "text": str(item[1]), "x": x, "y": y,
                "angle": sexpr.num(sexpr.child(item, "at"), 3)}
    return None


def _build(lib: str, name: str, node: list) -> SymbolDef:
    props = {str(p[1]): str(p[2]) for p in sexpr.children(node, "property")}
    pins: list[PinDef] = []
    graphics: list[dict] = []
    units: set[int] = set()
    for sub in sexpr.children(node, "symbol"):
        sub_name = str(sub[1])
        try:
            unit = int(sub_name.rsplit("_", 2)[-2])
        except (ValueError, IndexError):
            unit = 0
        if unit:
            units.add(unit)
        for item in sub[2:]:
            if sexpr.tag(item) == "pin":
                at = sexpr.child(item, "at")
                pins.append(
                    PinDef(
                        number=str(sexpr.value(sexpr.child(item, "number"), 1, "")),
                        name=str(sexpr.value(sexpr.child(item, "name"), 1, "")),
                        electrical_type=str(item[1]),
                        x=sexpr.num(at, 1),
                        y=sexpr.num(at, 2),
                        angle=sexpr.num(at, 3),
                        length=sexpr.num(sexpr.child(item, "length")),
                        unit=unit,
                        hidden=sexpr.has_flag(item, "hide"),
                    )
                )
            else:
                g = _graphic(item, unit)
                if g:
                    graphics.append(g)

    pin_names = sexpr.child(node, "pin_names")
    pin_numbers = sexpr.child(node, "pin_numbers")
    flat = copy.deepcopy(node)
    flat[1] = f"{lib}:{name}"
    return SymbolDef(
        lib_id=f"{lib}:{name}",
        library=lib,
        name=name,
        properties=props,
        pins=pins,
        graphics=graphics,
        unit_count=max(units) if units else 1,
        is_power=sexpr.child(node, "power") is not None,
        pin_names_hidden=bool(pin_names is not None and sexpr.has_flag(pin_names, "hide")),
        pin_numbers_hidden=bool(pin_numbers is not None and sexpr.has_flag(pin_numbers, "hide")),
        pin_name_offset=sexpr.num(sexpr.child(pin_names, "offset"), 1, 0.508) if pin_names else 0.508,
        node=flat,
    )
