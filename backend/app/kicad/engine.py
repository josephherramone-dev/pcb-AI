"""EDA engine interface and its KiCad implementation.

The rest of the backend (and therefore the frontend) depends only on
:class:`EdaEngine`. The KiCad implementation generates native project files,
asks KiCad to export a netlist that is cross-checked against the design intent,
runs KiCad's ERC/DRC and produces manufacturing outputs. Every check result
records exactly which KiCad method produced it; if a capability is missing the
result is ``unavailable`` - never a fabricated pass.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from app.core.config import Settings
from app.design.model import DesignDocument
from app.kicad import reports
from app.kicad.capabilities import detect_capabilities
from app.kicad.runner import EdaRunner, make_runner
from app.kicad.schematic_writer import _uid, write_schematic
from app.library.service import LibraryService

CheckStatus = Literal["passed", "failed", "error", "unavailable"]


@dataclass
class CheckResult:
    check: str
    status: CheckStatus
    message: str
    method: str | None = None
    engine_version: str | None = None
    summary: dict = field(default_factory=dict)
    violations: list[dict] = field(default_factory=list)
    report_file: str | None = None
    log: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExportResult:
    status: CheckStatus
    message: str
    files: dict[str, str] = field(default_factory=dict)  # artifact kind -> relative path
    log: str = ""


def kicad_net_name(name: str) -> str:
    """Net name as KiCad derives it from a local label on the root sheet ("/" + label)."""
    return "/" + name


def project_slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:48]
    return slug or "project"


class EdaEngine(ABC):
    @abstractmethod
    def capabilities(self, force: bool = False) -> dict: ...

    @abstractmethod
    def generate_project(self, design: DesignDocument, slug: str, seed: str, workdir: Path) -> CheckResult: ...

    @abstractmethod
    def verify_netlist(self, design: DesignDocument, slug: str, workdir: Path) -> CheckResult: ...

    @abstractmethod
    def run_erc(self, slug: str, workdir: Path) -> CheckResult: ...

    @abstractmethod
    def run_drc(self, slug: str, workdir: Path) -> CheckResult: ...

    @abstractmethod
    def export_manufacturing(self, slug: str, workdir: Path) -> ExportResult: ...


class KiCadEngine(EdaEngine):
    def __init__(self, settings: Settings, library: LibraryService, runner: EdaRunner | None = None):
        self.settings = settings
        self.library = library
        self.runner = runner or make_runner(settings)

    # ------------------------------------------------------------------
    def capabilities(self, force: bool = False) -> dict:
        return detect_capabilities(self.runner, force=force)

    def _feature(self, name: str) -> dict:
        return self.capabilities()["features"][name]

    def _version(self) -> str | None:
        return self.capabilities().get("kicad_version")

    def _major(self) -> int | None:
        v = self._version() or ""
        m = re.match(r"(\d+)\.", v)
        return int(m.group(1)) if m else None

    # ------------------------------------------------------------------
    def generate_project(self, design: DesignDocument, slug: str, seed: str, workdir: Path) -> CheckResult:
        feat = self._feature("pcb_generation")
        if not feat["available"]:
            return CheckResult("kicad_project", "unavailable", feat["reason"])
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "reports").mkdir(exist_ok=True)
        logs: list[str] = []

        sch_text = write_schematic(design, self.library, slug, seed)
        (workdir / f"{slug}.kicad_sch").write_text(sch_text, encoding="utf-8")

        pad_nets: dict[str, dict[str, str]] = {}
        for net in design.nets:
            for p in net.pins:
                pad_nets.setdefault(p.ref, {})[p.pin] = kicad_net_name(net.name)
        components = [
            {
                "ref": c.ref, "value": c.value, "footprint": c.footprint,
                "x": c.pcb.x, "y": c.pcb.y, "rotation": c.pcb.rotation,
                "pads": pad_nets.get(c.ref, {}), "symbol_uuid": _uid(seed, "sym", c.ref),
            }
            for c in design.components
            if c.on_board and c.footprint and c.pcb is not None
        ]
        spec = {
            "output": f"{slug}.kicad_pcb",
            "title": design.title or slug,
            "footprint_dir": self.runner.engine_footprint_dir(),
            "nets": [kicad_net_name(n.name) for n in design.nets],
            "components": components,
            "outline": [list(p) for p in design.board.outline()],
            "tracks": [
                {"net": kicad_net_name(t.net), "layer": t.layer, "width": t.width,
                 "start": [t.start.x, t.start.y], "end": [t.end.x, t.end.y]}
                for t in design.tracks
            ],
            "vias": [{"net": kicad_net_name(v.net), "x": v.at.x, "y": v.at.y, "diameter": v.diameter, "drill": v.drill}
                     for v in design.vias],
        }
        (workdir / "pcb_spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
        res = self.runner.run("python", ["build_pcb.py", "pcb_spec.json"], workdir)
        logs.append(res.log())
        if not res.ok:
            return CheckResult("kicad_project", "error", "KiCad failed to build the PCB file",
                               method=feat["method"], engine_version=self._version(), log="\n".join(logs))
        try:
            pcb_summary = json.loads(res.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            return CheckResult("kicad_project", "error", "could not read the PCB build summary",
                               method=feat["method"], engine_version=self._version(), log="\n".join(logs))

        self._write_lib_tables(design, workdir)
        logs.append(self._patch_project_rules(design, workdir / f"{slug}.kicad_pro"))

        problems = []
        if pcb_summary.get("missing_pads"):
            problems.append("pins without matching footprint pads: " + ", ".join(pcb_summary["missing_pads"]))
        if pcb_summary["loaded"]["footprints"] != len(components):
            problems.append(
                f"KiCad loaded {pcb_summary['loaded']['footprints']} footprints, expected {len(components)}"
            )
        status: CheckStatus = "failed" if problems else "passed"
        msg = "; ".join(problems) if problems else (
            f"Native KiCad project written and re-loaded by KiCad ({len(components)} footprints, "
            f"{len(design.nets)} nets)"
        )
        return CheckResult("kicad_project", status, msg, method=feat["method"],
                           engine_version=pcb_summary.get("kicad_version"), summary=pcb_summary,
                           log="\n".join(logs))

    def _write_lib_tables(self, design: DesignDocument, workdir: Path) -> None:
        """Project library tables using KiCad's standard library path variables.

        Uses ``${KICADn_FOOTPRINT_DIR}`` / ``${KICADn_SYMBOL_DIR}`` so the
        downloaded project resolves the official libraries on any standard KiCad
        installation of the same major version.
        """
        major = self._major()
        if not major:
            return
        fp_libs = sorted({c.footprint.split(":", 1)[0] for c in design.components if c.footprint})
        sym_libs = sorted({c.lib_symbol.split(":", 1)[0] for c in design.components})
        fp = ["(fp_lib_table", "  (version 7)"]
        for lib in fp_libs:
            fp.append(f'  (lib (name "{lib}")(type "KiCad")(uri "${{KICAD{major}_FOOTPRINT_DIR}}/{lib}.pretty")'
                      f'(options "")(descr "KiCad official library"))')
        sym = ["(sym_lib_table", "  (version 7)"]
        for lib in sym_libs:
            sym.append(f'  (lib (name "{lib}")(type "KiCad")(uri "${{KICAD{major}_SYMBOL_DIR}}/{lib}.kicad_sym")'
                       f'(options "")(descr "KiCad official library"))')
        (workdir / "fp-lib-table").write_text("\n".join([*fp, ")"]) + "\n", encoding="utf-8")
        (workdir / "sym-lib-table").write_text("\n".join([*sym, ")"]) + "\n", encoding="utf-8")

    def _patch_project_rules(self, design: DesignDocument, pro_path: Path) -> str:
        """Apply the design's default net class rules to the KiCad project file written by KiCad."""
        if not pro_path.is_file():
            return f"project file {pro_path.name} not found; net class rules not applied"
        data = json.loads(pro_path.read_text(encoding="utf-8"))
        r = design.board.rules
        classes = data.setdefault("net_settings", {}).setdefault("classes", [])
        default = next((c for c in classes if c.get("name") == "Default"), None)
        if default is None:
            default = {"name": "Default"}
            classes.append(default)
        default.update({"clearance": r.clearance, "track_width": r.track_width,
                        "via_diameter": r.via_diameter, "via_drill": r.via_drill})
        pro_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return (f"applied Default net class: clearance {r.clearance} mm, track {r.track_width} mm, "
                f"via {r.via_diameter}/{r.via_drill} mm")

    # ------------------------------------------------------------------
    def verify_netlist(self, design: DesignDocument, slug: str, workdir: Path) -> CheckResult:
        feat = self._feature("schematic_netlist")
        if not feat["available"]:
            return CheckResult("netlist_match", "unavailable", feat["reason"])
        out = "reports/netlist.net"
        res = self.runner.run("cli", ["sch", "export", "netlist", "-o", out, f"{slug}.kicad_sch"], workdir)
        path = workdir / out
        if not res.ok or not path.is_file():
            return CheckResult("netlist_match", "error",
                               "KiCad could not load the generated schematic / export its netlist",
                               method=feat["method"], engine_version=self._version(), log=res.log())
        nl = reports.parse_netlist(path.read_text(encoding="utf-8"))
        problems = compare_netlist(design, nl)
        status: CheckStatus = "failed" if problems else "passed"
        violations = [{"category": "netlist", "severity": "error", "type": "netlist_mismatch",
                       "description": p, "items": []} for p in problems]
        msg = (f"KiCad's netlist differs from the design intent in {len(problems)} place(s)" if problems
               else f"KiCad's netlist matches the design intent ({len(nl.components)} components, "
                    f"{sum(1 for n in nl.nets if not n.startswith('unconnected-'))} nets)")
        return CheckResult("netlist_match", status, msg, method=feat["method"], engine_version=self._version(),
                           summary=reports.summarize(violations), violations=violations,
                           report_file=out, log=res.log())

    def run_erc(self, slug: str, workdir: Path) -> CheckResult:
        feat = self._feature("erc")
        if not feat["available"]:
            return CheckResult("erc", "unavailable", feat["reason"], engine_version=self._version())
        out = "reports/erc.json"
        res = self.runner.run("cli", ["sch", "erc", "--format", "json", "--severity-all", "--units", "mm",
                                      "-o", out, f"{slug}.kicad_sch"], workdir)
        return self._rule_check("erc", feat, res, workdir / out, out, reports.parse_erc_json)

    def run_drc(self, slug: str, workdir: Path) -> CheckResult:
        feat = self._feature("drc")
        if not feat["available"]:
            return CheckResult("drc", "unavailable", feat["reason"], engine_version=self._version())
        board = f"{slug}.kicad_pcb"
        if feat["method"].startswith("kicad-cli"):
            out = "reports/drc.json"
            args = ["pcb", "drc", "--format", "json", "--severity-all", "--units", "mm"]
            if self._feature("schematic_parity")["available"]:
                args.append("--schematic-parity")
            res = self.runner.run("cli", [*args, "-o", out, board], workdir)
            return self._rule_check("drc", feat, res, workdir / out, out, reports.parse_drc_json)
        out = "reports/drc.rpt"
        res = self.runner.run("python", ["drc_pcbnew.py", board, out], workdir)
        return self._rule_check("drc", feat, res, workdir / out, out, reports.parse_drc_text)

    def _rule_check(self, name, feat, res, path: Path, rel: str, parser) -> CheckResult:
        if not res.ok or not path.is_file():
            return CheckResult(name, "error", f"KiCad {name.upper()} did not produce a report",
                               method=feat["method"], engine_version=self._version(), log=res.log())
        try:
            parsed = parser(path.read_text(encoding="utf-8"))
        except (ValueError, KeyError) as e:
            return CheckResult(name, "error", f"could not parse KiCad {name.upper()} report: {e}",
                               method=feat["method"], engine_version=self._version(), report_file=rel,
                               log=res.log())
        s = parsed["summary"]
        status: CheckStatus = "passed" if s["errors"] == 0 else "failed"
        msg = f"KiCad {name.upper()}: {s['errors']} error(s), {s['warnings']} warning(s)"
        return CheckResult(name, status, msg, method=feat["method"],
                           engine_version=parsed.get("kicad_version") or self._version(),
                           summary=s, violations=parsed["violations"], report_file=rel, log=res.log())

    # ------------------------------------------------------------------
    def export_manufacturing(self, slug: str, workdir: Path) -> ExportResult:
        logs: list[str] = []
        files: dict[str, str] = {}
        board = f"{slug}.kicad_pcb"
        gerber_dir = workdir / "exports" / "gerbers"
        gerber_dir.mkdir(parents=True, exist_ok=True)

        if self._feature("gerbers")["available"]:
            layers = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
            res = self.runner.run("cli", ["pcb", "export", "gerbers", "--layers", layers,
                                          "-o", "exports/gerbers/", board], workdir)
            logs.append(res.log())
            if not res.ok:
                return ExportResult("error", "Gerber export failed", log="\n".join(logs))
        if self._feature("drill")["available"]:
            res = self.runner.run("cli", ["pcb", "export", "drill", "--format", "excellon",
                                          "--excellon-units", "mm", "-o", "exports/gerbers/", board], workdir)
            logs.append(res.log())
            if not res.ok:
                return ExportResult("error", "Drill export failed", log="\n".join(logs))
        produced = sorted(p for p in gerber_dir.iterdir() if p.is_file())
        if produced:
            zpath = workdir / "exports" / f"{slug}-gerbers.zip"
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in produced:
                    zf.write(p, p.name)
            files["gerbers_zip"] = str(zpath.relative_to(workdir))

        netlist = workdir / "reports" / "netlist.net"
        if netlist.is_file():
            bom = bom_csv(reports.parse_netlist(netlist.read_text(encoding="utf-8")))
            bom_path = workdir / "exports" / f"{slug}-bom.csv"
            bom_path.write_text(bom, encoding="utf-8")
            files["bom_csv"] = str(bom_path.relative_to(workdir))

        if not files:
            return ExportResult("unavailable", "no manufacturing outputs could be produced by this engine",
                                log="\n".join(logs))
        return ExportResult("passed", f"exported {len(produced)} Gerber/drill file(s)" +
                            (" and BOM" if "bom_csv" in files else ""), files=files, log="\n".join(logs))

    def package_project(self, slug: str, workdir: Path) -> str:
        zpath = workdir / "exports" / f"{slug}-kicad.zip"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in (f"{slug}.kicad_pro", f"{slug}.kicad_sch", f"{slug}.kicad_pcb", "fp-lib-table",
                         "sym-lib-table"):
                p = workdir / name
                if p.is_file():
                    zf.write(p, f"{slug}/{name}")
            for rep in ("erc.json", "drc.json", "drc.rpt", "netlist.net"):
                p = workdir / "reports" / rep
                if p.is_file():
                    zf.write(p, f"{slug}/reports/{rep}")
        return str(zpath.relative_to(workdir))


def compare_netlist(design: DesignDocument, nl: reports.Netlist) -> list[str]:
    """Compare KiCad's netlist with design intent. Power-flag symbols (#refs) are not in KiCad netlists."""
    problems: list[str] = []
    expected_refs = {c.ref for c in design.components if not c.ref.startswith("#")}
    actual_refs = set(nl.components)
    for ref in sorted(expected_refs - actual_refs):
        problems.append(f"component {ref} is missing from KiCad's netlist")
    for ref in sorted(actual_refs - expected_refs):
        problems.append(f"KiCad's netlist contains unexpected component {ref}")

    actual = {}
    for name, nodes in nl.nets.items():
        if name.startswith("unconnected-") and len(nodes) <= 1:
            continue
        actual[reports.normalize_net_name(name)] = nodes
    expected = {}
    for net in design.nets:
        pins = {(p.ref, p.pin) for p in net.pins if not p.ref.startswith("#")}
        if pins:
            expected[net.name] = pins
    for name, pins in sorted(expected.items()):
        got = actual.get(name)
        if got is None:
            problems.append(f"net {name} is missing from KiCad's netlist")
            continue
        missing = pins - got
        extra = got - pins
        if missing:
            problems.append(f"net {name}: pins not connected in KiCad: " +
                            ", ".join(f"{r}.{p}" for r, p in sorted(missing)))
        if extra:
            problems.append(f"net {name}: unexpected pins connected in KiCad: " +
                            ", ".join(f"{r}.{p}" for r, p in sorted(extra)))
    for name in sorted(set(actual) - set(expected)):
        problems.append(f"KiCad's netlist contains unexpected net {name} ({len(actual[name])} pins)")
    return problems


def bom_csv(nl: reports.Netlist) -> str:
    groups: dict[tuple[str, str], list[str]] = {}
    for ref, info in nl.components.items():
        groups.setdefault((info["value"], info["footprint"]), []).append(ref)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["References", "Quantity", "Value", "Footprint"])
    for (value, fp), refs in sorted(groups.items(), key=lambda kv: _natural_key(kv[1][0])):
        refs.sort(key=_natural_key)
        w.writerow([" ".join(refs), len(refs), value, fp])
    return buf.getvalue()


def _natural_key(ref: str):
    m = re.match(r"([A-Za-z#]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)
