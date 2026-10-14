"""Run KiCad's DRC through the pcbnew Python API (used when kicad-cli has no ``pcb drc``, i.e. KiCad 7).

    <kicad-python> drc_pcbnew.py <board.kicad_pcb> <report.rpt>

Writes KiCad's native text DRC report. The backend parses it.
"""

import sys

import pcbnew


def main(board_path, report_path):
    board = pcbnew.LoadBoard(board_path)
    ok = pcbnew.WriteDRCReport(board, report_path, pcbnew.EDA_UNITS_MILLIMETRES, True)
    if not ok:
        raise SystemExit("WriteDRCReport returned False")
    print(pcbnew.Version())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
