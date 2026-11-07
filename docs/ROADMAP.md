# Roadmap and milestone reports

## Phase 1 — Foundation (this milestone)

### What works

- End-to-end vertical slice: create project (empty or template) → edit through validated
  operations → native KiCad project → KiCad netlist cross-check → KiCad ERC/DRC →
  results shown per revision → Gerber/drill/BOM export → project ZIP download.
- Dashboard (create, open, rename, delete with confirmation), editor workspace with
  schematic, PCB and 3D views, inspector, validation panel, board settings, history,
  AI panel, dark/light themes.
- Interactive schematic editing (place, move, rotate, connect, nets, no-connect, delete)
  and PCB editing (move/rotate footprints, 45° track routing with short guard, vias,
  layers, board outline, net-class rules), undo/redo through immutable revisions.
- KiCad capability detection with honest `unavailable` states; local and Docker runners.
- Claude-based assistant behind a provider interface; validated proposals with
  confirmation for destructive changes.
- PostgreSQL/SQLite persistence, Alembic migrations, local artifact storage, job queue
  (Celery/thread/eager), Docker Compose stack.

### What was tested

| Suite | Environment | Result |
|---|---|---|
| Backend unit + API + KiCad integration (`pytest`) | KiCad 7.0.11 local, SQLite | 49 passed, 1 skipped (ERC negative test: ERC unavailable on 7.0) |
| Same | KiCad 9.0.9 Docker runner, SQLite | 50 passed |
| Same | KiCad 7.0.11 local, PostgreSQL 16 | 48 passed, 1 skipped (before the legal endpoint test was added) |
| `ruff check` | — | clean |
| Frontend `tsc`, `eslint`, `vitest` (12 tests), `next build` | Node 22 | clean / passed |
| Playwright e2e (5 tests: vertical slice, dashboard CRUD, schematic editing + undo/redo, PCB routing, legal notices) | dev servers, KiCad 9 Docker runner | 5 passed |
| `npm audit --omit=dev`, `pip-audit` | after upgrading Next.js to 16.4.5 and pinning certifi | 0 known vulnerabilities |
| Same e2e suite | full Docker Compose stack (Postgres, Redis, Celery worker, KiCad 9 in container) | 4 passed |
| Backend image with Alembic on PostgreSQL + in-container KiCad validation | Docker | passed |

Notes on the build environment: Debian mirrors and `npm ci` were not reachable from
Docker builds in the sandbox used for development, so the images were verified with
equivalent sandbox-only build variants (pip bootstrapped from PyPI; host `node_modules`
reused). The committed Dockerfiles use the standard `apt`/`npm ci` steps.

### Incomplete / not yet verified

- Live Claude conversation (no API key available during development; the provider was
  tested against a mock of the Messages API).
- KiCad 8.x integration run.
- 3D models / GLB export, back-side placement, copper zones, autorouting, free-form
  schematic wires, multi-unit symbols, KiCad file import, authentication.

## Phase 2 — Editing depth (next)

1. **Next concrete step:** import of native KiCad projects (parse `.kicad_sch`/`.kicad_pcb`
   into the design document) so edits made in KiCad can round-trip, with the netlist
   cross-check reused as the import validator.
2. Free-form schematic wires and junctions (stored as geometry, still verified via
   KiCad's netlist).
3. Back-side placement, copper zones (filled by KiCad), DRC marker overlays on the canvas.
4. KiCad GLB export + 3D model libraries in the worker image for model-accurate 3D.
5. Revision diff view (operations and visual).

## Phase 3 — Library and AI

1. Library expansion with an automated symbol↔footprint verification pipeline.
2. Datasheet ingestion with citations; parameterised part selection.
3. AI design planning flow (requirements → clarification → block diagram → proposal),
   evaluated on a fixed task set before release.
4. AI explanations linked to specific ERC/DRC violations with suggested operations.

## Phase 4 — Routing and production

1. Autorouting via Freerouting (Specctra DSN/SES) in an isolated worker.
2. Authentication, organisations, sharing; S3-compatible storage backend.
3. Manufacturing presets (fab capability rule sets), panelisation, assembly outputs.
4. Horizontal scaling of EDA workers with per-job containers.
