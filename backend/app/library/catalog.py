"""Curated catalog of parts supported for placement in milestone 1.

Each entry pairs an official KiCad symbol with an official KiCad footprint. Pin
numbers, pin names, descriptions and datasheet links are *not* stored here:
they are read at runtime from the KiCad library files so they cannot drift from
what KiCad will actually use. ``tests/test_library.py`` verifies that every
symbol pin maps onto a pad of the paired footprint.

``notes`` contains integration remarks written by the platform maintainers, not
component specifications. Electrical specifications must come from the
manufacturer datasheet linked by the KiCad library.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogPart:
    id: str
    name: str
    category: str
    lib_symbol: str
    footprint: str | None
    ref_prefix: str
    default_value: str
    value_editable: bool = True
    in_bom: bool = True
    on_board: bool = True
    notes: str = ""


CATALOG: tuple[CatalogPart, ...] = (
    CatalogPart(
        id="resistor_0805", name="Resistor (0805 SMD)", category="Passives",
        lib_symbol="Device:R", footprint="Resistor_SMD:R_0805_2012Metric",
        ref_prefix="R", default_value="10k",
        notes="Generic resistor. Value, tolerance and power rating must be chosen for the application.",
    ),
    CatalogPart(
        id="capacitor_0805", name="Capacitor (0805 SMD, non-polarized)", category="Passives",
        lib_symbol="Device:C", footprint="Capacitor_SMD:C_0805_2012Metric",
        ref_prefix="C", default_value="100n",
        notes="Generic ceramic capacitor footprint. Voltage rating and dielectric are not modelled.",
    ),
    CatalogPart(
        id="capacitor_polarized_radial", name="Capacitor, polarized (radial THT, D5.0mm)", category="Passives",
        lib_symbol="Device:C_Polarized", footprint="Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
        ref_prefix="C", default_value="10u",
        notes="Pin 1 is the positive terminal in the KiCad symbol.",
    ),
    CatalogPart(
        id="led_0805", name="LED (0805 SMD)", category="Optoelectronics",
        lib_symbol="Device:LED", footprint="LED_SMD:LED_0805_2012Metric",
        ref_prefix="D", default_value="LED",
        notes="KiCad symbol pin 1 = K (cathode), pin 2 = A (anode).",
    ),
    CatalogPart(
        id="diode_sod123", name="Diode (SOD-123)", category="Discretes",
        lib_symbol="Device:D", footprint="Diode_SMD:D_SOD-123",
        ref_prefix="D", default_value="D",
        notes="Generic diode symbol. Set the value to the actual part number.",
    ),
    CatalogPart(
        id="nmos_2n7002", name="2N7002 N-channel MOSFET (SOT-23)", category="Discretes",
        lib_symbol="Transistor_FET:2N7002", footprint="Package_TO_SOT_SMD:SOT-23",
        ref_prefix="Q", default_value="2N7002", value_editable=False,
    ),
    CatalogPart(
        id="ne555_dip8", name="NE555 timer (DIP-8)", category="ICs",
        lib_symbol="Timer:NE555P", footprint="Package_DIP:DIP-8_W7.62mm",
        ref_prefix="U", default_value="NE555P", value_editable=False,
    ),
    CatalogPart(
        id="ams1117_3v3", name="AMS1117-3.3 LDO regulator (SOT-223)", category="Power",
        lib_symbol="Regulator_Linear:AMS1117-3.3", footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        ref_prefix="U", default_value="AMS1117-3.3", value_editable=False,
        notes="Check input/output capacitor requirements in the manufacturer datasheet.",
    ),
    CatalogPart(
        id="push_button_6mm", name="Push button (6mm THT)", category="Electromechanical",
        lib_symbol="Switch:SW_Push", footprint="Button_Switch_THT:SW_PUSH_6mm",
        ref_prefix="SW", default_value="SW_Push",
    ),
    CatalogPart(
        id="header_1x02", name="Pin header 1x02 (2.54mm)", category="Connectors",
        lib_symbol="Connector_Generic:Conn_01x02",
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
        ref_prefix="J", default_value="Conn_01x02",
    ),
    CatalogPart(
        id="header_1x03", name="Pin header 1x03 (2.54mm)", category="Connectors",
        lib_symbol="Connector_Generic:Conn_01x03",
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
        ref_prefix="J", default_value="Conn_01x03",
    ),
    CatalogPart(
        id="header_1x04", name="Pin header 1x04 (2.54mm)", category="Connectors",
        lib_symbol="Connector_Generic:Conn_01x04",
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        ref_prefix="J", default_value="Conn_01x04",
    ),
    CatalogPart(
        id="pwr_flag", name="Power flag (ERC marker)", category="Schematic markers",
        lib_symbol="power:PWR_FLAG", footprint=None,
        ref_prefix="#FLG", default_value="PWR_FLAG", value_editable=False,
        in_bom=False, on_board=False,
        notes=(
            "Virtual symbol: tells KiCad ERC that a net is driven by a power source "
            "(e.g. an input connector). It has no footprint and is not placed on the PCB."
        ),
    ),
)

_BY_ID = {p.id: p for p in CATALOG}


def get_part(part_id: str) -> CatalogPart | None:
    return _BY_ID.get(part_id)


def all_parts() -> tuple[CatalogPart, ...]:
    return CATALOG
