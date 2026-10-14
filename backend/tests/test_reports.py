import json

from app.design.model import DesignDocument
from app.kicad import reports
from app.kicad.engine import bom_csv, compare_netlist

# Excerpt of a real report written by KiCad 7.0.11 pcbnew.WriteDRCReport
DRC_TEXT = """** Drc report for out/test.kicad_pcb **
** Created on 2026-10-14 12:40:24 **

** Found 2 DRC violations **
[solder_mask_bridge]: Front solder mask aperture bridges items with different nets
    Rule: board setup solder mask min width; Severity: error
    @(49.0875 mm, 50.0000 mm): Track [VCC] on F.Cu, length 10.0000 mm
    @(50.9125 mm, 50.0000 mm): Pad 2 [GND] of R1 on F.Cu
[lib_footprint_issues]: The current configuration does not include the library ''.
    Local override; Severity: warning
    @(50.0000 mm, 50.0000 mm): Footprint R1

** Found 1 unconnected pads **
[unconnected_items]: Missing connection between items
    Local override; Severity: error
    @(50.9125 mm, 50.0000 mm): Pad 2 [GND] of R1 on F.Cu
    @(60.9125 mm, 50.0000 mm): Pad 2 [GND] of R2 on F.Cu

** Found 0 Footprint errors **

** End of Report **
"""

ERC_JSON = {
    "$schema": "https://schemas.kicad.org/erc.v1.json", "kicad_version": "9.0.9", "coordinate_units": "mm",
    "sheets": [{"path": "/", "violations": [
        {"type": "power_pin_not_driven", "severity": "error",
         "description": "Input Power pin not driven by any Output Power pins",
         "items": [{"description": "Symbol U1 Pin 8 [VCC, Power input, Line]", "pos": {"x": 1.0, "y": 2.0}}]},
        {"type": "pin_not_connected", "severity": "warning", "description": "Pin not connected", "items": []},
    ]}],
}

NETLIST = """(export (version "E")
  (components
    (comp (ref "R1") (value "1k") (footprint "Resistor_SMD:R_0805_2012Metric"))
    (comp (ref "R2") (value "1k") (footprint "Resistor_SMD:R_0805_2012Metric"))
    (comp (ref "D1") (value "LED") (footprint "LED_SMD:LED_0805_2012Metric")))
  (nets
    (net (code "1") (name "/A") (node (ref "R1") (pin "2")) (node (ref "D1") (pin "2")))
    (net (code "2") (name "unconnected-(R1-Pad1)") (node (ref "R1") (pin "1")))
    (net (code "3") (name "/B") (node (ref "R2") (pin "1")) (node (ref "D1") (pin "1")))))
"""


def test_parse_drc_text_report():
    r = reports.parse_drc_text(DRC_TEXT)
    assert r["summary"] == {"errors": 2, "warnings": 1, "exclusions": 0, "total": 3}
    unconnected = [v for v in r["violations"] if v["category"] == "unconnected"]
    assert len(unconnected) == 1 and len(unconnected[0]["items"]) == 2
    assert unconnected[0]["items"][1]["x"] == 60.9125


def test_parse_erc_json():
    r = reports.parse_erc_json(json.dumps(ERC_JSON))
    assert r["kicad_version"] == "9.0.9"
    assert r["summary"]["errors"] == 1 and r["summary"]["warnings"] == 1
    assert r["violations"][0]["items"][0]["x"] == 1.0


def test_parse_drc_json_categories():
    data = {"kicad_version": "9.0.9", "violations": [],
            "unconnected_items": [{"type": "unconnected_items", "severity": "error", "description": "x", "items": []}],
            "schematic_parity": [{"type": "net_conflict", "severity": "warning", "description": "y", "items": []}]}
    r = reports.parse_drc_json(json.dumps(data))
    assert [v["category"] for v in r["violations"]] == ["unconnected", "parity"]


def _doc(nets):
    comps = []
    for ref, part, sym, fp in (("R1", "resistor_0805", "Device:R", "Resistor_SMD:R_0805_2012Metric"),
                               ("R2", "resistor_0805", "Device:R", "Resistor_SMD:R_0805_2012Metric"),
                               ("D1", "led_0805", "Device:LED", "LED_SMD:LED_0805_2012Metric")):
        comps.append({"ref": ref, "part_id": part, "lib_symbol": sym, "footprint": fp, "value": "x",
                      "schematic": {"x": 0, "y": 0}})
    return DesignDocument.model_validate({"components": comps, "nets": nets})


def test_netlist_comparison_matches():
    nl = reports.parse_netlist(NETLIST)
    doc = _doc([{"name": "A", "pins": [{"ref": "R1", "pin": "2"}, {"ref": "D1", "pin": "2"}]},
                {"name": "B", "pins": [{"ref": "R2", "pin": "1"}, {"ref": "D1", "pin": "1"}]}])
    assert compare_netlist(doc, nl) == []


def test_netlist_comparison_reports_differences():
    nl = reports.parse_netlist(NETLIST)
    doc = _doc([{"name": "A", "pins": [{"ref": "R1", "pin": "2"}, {"ref": "R2", "pin": "2"}]}])
    problems = compare_netlist(doc, nl)
    assert any("pins not connected in KiCad: R2.2" in p for p in problems)
    assert any("unexpected pins connected in KiCad: D1.2" in p for p in problems)
    assert any("unexpected net B" in p for p in problems)


def test_bom_groups_by_value_and_footprint():
    csv_text = bom_csv(reports.parse_netlist(NETLIST))
    lines = csv_text.strip().splitlines()
    assert lines[0] == "References,Quantity,Value,Footprint"
    assert "R1 R2,2,1k,Resistor_SMD:R_0805_2012Metric" in lines
