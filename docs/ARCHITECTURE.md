# Architecture

## Modules and responsibilities

| # | Module | Location | Responsibility |
|---|---|---|---|
| 1 | Frontend application | `frontend/` | Dashboard, editor (schematic/PCB/3D), AI panel. Talks only to the REST API. |
| 2 | Backend API | `backend/app/api` | REST endpoints, request validation, error mapping. |
| 3 | AI orchestration | `backend/app/ai` | Provider-independent LLM interface, Claude provider, tools, proposals. |
| 4 | Component library | `backend/app/library` | S-expression parser, KiCad symbol/footprint readers, curated catalog. |
| 5 | Schematic project service | `backend/app/kicad/schematic_*`, `render/schematic.py` | Schematic geometry (shared by writer and preview), `.kicad_sch` writer. |
| 6 | PCB project service | `backend/app/kicad/scripts/build_pcb.py`, `render/pcb.py` | Board generation in KiCad's Python, PCB render model and ratsnest. |
| 7 | KiCad integration / EDA workers | `backend/app/kicad`, `backend/app/jobs` | `EdaEngine` interface, `KiCadEngine`, runners, capability detection, job queue. |
| 8 | Validation & reports | `backend/app/kicad/reports.py`, `services/validation.py` | Report parsing, validation levels, design-model checks. |
| 9 | 3D visualisation | `frontend/src/components/editor/board-3d.tsx` | Approximate three.js preview (KiCad GLB export planned). |
| 10 | Persistence & versioning | `backend/app/db`, `services/projects.py`, `storage/` | Projects, immutable revisions, undo/redo, artifacts. |
| 11 | Manufacturing export | `KiCadEngine.export_manufacturing` | Gerbers, drill, BOM, project ZIP. |

## Canonical design document

`backend/app/design/model.py` — a JSON document stored per revision:

```
DesignDocument
  title
  components[]: ref, part_id, lib_symbol ("Device:R"), footprint ("Resistor_SMD:R_0805_2012Metric"),
                value, in_bom, on_board, schematic {x, y, rotation}, pcb {x, y, rotation, side}
  nets[]:       name, pins[] {ref, pin}          # pin = KiCad pin number
  no_connects[]: {ref, pin}
  board:        origin, width, height, copper_layers, rules {clearance, track_width, via_diameter, via_drill}
  tracks[]:     id, net, layer, width, start, end
  vias[]:       id, net, at, diameter, drill
```

What it deliberately does **not** do: define its own symbols, footprints, pin
semantics, rule checks or file formats. Those come from KiCad. The document is the
application's record of *intent*; KiCad's interpretation of the generated files is
checked against it (netlist cross-check) on every validation run.

## Design operations

`backend/app/design/operations.py` defines a discriminated union of operations
(`add_component`, `connect`, `move_footprint`, `add_track`, …). `apply_operations`:

1. validates each operation against the current document and the KiCad libraries
   (part exists, pin exists on the symbol, net name is KiCad-safe, reference unique,
   coordinates in range, a pin belongs to one net only, …);
2. returns a *new* document (the input is never mutated);
3. raises `OperationError(index, op, message)` on the first problem.

Destructive operations (`remove_component`, `delete_net`, `delete_track`, `delete_via`,
`load_template` on a non-empty design) are flagged so UIs and the AI flow can require
confirmation.

## Revisions and concurrency

- Every applied batch creates an immutable `Revision` (author `user` / `ai` / `system`,
  message, operations, full design snapshot).
- `Project.head_revision_id` is the current state. Undo moves the head to the parent;
  redo to the newest child; restore creates a new revision with an old snapshot.
- Writers must send `base_revision_id`; if the head moved, the API returns **409** instead
  of overwriting. Pending AI proposals become `stale` when the head changes.
- Check results and artifacts belong to a revision, so validation status never carries
  over to a modified design.

## Jobs

`backend/app/jobs/queue.py`: jobs are rows in `jobs` (status, progress, log, result).
Backends: `eager` (tests), `inline` thread pool (local dev), `celery` (Compose). The
pipeline (`services/eda_pipeline.py`) creates a fresh working directory, runs the engine
steps, stores `CheckRecord`s and `Artifact`s, and deletes the working directory.

## REST API (summary)

```
GET    /api/system/capabilities            engine features, library, AI and job status
GET    /api/projects | POST /api/projects  list / create (optional template_id)
PATCH  /api/projects/{id}                  rename
DELETE /api/projects/{id}?confirm=<name>   delete (name confirmation required)
GET    /api/projects/{id}/design           head revision, design, validation status, design-model checks
POST   /api/projects/{id}/operations       {base_revision_id, operations[], message}
POST   /api/projects/{id}/operations/preview   dry run
POST   /api/projects/{id}/undo | /redo
GET    /api/projects/{id}/revisions        POST .../revisions/{rid}/restore
GET    /api/projects/{id}/render/schematic | /render/pcb      render models (labelled "preview")
POST   /api/projects/{id}/jobs             {kind: validate|export}
GET    /api/projects/{id}/jobs | /api/jobs/{job_id}
GET    /api/projects/{id}/artifacts        GET /api/artifacts/{id}/download
GET    /api/library/parts[?q=] | /api/library/parts/{id} | /api/templates
GET    /api/ai/status
GET    /api/projects/{id}/ai/messages      POST (send) | .../{mid}/apply | .../{mid}/reject
```

Interactive OpenAPI docs: `http://localhost:8000/docs`.

## Frontend

- Next.js App Router; all editor components are client components.
- `/api/*` is proxied by Next.js rewrites to the backend, so the browser never needs the
  backend URL or any secret.
- Server state via TanStack Query; editor UI state (view, selection, tools, layers) via
  zustand.
- Canvases are SVG in millimetre user units with pan/zoom, grid snapping and hit
  testing. Every edit is sent as a design operation; the canvases re-render from the
  backend's render models, which are derived from the same geometry code as the KiCad
  files.

## Key decisions and trade-offs

| Decision | Rationale | Trade-off |
|---|---|---|
| Generate `.kicad_sch` directly, `.kicad_pcb` via `pcbnew` | No headless API exists for creating schematics; boards are safest built by KiCad itself. | Writer must follow format versions (tested on 7.0 and 9.0). |
| Net labels instead of routed wires in schematics | Deterministic connectivity that KiCad verifies; avoids building a wire router. | Generated schematics are less readable than hand-drawn ones. |
| Netlist cross-check on every validation | Proves the generated file means what the design says. | Extra KiCad invocation per run (~1 s). |
| Design document is the source of truth; native files are generated | Enables validated operations, audit trail, AI proposals. | Edits made in KiCad cannot yet be imported. |
| Curated part catalog | Pin↔pad mapping verified by tests; prevents invented pinouts. | Small library in milestone 1. |
| Per-revision checks | Validation status can never leak to modified designs. | Users must re-run checks after edits (by design). |
| ESLint 9 pinned | `eslint-config-next` plugins do not yet declare ESLint 10 support. | ESLint 9 is end-of-life upstream; revisit when plugins update. |
| TypeScript 5.9 (not 7.x) | Tooling compatibility with Next.js 16. | Upgrade later. |
