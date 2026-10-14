"""Detect what the configured KiCad engine can actually do.

Nothing is assumed from a version number alone: each feature is probed by
inspecting ``kicad-cli`` help output and by importing ``pcbnew`` in KiCad's
Python. Features that are missing are reported with the reason, so the UI and
the AI can state clearly what cannot be checked.
"""

from __future__ import annotations

import json
import re
import tempfile
import threading
import time
from pathlib import Path

from app.kicad.runner import EdaRunner

_CACHE: dict = {}
_LOCK = threading.Lock()
_TTL_S = 600


def _subcommands(help_text: str) -> set[str]:
    """Extract subcommand names from kicad-cli help (formats of KiCad 7 and 9)."""
    names: set[str] = set()
    m = re.search(r"\{([a-z0-9_,\-]+)\}", help_text)
    if m:
        names.update(m.group(1).split(","))
    in_sub = False
    for line in help_text.splitlines():
        if line.strip().lower().startswith("subcommands"):
            in_sub = True
            continue
        if in_sub:
            mm = re.match(r"^\s{2}([a-z0-9_\-]+)\b", line)
            if mm:
                names.add(mm.group(1))
    return names


def _feature(available: bool, method: str | None = None, reason: str | None = None) -> dict:
    return {"available": available, "method": method if available else None, "reason": None if available else reason}


def detect_capabilities(runner: EdaRunner, force: bool = False) -> dict:
    key = json.dumps(runner.describe(), sort_keys=True)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and not force and time.time() - cached["_at"] < _TTL_S:
            return cached["value"]

    with tempfile.TemporaryDirectory(prefix="pcbai-probe-") as tmp:
        work = Path(tmp)
        work.chmod(0o777)
        version_res = runner.run("cli", ["version"], work, timeout=60)
        cli_ok = version_res.ok
        version = version_res.stdout.strip().splitlines()[-1] if cli_ok and version_res.stdout.strip() else None

        def sub(*args: str) -> set[str]:
            if not cli_ok:
                return set()
            r = runner.run("cli", [*args, "--help"], work, timeout=60)
            return _subcommands(r.stdout + "\n" + r.stderr)

        sch = sub("sch")
        sch_export = sub("sch", "export")
        pcb = sub("pcb")
        pcb_export = sub("pcb", "export")

        py_res = runner.run("python", ["probe.py"], work, timeout=60)
        try:
            py = json.loads(py_res.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            py = {"pcbnew": False, "error": (py_res.stderr or py_res.stdout).strip()[-500:]}

    pcbnew_ok = bool(py.get("pcbnew"))
    cli_reason = "kicad-cli not available: " + (version_res.stderr.strip()[-300:] or "not found")
    features = {
        "schematic_netlist": _feature("netlist" in sch_export, "kicad-cli sch export netlist",
                                      cli_reason if not cli_ok else "kicad-cli has no 'sch export netlist'"),
        "erc": _feature("erc" in sch, "kicad-cli sch erc",
                        cli_reason if not cli_ok else
                        f"kicad-cli {version} has no 'sch erc' (added in KiCad 8). KiCad 7 offers no headless "
                        "ERC API, so electrical rules cannot be checked with this engine."),
        "drc": (
            _feature(True, "kicad-cli pcb drc") if "drc" in pcb else
            _feature(True, "pcbnew.WriteDRCReport (KiCad Python)") if py.get("write_drc_report") else
            _feature(False, reason="neither 'kicad-cli pcb drc' nor pcbnew.WriteDRCReport is available")
        ),
        "schematic_parity": _feature("drc" in pcb, "kicad-cli pcb drc --schematic-parity",
                                     "requires 'kicad-cli pcb drc' (KiCad 8+)"),
        "pcb_generation": _feature(pcbnew_ok, "pcbnew Python API",
                                   f"KiCad Python (pcbnew) not importable: {py.get('error', 'unknown')}"),
        "gerbers": _feature("gerbers" in pcb_export, "kicad-cli pcb export gerbers", "not available"),
        "drill": _feature("drill" in pcb_export, "kicad-cli pcb export drill", "not available"),
        "bom": _feature("netlist" in sch_export, "derived from KiCad netlist export",
                        "requires 'kicad-cli sch export netlist'"),
        "schematic_svg": _feature("svg" in sch_export, "kicad-cli sch export svg", "not available"),
        "pcb_svg": _feature("svg" in pcb_export, "kicad-cli pcb export svg", "not available"),
        "step": _feature("step" in pcb_export, "kicad-cli pcb export step", "not available"),
        "glb": _feature("glb" in pcb_export, "kicad-cli pcb export glb",
                        "kicad-cli has no 'pcb export glb' (added in KiCad 9)"),
    }
    value = {
        "engine": "kicad",
        "runner": runner.describe(),
        "kicad_cli_available": cli_ok,
        "kicad_version": version,
        "pcbnew_version": py.get("version"),
        "features": features,
        "notes": [
            "3D component models (STEP/WRL) are not installed in the default KiCad images; "
            "3D previews use footprint courtyards as approximate bodies.",
        ],
        "detected_at": time.time(),
    }
    with _LOCK:
        _CACHE[key] = {"value": value, "_at": time.time()}
    return value
