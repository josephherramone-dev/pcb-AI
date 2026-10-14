"""Validation status of a design revision.

Levels (each requires the previous one, and is evaluated per revision - a new
revision starts again at ``preview``):

``preview``
    The design document is well-formed and renders. Nothing has been checked by
    the EDA engine.
``structural``
    KiCad generated and re-loaded the native project, and KiCad's own netlist of
    the generated schematic matches the design intent exactly.
``rules_passed``
    KiCad ERC and DRC ran on this revision and reported no errors.
``verified``
    Full engineering verification (review, simulation, prototype). Never set
    automatically; recorded only by a human.
"""

from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CheckRecord, Revision
from app.design.model import DesignDocument
from app.kicad.schematic_layout import visible_pins
from app.library.service import LibraryService, PartUnavailable

LEVELS = {
    "preview": "Preview only - not checked by KiCad",
    "structural": "Structurally valid KiCad project (netlist verified by KiCad)",
    "rules_passed": "Passed KiCad ERC and DRC",
    "verified": "Engineering verified (human sign-off)",
}

CHECKS = ("kicad_project", "netlist_match", "erc", "drc")


def latest_checks(db: Session, revision: Revision) -> dict[str, CheckRecord]:
    out: dict[str, CheckRecord] = {}
    rows = db.scalars(select(CheckRecord).where(CheckRecord.revision_id == revision.id)
                      .order_by(CheckRecord.created_at.asc()))
    for row in rows:
        out[row.check] = row
    return out


def check_to_dict(c: CheckRecord) -> dict:
    return {
        "id": c.id, "check": c.check, "status": c.status, "message": c.message, "method": c.method,
        "engine_version": c.engine_version, "summary": c.summary, "violations": c.violations,
        "report_artifact_id": c.report_artifact_id, "job_id": c.job_id, "created_at": c.created_at.isoformat(),
    }


def validation_status(db: Session, revision: Revision) -> dict:
    checks = latest_checks(db, revision)

    def ok(name: str) -> bool:
        return name in checks and checks[name].status == "passed"

    level = "preview"
    blockers: list[str] = []
    if ok("kicad_project") and ok("netlist_match"):
        level = "structural"
        if ok("erc") and ok("drc"):
            level = "rules_passed"
        else:
            for name in ("erc", "drc"):
                c = checks.get(name)
                if c is None:
                    blockers.append(f"{name.upper()} has not been run on this revision")
                elif c.status == "unavailable":
                    blockers.append(f"{name.upper()} unavailable: {c.message}")
                elif c.status != "passed":
                    blockers.append(f"{name.upper()} {c.status}: {c.message}")
    else:
        for name in ("kicad_project", "netlist_match"):
            c = checks.get(name)
            if c is None:
                blockers.append("KiCad project has not been generated/validated for this revision")
                break
            if c.status != "passed":
                blockers.append(f"{name} {c.status}: {c.message}")
    blockers.append("Engineering verification requires human review and is never set automatically")
    return {
        "revision_id": revision.id,
        "level": level,
        "label": LEVELS[level],
        "levels": LEVELS,
        "checks": {name: check_to_dict(c) for name, c in checks.items()},
        "next_steps": blockers,
    }


def design_model_checks(design: DesignDocument, library: LibraryService) -> list[dict]:
    """Fast, preliminary checks on the design document itself.

    These help while editing but are NOT KiCad ERC/DRC and never count towards
    the validation level.
    """
    issues: list[dict] = []
    connected = {(p.ref, p.pin) for n in design.nets for p in n.pins}
    nc = {(p.ref, p.pin) for p in design.no_connects}
    for comp in design.components:
        try:
            symbol = library.resolve(comp.part_id).symbol
        except PartUnavailable as e:
            issues.append({"severity": "error", "code": "part_unavailable", "ref": comp.ref, "message": str(e)})
            continue
        for pin in visible_pins(symbol):
            key = (comp.ref, pin.number)
            if key not in connected and key not in nc:
                label = f"{pin.name} " if pin.name not in ("~", "") else ""
                issues.append({"severity": "warning", "code": "pin_unconnected", "ref": comp.ref,
                               "message": f"{comp.ref} pin {pin.number} {label}is not connected"})
        if comp.on_board and comp.pcb:
            b = design.board
            if not (b.origin.x <= comp.pcb.x <= b.origin.x + b.width and
                    b.origin.y <= comp.pcb.y <= b.origin.y + b.height):
                issues.append({"severity": "warning", "code": "outside_board", "ref": comp.ref,
                               "message": f"{comp.ref} footprint origin is outside the board outline"})
    for net in design.nets:
        if len(net.pins) == 1:
            issues.append({"severity": "warning", "code": "single_pin_net", "ref": None,
                           "message": f"net {net.name} connects only one pin"})
    refs = [c.ref for c in design.components if c.on_board and c.pcb]
    for i, a in enumerate(refs):
        ca = design.component(a)
        for b in refs[i + 1:]:
            cb = design.component(b)
            if math.hypot(ca.pcb.x - cb.pcb.x, ca.pcb.y - cb.pcb.y) < 1.0:
                issues.append({"severity": "warning", "code": "stacked_footprints", "ref": a,
                               "message": f"{a} and {b} footprints are placed on top of each other"})
    return issues
