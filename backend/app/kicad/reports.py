"""Parse KiCad's own ERC/DRC reports and netlists into a normalised structure.

Supported inputs
  * ERC/DRC JSON reports (``kicad-cli ... --format json``, KiCad 8+)
  * DRC text reports written by ``pcbnew.WriteDRCReport`` (KiCad 7)
  * KiCad S-expression netlists (``kicad-cli sch export netlist``)

Normalised violation::

    {"category": "violation" | "unconnected" | "parity", "severity": "error" | "warning" | "exclusion",
     "type": "clearance", "description": "...", "items": [{"description": "...", "x": mm, "y": mm}]}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.library import sexpr


def _item(raw: dict) -> dict:
    pos = raw.get("pos") or {}
    return {"description": raw.get("description", ""), "x": pos.get("x"), "y": pos.get("y")}


def _violation(raw: dict, category: str) -> dict:
    return {
        "category": category,
        "severity": raw.get("severity", "error"),
        "type": raw.get("type", "unknown"),
        "description": raw.get("description", ""),
        "items": [_item(i) for i in raw.get("items", [])],
    }


def summarize(violations: list[dict]) -> dict:
    counts = {"error": 0, "warning": 0, "exclusion": 0}
    for v in violations:
        counts[v["severity"]] = counts.get(v["severity"], 0) + 1
    return {
        "errors": counts.get("error", 0),
        "warnings": counts.get("warning", 0),
        "exclusions": counts.get("exclusion", 0),
        "total": len(violations),
    }


def parse_erc_json(text: str) -> dict:
    data = json.loads(text)
    violations = []
    for sheet in data.get("sheets", []):
        for v in sheet.get("violations", []):
            violations.append(_violation(v, "violation"))
    return {"kicad_version": data.get("kicad_version"), "violations": violations, "summary": summarize(violations)}


def parse_drc_json(text: str) -> dict:
    data = json.loads(text)
    violations = [_violation(v, "violation") for v in data.get("violations", [])]
    violations += [_violation(v, "unconnected") for v in data.get("unconnected_items", [])]
    violations += [_violation(v, "parity") for v in data.get("schematic_parity", [])]
    return {"kicad_version": data.get("kicad_version"), "violations": violations, "summary": summarize(violations)}


_SECTION_RE = re.compile(r"^\*\* Found (\d+) (DRC violations|unconnected pads|Footprint errors) \*\*")
_HEAD_RE = re.compile(r"^\[(?P<type>[a-z_]+)\]: (?P<desc>.*)$")
_SEV_RE = re.compile(r"Severity: (?P<sev>error|warning|exclusion|ignore)")
_POS_RE = re.compile(r"^@\((?P<x>-?[\d.]+) mm, (?P<y>-?[\d.]+) mm\): (?P<desc>.*)$")


def parse_drc_text(text: str) -> dict:
    """Parse a KiCad 7 ``WriteDRCReport`` text report."""
    violations: list[dict] = []
    category = "violation"
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        sec = _SECTION_RE.match(line)
        if sec:
            category = {"DRC violations": "violation", "unconnected pads": "unconnected",
                        "Footprint errors": "parity"}[sec.group(2)]
            current = None
            continue
        head = _HEAD_RE.match(line)
        if head:
            current = {"category": category, "severity": "error", "type": head.group("type"),
                       "description": head.group("desc"), "items": []}
            violations.append(current)
            continue
        if current is None:
            continue
        sev = _SEV_RE.search(line)
        if sev:
            current["severity"] = sev.group("sev")
            continue
        pos = _POS_RE.match(line)
        if pos:
            current["items"].append({"description": pos.group("desc"), "x": float(pos.group("x")),
                                     "y": float(pos.group("y"))})
    violations = [v for v in violations if v["severity"] != "ignore"]
    return {"kicad_version": None, "violations": violations, "summary": summarize(violations)}


@dataclass
class Netlist:
    components: dict[str, dict] = field(default_factory=dict)  # ref -> {value, footprint}
    nets: dict[str, set[tuple[str, str]]] = field(default_factory=dict)


def parse_netlist(text: str) -> Netlist:
    tree = sexpr.parse(text)
    nl = Netlist()
    comps = sexpr.child(tree, "components")
    for comp in sexpr.children(comps, "comp") if comps else []:
        ref = str(sexpr.value(sexpr.child(comp, "ref"), 1, ""))
        nl.components[ref] = {
            "value": str(sexpr.value(sexpr.child(comp, "value"), 1, "")),
            "footprint": str(sexpr.value(sexpr.child(comp, "footprint"), 1, "")),
        }
    nets = sexpr.child(tree, "nets")
    for net in sexpr.children(nets, "net") if nets else []:
        name = str(sexpr.value(sexpr.child(net, "name"), 1, ""))
        nodes = {
            (str(sexpr.value(sexpr.child(n, "ref"), 1, "")), str(sexpr.value(sexpr.child(n, "pin"), 1, "")))
            for n in sexpr.children(net, "node")
        }
        nl.nets[name] = nodes
    return nl


def normalize_net_name(name: str) -> str:
    """KiCad prefixes local-label nets on the root sheet with '/'."""
    return name[1:] if name.startswith("/") else name
