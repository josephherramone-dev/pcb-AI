"""Read footprints from installed KiCad ``.pretty`` libraries (``.kicad_mod`` files).

Used for previews (pad geometry, silkscreen, courtyard) and for validating that
symbol pins map onto real footprint pads. The authoritative placement of
footprints in a board is still done by KiCad (``pcbnew.FootprintLoad``) when
the native project is generated.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.library import sexpr


class FootprintNotFound(LookupError):
    pass


@dataclass(frozen=True)
class PadDef:
    number: str
    pad_type: str  # smd | thru_hole | np_thru_hole | connect
    shape: str  # rect | roundrect | circle | oval | trapezoid | custom
    x: float
    y: float
    angle: float
    width: float
    height: float
    layers: tuple[str, ...]
    drill: float | None
    roundrect_ratio: float


@dataclass
class FootprintDef:
    lib_id: str
    library: str
    name: str
    description: str
    tags: str
    attributes: tuple[str, ...]
    pads: list[PadDef]
    graphics: list[dict]
    courtyard: tuple[float, float, float, float] | None  # minx, miny, maxx, maxy
    models: list[str] = field(default_factory=list)

    @property
    def pad_numbers(self) -> set[str]:
        return {p.number for p in self.pads if p.number}


class FootprintLibrary:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self.root.is_dir() and any(self.root.glob("*.pretty"))

    def get(self, lib_id: str) -> FootprintDef:
        lib, _, name = lib_id.partition(":")
        if not lib or not name:
            raise FootprintNotFound(f"invalid footprint id {lib_id!r}; expected 'Library:Footprint'")
        with self._lock:
            return _load(self.root, lib, name)


_GRAPHIC_LAYERS = {"F.SilkS", "B.SilkS", "F.Fab", "B.Fab", "F.CrtYd", "B.CrtYd", "F.Silkscreen",
                   "B.Silkscreen", "F.Courtyard", "B.Courtyard"}
_LAYER_ALIASES = {"F.Silkscreen": "F.SilkS", "B.Silkscreen": "B.SilkS",
                  "F.Courtyard": "F.CrtYd", "B.Courtyard": "B.CrtYd"}


def _xy(node) -> tuple[float, float]:
    return sexpr.num(node, 1), sexpr.num(node, 2)


@lru_cache(maxsize=512)
def _load(root: Path, lib: str, name: str) -> FootprintDef:
    path = root / f"{lib}.pretty" / f"{name}.kicad_mod"
    if not path.is_file():
        raise FootprintNotFound(f"footprint {lib}:{name} not found in {root}")
    tree = sexpr.parse(path.read_text(encoding="utf-8"))
    pads: list[PadDef] = []
    graphics: list[dict] = []
    for pad in sexpr.children(tree, "pad"):
        at = sexpr.child(pad, "at")
        size = sexpr.child(pad, "size")
        drill_node = sexpr.child(pad, "drill")
        drill = None
        if drill_node is not None:
            vals = [x for x in drill_node[1:] if not isinstance(x, list)]
            nums = [float(v) for v in vals if _is_number(v)]
            drill = nums[0] if nums else None
        layers_node = sexpr.child(pad, "layers")
        pads.append(
            PadDef(
                number=str(pad[1]),
                pad_type=str(pad[2]),
                shape=str(pad[3]),
                x=sexpr.num(at, 1),
                y=sexpr.num(at, 2),
                angle=sexpr.num(at, 3),
                width=sexpr.num(size, 1),
                height=sexpr.num(size, 2),
                layers=tuple(str(x) for x in (layers_node[1:] if layers_node else [])),
                drill=drill,
                roundrect_ratio=sexpr.num(sexpr.child(pad, "roundrect_rratio"), 1, 0.25),
            )
        )

    xs: list[float] = []
    ys: list[float] = []
    for item in tree[1:]:
        t = sexpr.tag(item)
        if t not in ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly"):
            continue
        layer = str(sexpr.value(sexpr.child(item, "layer"), 1, ""))
        if layer not in _GRAPHIC_LAYERS:
            continue
        layer = _LAYER_ALIASES.get(layer, layer)
        stroke = sexpr.child(item, "stroke")
        width = sexpr.num(sexpr.child(stroke, "width")) if stroke else sexpr.num(sexpr.child(item, "width"))
        g: dict = {"layer": layer, "width": width}
        if t == "fp_line":
            g.update(kind="line", start=list(_xy(sexpr.child(item, "start"))), end=list(_xy(sexpr.child(item, "end"))))
            pts = [g["start"], g["end"]]
        elif t == "fp_rect":
            s, e = _xy(sexpr.child(item, "start")), _xy(sexpr.child(item, "end"))
            g.update(kind="rect", start=list(s), end=list(e))
            pts = [list(s), list(e)]
        elif t == "fp_circle":
            c, e = _xy(sexpr.child(item, "center")), _xy(sexpr.child(item, "end"))
            r = ((c[0] - e[0]) ** 2 + (c[1] - e[1]) ** 2) ** 0.5
            g.update(kind="circle", center=list(c), radius=r)
            pts = [[c[0] - r, c[1] - r], [c[0] + r, c[1] + r]]
        elif t == "fp_arc":
            g.update(kind="arc", start=list(_xy(sexpr.child(item, "start"))),
                     mid=list(_xy(sexpr.child(item, "mid"))), end=list(_xy(sexpr.child(item, "end"))))
            pts = [g["start"], g["mid"], g["end"]]
        else:
            ptsn = sexpr.child(item, "pts")
            poly = [list(_xy(p)) for p in sexpr.children(ptsn, "xy")] if ptsn else []
            g.update(kind="poly", points=poly)
            pts = poly
        graphics.append(g)
        if layer.endswith("CrtYd"):
            for p in pts:
                xs.append(p[0])
                ys.append(p[1])

    attr = sexpr.child(tree, "attr")
    descr = sexpr.child(tree, "descr")
    tags = sexpr.child(tree, "tags")
    return FootprintDef(
        lib_id=f"{lib}:{name}",
        library=lib,
        name=name,
        description=str(sexpr.value(descr, 1, "")),
        tags=str(sexpr.value(tags, 1, "")),
        attributes=tuple(str(x) for x in (attr[1:] if attr else []) if not isinstance(x, list)),
        pads=pads,
        graphics=graphics,
        courtyard=(min(xs), min(ys), max(xs), max(ys)) if xs else None,
        models=[str(m[1]) for m in sexpr.children(tree, "model")],
    )


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
