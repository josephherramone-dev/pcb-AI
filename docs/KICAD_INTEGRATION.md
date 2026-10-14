# KiCad integration — investigation and design

This document records what was *actually observed* when probing KiCad, not what was
assumed. All findings were reproduced in the development environment on 2026-10-14.

## Engines investigated

| | Ubuntu 24.04 package | Official Docker image `kicad/kicad:9.0` |
|---|---|---|
| Version | 7.0.11 | 9.0.9 |
| Base OS / Python | Ubuntu 24.04 / `pcbnew` built for Python 3.12 | Debian 12 / Python 3.11 |
| Libraries | symbols, footprints (no 3D models with `--no-install-recommends`) | symbols, footprints, no 3D models |
| Library format version | `20211014`-era (KiCad 7 tokens: bare `hide`) | `20241209` (`(hide yes)`, `Description` property, renamed pins) |

The KiCad 9 PPA (`ppa:kicad/kicad-9.0-releases`) was not reachable from the build
environment; the Docker image was used for KiCad 9.

## `kicad-cli` capabilities (from `--help`)

| Feature | 7.0.11 | 9.0.9 |
|---|---|---|
| `sch export netlist` | yes | yes |
| `sch export svg/pdf` | yes | yes |
| `sch export bom` | no (`python-bom` XML only) | yes |
| **`sch erc`** | **no** | yes (`--format json`, `--severity-all`) |
| **`pcb drc`** | **no** | yes (`--format json`, `--schematic-parity`) |
| `pcb export gerbers/drill/pos/step/svg` | yes | yes |
| `pcb export glb/vrml/stl/ipc2581/odb` | no | yes |
| `pcb render` | no | yes |

## KiCad Python (`pcbnew` SWIG bindings)

Verified headless on both versions:

- `pcbnew.FootprintLoad(lib_path, name)`, `BOARD()`, `NETINFO_ITEM`, `PCB_TRACK`,
  `PCB_VIA`, `PCB_SHAPE`, `SaveBoard`, `LoadBoard` work without a GUI.
- `pcbnew.WriteDRCReport(board, path, units, all_track_errors)` exists on **7.0** and
  runs a real DRC headlessly (text report). Used as the DRC method on KiCad 7.
- There is **no headless ERC** in KiCad 7 (no CLI command, no Python API). ERC is
  reported as `unavailable` on that engine.
- API differences handled in `backend/app/kicad/scripts/build_pcb.py`: `SetWidth` takes a
  layer argument for padstack items in KiCad 9; `FootprintLoad` returns footprints with an
  empty library nickname, so `SetFPID(LIB_ID(lib, name))` is required.
- The KiCad 9 IPC API requires a running KiCad GUI instance and was not used.

## How the platform uses KiCad

1. **Capability detection** (`app/kicad/capabilities.py`) parses `kicad-cli` help output
   and imports `pcbnew` in KiCad's Python. Every feature is reported with the method
   that will be used or the reason it is unavailable. Exposed at
   `GET /api/system/capabilities` and in the UI.
2. **Schematic generation** (`app/kicad/schematic_writer.py`) writes `.kicad_sch`
   S-expressions directly. Symbol definitions are copied from the installed library into
   `lib_symbols` (derived `extends` symbols are flattened). The file dialect follows the
   installed library version (7: `20230121`, 8: `20231120`, 9: `20250114`), because
   embedded symbol definitions use that version's tokens. Connectivity uses short wire
   stubs ending in **local net labels** at each connected pin.
3. **PCB generation** runs `scripts/build_pcb.py` inside KiCad's Python: footprints are
   loaded from the official libraries, nets assigned to pads, outline/tracks/vias added,
   the board saved and **re-loaded** to report what KiCad actually wrote. Net names use
   KiCad's convention for root-sheet local labels (`/NAME`) so that schematic parity
   checks agree.
4. **Project file**: KiCad writes `.kicad_pro`; the backend patches the Default net class
   (clearance, track width, via size). Project-local `fp-lib-table` / `sym-lib-table`
   reference libraries via `${KICADn_FOOTPRINT_DIR}` / `${KICADn_SYMBOL_DIR}`, which
   resolve on standard installations of the same major version. Headless KiCad 7 has no
   first-run configuration, so the local runner defines those variables explicitly.
5. **Netlist cross-check**: `kicad-cli sch export netlist` on the generated schematic;
   parsed and compared pin-by-pin with the design intent (power flags excluded, as KiCad
   excludes them from netlists). Any difference fails the `netlist_match` check.
6. **ERC/DRC**: `kicad-cli sch erc` / `pcb drc --schematic-parity` (JSON) on KiCad 8+,
   `WriteDRCReport` (text) on KiCad 7. Reports are parsed into a common violation format
   and stored with the raw report as a downloadable artifact.
7. **Exports**: Gerbers for F/B copper, paste, silkscreen, mask and Edge.Cuts; Excellon
   drill files; BOM CSV derived from KiCad's netlist; project ZIP.

## Isolation

- Commands are argument vectors built from fixed templates (`app/kicad/engine.py`). File
  arguments are relative paths inside a per-job working directory. Only the scripts in
  `ALLOWED_SCRIPTS` can be executed. No shell is involved and no AI output is ever used
  to build a command.
- **Local runner**: subprocess with timeout, minimal environment, `HOME` inside the job
  directory. In Docker Compose the worker container is the isolation boundary
  (`mem_limit`, `pids_limit`).
- **Docker runner**: each command in a fresh `kicad/kicad:9.0` container with
  `--network none`, memory/CPU/PID limits, `no-new-privileges`, only the job directory
  mounted. Requires access to the Docker daemon (a security-sensitive capability;
  appropriate for single-host deployments or a dedicated EDA host).

## Verified results (KiCad 9.0.9)

| Template | Project | Netlist match | ERC | DRC (unrouted) |
|---|---|---|---|---|
| LED indicator | passed | passed | 0 errors, 0 warnings | fails: unconnected items |
| 3.3 V LDO | passed | passed | 0 errors, 0 warnings | fails: unconnected items |
| NE555 blinker | passed | passed | 0 errors, 0 warnings | fails: 17 unconnected items |
| LDO without PWR_FLAG | passed | passed | **fails: power pin not driven** | — |
| LED indicator, hand-routed | passed | passed | passed | **passed** → `rules_passed` |

The same tests on KiCad 7.0.11 give identical project/netlist/DRC outcomes, with ERC
`unavailable`.

## Open questions / further investigation

- **3D models**: neither environment ships the 3D model libraries (several GB).
  `pcb export glb` works on 9.0 but produces bodies only when models are installed.
- **Round-tripping user edits** made in KiCad back into the platform (parsing
  `.kicad_sch`/`.kicad_pcb` into the design document) is not implemented.
- **Autorouting**: candidate is Freerouting via Specctra DSN/SES export/import
  (`pcbnew.ExportSpecctraDSN` / `ImportSpecctraSES`); needs a Java runtime in the worker.
- **KiCad 8**: not tested directly; capability detection is feature-based, and the
  schematic writer has a KiCad 8 dialect, but an integration run on 8.x is still needed.
- **Library drift**: KiCad 9 renamed some pins (e.g. NE555 `TR` → `TRIG`). Templates
  assert accepted pin names and fail loudly on mismatch.
