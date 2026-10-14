"""Starter circuit templates.

Templates are expressed as design operations, so they go through exactly the
same validation as user and AI edits. Each template also declares the pin
*names* it relies on; building the template fails loudly if the installed KiCad
library disagrees (for example after a library update), instead of silently
producing a wrong circuit.

Component values in templates are starting points with stated assumptions. They
are NOT verified engineering designs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.design.model import DesignDocument
from app.library.service import LibraryService


@dataclass(frozen=True)
class CircuitTemplate:
    id: str
    name: str
    description: str
    assumptions: tuple[str, ...]
    operations: tuple[dict, ...]
    # ref -> pin number -> accepted pin names (KiCad renamed some pins between releases)
    expected_pin_names: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    board: tuple[float, float] = (40.0, 30.0)


def _c(part_id, ref, x, y, value=None, rotation=0, pcb=None):
    op = {"op": "add_component", "part_id": part_id, "ref": ref, "x": x, "y": y, "rotation": rotation}
    if value is not None:
        op["value"] = value
    if pcb is not None:
        op["pcb_x"], op["pcb_y"] = pcb
    return op


def _n(net, *pins):
    return {"op": "connect", "net": net, "pins": [{"ref": r, "pin": p} for r, p in (s.split(".") for s in pins)]}


TEMPLATES: tuple[CircuitTemplate, ...] = (
    CircuitTemplate(
        id="led_indicator",
        name="LED indicator",
        description="Power input header driving an LED through a current-limiting resistor.",
        assumptions=(
            "Supply voltage assumed to be 5 V on J1 pin 1 (VIN) relative to pin 2 (GND).",
            "R1 = 1k gives roughly (5 V - Vf) / 1 kOhm, i.e. about 3 mA for an LED with Vf near 2 V. "
            "Check the forward voltage and current rating in your LED's datasheet.",
            "PWR_FLAG symbols tell ERC that VIN and GND are supplied externally through J1.",
        ),
        board=(30.0, 20.0),
        operations=(
            {"op": "set_board", "width": 30, "height": 20, "origin_x": 100, "origin_y": 80},
            _c("header_1x02", "J1", 63.5, 88.9, pcb=(104.0, 88.73)),
            _c("resistor_0805", "R1", 88.9, 88.9, value="1k", rotation=90, pcb=(114.0, 90.0)),
            _c("led_0805", "D1", 114.3, 88.9, rotation=180, pcb=(122.0, 90.0)),
            _c("pwr_flag", "#FLG1", 76.2, 76.2),
            _c("pwr_flag", "#FLG2", 76.2, 101.6),
            _n("VIN", "J1.1", "R1.1", "#FLG1.1"),
            _n("LED_A", "R1.2", "D1.2"),
            _n("GND", "D1.1", "J1.2", "#FLG2.1"),
        ),
        expected_pin_names={"D1": {"1": ("K",), "2": ("A",)}},
    ),
    CircuitTemplate(
        id="ldo_3v3",
        name="3.3 V LDO regulator",
        description="AMS1117-3.3 linear regulator with input/output capacitors and headers.",
        assumptions=(
            "Input voltage on J1 assumed to be within the AMS1117-3.3 input range given in its datasheet.",
            "C1 = 10u and C2 = 22u are placeholder values; check the regulator datasheet for "
            "required capacitance, ESR and dielectric for stability.",
            "Thermal dissipation (VIN - 3.3 V) x I_load has not been evaluated.",
        ),
        board=(40.0, 25.0),
        operations=(
            {"op": "set_board", "width": 40, "height": 25, "origin_x": 100, "origin_y": 80},
            _c("header_1x02", "J1", 50.8, 88.9, pcb=(104.0, 91.23)),
            _c("ams1117_3v3", "U1", 101.6, 88.9, pcb=(120.0, 92.0)),
            _c("capacitor_0805", "C1", 76.2, 96.52, value="10u", pcb=(111.0, 98.0)),
            _c("capacitor_0805", "C2", 127.0, 96.52, value="22u", pcb=(129.0, 98.0)),
            _c("header_1x02", "J2", 152.4, 88.9, rotation=180, pcb=(136.0, 91.23)),
            _c("pwr_flag", "#FLG1", 63.5, 76.2),
            _c("pwr_flag", "#FLG2", 63.5, 109.22),
            _n("VIN", "J1.1", "U1.3", "C1.1", "#FLG1.1"),
            _n("+3V3", "U1.2", "C2.1", "J2.1"),
            _n("GND", "J1.2", "U1.1", "C1.2", "C2.2", "J2.2", "#FLG2.1"),
        ),
        expected_pin_names={"U1": {"1": ("GND",), "2": ("VO",), "3": ("VI",)}},
    ),
    CircuitTemplate(
        id="ne555_blinker",
        name="NE555 astable LED blinker",
        description="Classic NE555 astable oscillator driving an LED.",
        assumptions=(
            "Supply assumed to be 5-9 V on J1; confirm against the NE555 datasheet supply range.",
            "Astable frequency from the datasheet formula f = 1.44 / ((R1 + 2*R2) * C1); with "
            "R1 = 10k, R2 = 47k, C1 = 10u this is about 1.4 Hz before component tolerances.",
            "R3 = 1k limits LED current; verify against the LED datasheet and supply voltage.",
            "C1 uses the 0805 ceramic footprint; a 10u part in 0805 must be checked for voltage rating and DC bias.",
        ),
        board=(45.0, 35.0),
        operations=(
            {"op": "set_board", "width": 45, "height": 35, "origin_x": 100, "origin_y": 80},
            _c("header_1x02", "J1", 38.1, 76.2, pcb=(104.0, 86.0)),
            _c("ne555_dip8", "U1", 101.6, 88.9, pcb=(120.0, 92.0)),
            _c("resistor_0805", "R1", 132.08, 72.39, value="10k", pcb=(134.0, 86.0)),
            _c("resistor_0805", "R2", 132.08, 97.79, value="47k", pcb=(134.0, 92.0)),
            _c("capacitor_0805", "C1", 66.04, 104.14, value="10u", pcb=(110.0, 106.0)),
            _c("capacitor_0805", "C2", 76.2, 104.14, value="10n", pcb=(116.0, 106.0)),
            _c("capacitor_0805", "C3", 63.5, 72.39, value="100n", pcb=(110.0, 86.0)),
            _c("resistor_0805", "R3", 152.4, 80.01, value="1k", pcb=(134.0, 100.0)),
            _c("led_0805", "D1", 152.4, 106.68, rotation=90, pcb=(140.0, 100.0)),
            _c("pwr_flag", "#FLG1", 50.8, 63.5),
            _c("pwr_flag", "#FLG2", 50.8, 116.84),
            _n("VCC", "J1.1", "U1.8", "U1.4", "R1.1", "C3.1", "#FLG1.1"),
            _n("DIS", "R1.2", "U1.7", "R2.1"),
            _n("TRIG", "R2.2", "U1.6", "U1.2", "C1.1"),
            _n("CV", "U1.5", "C2.1"),
            _n("OUT", "U1.3", "R3.1"),
            _n("LED_A", "R3.2", "D1.2"),
            _n("GND", "J1.2", "U1.1", "C1.2", "C2.2", "C3.2", "D1.1", "#FLG2.1"),
        ),
        expected_pin_names={
            # KiCad 7 names / KiCad 9 names
            "U1": {"1": ("GND",), "2": ("TR", "TRIG"), "3": ("Q", "OUT"), "4": ("R", "~{RST}"),
                   "5": ("CV", "CONT"), "6": ("THR", "THRES"), "7": ("DIS", "DISCH"), "8": ("VCC",)},
            "D1": {"1": ("K",), "2": ("A",)},
        },
    ),
)

_BY_ID = {t.id: t for t in TEMPLATES}


class TemplateError(ValueError):
    pass


def get_template(template_id: str) -> CircuitTemplate | None:
    return _BY_ID.get(template_id)


def build_template(template_id: str, library: LibraryService) -> DesignDocument:
    from app.design.operations import apply_operations, parse_operations

    tpl = get_template(template_id)
    if tpl is None:
        raise TemplateError(f"unknown template {template_id!r}")
    doc = DesignDocument(title=tpl.name)
    doc = apply_operations(doc, parse_operations(list(tpl.operations)), library)
    for ref, expected in tpl.expected_pin_names.items():
        comp = doc.component(ref)
        symbol = library.resolve(comp.part_id).symbol
        for number, names in expected.items():
            pin = symbol.pin(number)
            if pin is None or pin.name not in names:
                actual = pin.name if pin else "missing"
                raise TemplateError(
                    f"template {template_id}: {comp.lib_symbol} pin {number} is {actual!r} in the installed "
                    f"KiCad library, template expects one of {list(names)}"
                )
    return doc


def template_summaries() -> list[dict]:
    return [
        {"id": t.id, "name": t.name, "description": t.description, "assumptions": list(t.assumptions)}
        for t in TEMPLATES
    ]
