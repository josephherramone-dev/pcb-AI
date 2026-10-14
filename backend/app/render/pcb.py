"""PCB render model for the browser: board outline, footprints (from KiCad
libraries), pad nets, tracks, vias and a preview ratsnest.

The ratsnest is an approximate preview computed here (minimum spanning tree over
pad positions, merging items joined by tracks). KiCad DRC remains the
authority on connectivity.
"""

from __future__ import annotations

import math

from app.design.model import DesignDocument
from app.library.service import LibraryService


def rotate(x: float, y: float, deg: float) -> tuple[float, float]:
    """Rotate a footprint-local point counter-clockwise on screen (Y axis down), like KiCad."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return x * c + y * s, -x * s + y * c


def footprint_render(fp) -> dict:
    return {
        "lib_id": fp.lib_id,
        "description": fp.description,
        "pads": [
            {"number": p.number, "type": p.pad_type, "shape": p.shape, "x": p.x, "y": p.y, "angle": p.angle,
             "width": p.width, "height": p.height, "layers": list(p.layers), "drill": p.drill,
             "roundrect_ratio": p.roundrect_ratio}
            for p in fp.pads
        ],
        "graphics": fp.graphics,
        "courtyard": list(fp.courtyard) if fp.courtyard else None,
        "has_3d_model_reference": bool(fp.models),
    }


class _UF:
    def __init__(self):
        self.p: dict = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def render_pcb(design: DesignDocument, library: LibraryService) -> dict:
    footprints: dict[str, dict] = {}
    comps = []
    pad_net: dict[tuple[str, str], str] = {}
    for net in design.nets:
        for p in net.pins:
            pad_net[(p.ref, p.pin)] = net.name

    # absolute pad positions per net
    pads_abs: list[dict] = []
    for comp in design.components:
        if not comp.on_board or not comp.footprint or comp.pcb is None:
            continue
        fp = library.footprints.get(comp.footprint)
        footprints.setdefault(comp.footprint, footprint_render(fp))
        nets = {}
        for pad in fp.pads:
            net = pad_net.get((comp.ref, pad.number))
            if net:
                nets[pad.number] = net
            dx, dy = rotate(pad.x, pad.y, comp.pcb.rotation)
            pads_abs.append({"ref": comp.ref, "number": pad.number, "net": net,
                             "x": round(comp.pcb.x + dx, 4), "y": round(comp.pcb.y + dy, 4),
                             "r": max(pad.width, pad.height) / 2})
        comps.append({"ref": comp.ref, "value": comp.value, "footprint": comp.footprint, "x": comp.pcb.x,
                      "y": comp.pcb.y, "rotation": comp.pcb.rotation, "side": comp.pcb.side, "pad_nets": nets})

    ratsnest = _ratsnest(design, pads_abs)
    b = design.board
    return {
        "board": {"outline": [list(p) for p in b.outline()], "origin": b.origin.model_dump(), "width": b.width,
                  "height": b.height, "rules": b.rules.model_dump(), "copper_layers": b.copper_layers},
        "footprints": footprints,
        "components": comps,
        "pads": pads_abs,
        "tracks": [t.model_dump() for t in design.tracks],
        "vias": [v.model_dump() for v in design.vias],
        "nets": [n.name for n in design.nets],
        "ratsnest": ratsnest,
        "ratsnest_note": "Preview ratsnest computed by the platform; KiCad DRC is authoritative for connectivity.",
    }


def _ratsnest(design: DesignDocument, pads: list[dict]) -> list[dict]:
    uf = _UF()
    out: list[dict] = []
    by_net: dict[str, list[dict]] = {}
    for p in pads:
        if p["net"]:
            by_net.setdefault(p["net"], []).append(p)

    def near(ax, ay, bx, by, tol):
        return math.hypot(ax - bx, ay - by) <= tol

    for net, net_pads in by_net.items():
        nodes = [("pad", p["ref"], p["number"], p["x"], p["y"], p["r"]) for p in net_pads]
        copper = [t for t in design.tracks if t.net == net]
        vias = [v for v in design.vias if v.net == net]
        for t in copper:
            a = ("pt", t.id, "a", t.start.x, t.start.y, t.width / 2)
            b = ("pt", t.id, "b", t.end.x, t.end.y, t.width / 2)
            uf.union(a[:3], b[:3])
            nodes += [a, b]
        for v in vias:
            nodes.append(("via", v.id, "", v.at.x, v.at.y, v.diameter / 2))
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                if a[0] == "pad" and b[0] == "pad":
                    if a[1] == b[1] and a[2] == b[2]:
                        uf.union(a[:3], b[:3])  # duplicated pad numbers in one footprint
                    continue
                if near(a[3], a[4], b[3], b[4], max(a[5], b[5]) + 1e-3):
                    uf.union(a[:3], b[:3])
        # Kruskal over pad pairs between different clusters
        pad_nodes = [n for n in nodes if n[0] == "pad"]
        edges = sorted(
            (math.hypot(a[3] - b[3], a[4] - b[4]), i, j)
            for i, a in enumerate(pad_nodes) for j, b in enumerate(pad_nodes) if i < j
        )
        for _, i, j in edges:
            a, b = pad_nodes[i], pad_nodes[j]
            if uf.find(a[:3]) != uf.find(b[:3]):
                uf.union(a[:3], b[:3])
                out.append({"net": net, "x1": a[3], "y1": a[4], "x2": b[3], "y2": b[4]})
    return out
