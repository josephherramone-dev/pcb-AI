"""Report which pcbnew Python features the installed KiCad offers (capability detection)."""

import json

try:
    import pcbnew

    print(json.dumps({
        "pcbnew": True,
        "version": pcbnew.Version(),
        "write_drc_report": hasattr(pcbnew, "WriteDRCReport"),
        "footprint_load": hasattr(pcbnew, "FootprintLoad"),
    }))
except Exception as e:  # noqa: BLE001 - report any import failure
    print(json.dumps({"pcbnew": False, "error": f"{type(e).__name__}: {e}"}))
