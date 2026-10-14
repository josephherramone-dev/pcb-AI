# PCB AI — AI-native PCB design platform (milestone 1: foundation)

A browser-based PCB design workspace with an AI assistant, built on **KiCad** as the
EDA engine. Circuits are edited through typed, validated operations; every revision can
be turned into a **native KiCad project**, cross-checked by KiCad's own netlist export,
run through **KiCad ERC/DRC**, exported to Gerbers/drill/BOM and downloaded.

> Status: milestone 1 (foundation + one end-to-end vertical slice). It is not yet a
> production EDA tool. See [What works](#what-works-milestone-1) and
> [Known limitations](#known-limitations).

![Validation panel showing real KiCad results](docs/screenshots/validation.png)

## Contents

- [Quick start (Docker)](#quick-start-docker)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Validation levels](#validation-levels)
- [What works (milestone 1)](#what-works-milestone-1)
- [Testing](#testing)
- [Known limitations](#known-limitations)
- [Further documentation](#further-documentation)

## Quick start (Docker)

Requirements: Docker with Compose v2.24+.

```bash
cp .env.example .env          # optionally set ANTHROPIC_API_KEY
docker compose up --build
```

- Web app: <http://localhost:3000>
- API docs (OpenAPI): <http://localhost:8000/docs>

The Compose stack runs PostgreSQL, Redis, the FastAPI **api**, a Celery **worker** that
executes KiCad jobs, and the Next.js **frontend**. The backend image is based on the
official `kicad/kicad:9.0` image, so ERC, DRC, schematic/PCB parity checks and GLB
export are available.

Try it: **New project → NE555 astable LED blinker → Create**, then **Validate**. You will
see KiCad's real results: the project and netlist checks pass, ERC passes, and DRC fails
with unconnected items because the board is not routed yet. Route the tracks in the PCB
view (or start with the LED template, which is small) and validate again.

## Local development

### Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Python | 3.11+ (3.12 used) | backend |
| Node.js | 22.x | frontend |
| KiCad | 7.0+ (9.0 recommended) | `kicad-cli` + KiCad's Python (`pcbnew`) |
| PostgreSQL | 16 | optional for dev (SQLite works) |
| Redis | 7 | only with `JOB_BACKEND=celery` |

KiCad options:

- **Native install** (e.g. `apt install kicad` gives 7.0 on Ubuntu 24.04; the KiCad PPA
  or the official installers give 9.0). Set `KICAD_PYTHON` to an interpreter that can
  `import pcbnew` (on Ubuntu 24.04: `python3.12`).
- **Docker runner**: set `KICAD_EXEC_MODE=docker`; every EDA command then runs in a
  fresh, network-less `kicad/kicad:9.0` container. Point `KICAD_SYMBOL_DIR` /
  `KICAD_FOOTPRINT_DIR` at KiCad 9 library copies so previews match the engine:

  ```bash
  mkdir -p backend/data/kicad9-libs && cid=$(docker create kicad/kicad:9.0)
  docker cp $cid:/usr/share/kicad/symbols backend/data/kicad9-libs/
  docker cp -L $cid:/usr/share/kicad/footprints backend/data/kicad9-libs/
  docker rm $cid
  ```

### Backend

```bash
cd backend
python3.12 -m venv .venv && . .venv/bin/activate      # or: uv venv -p 3.12
pip install -e ".[dev]"
cp ../.env.example .env                                # edit as needed
uvicorn app.main:app --reload --port 8000
```

By default the backend uses SQLite (`./data/pcbai.db`), local file storage
(`./data/storage`) and an in-process thread pool for jobs, so no other services are
required. With PostgreSQL, run migrations first:

```bash
DATABASE_URL=postgresql+psycopg://pcbai:pcbai@localhost:5432/pcbai AUTO_CREATE_TABLES=false alembic upgrade head
```

With Celery (`JOB_BACKEND=celery`), start a worker:

```bash
celery -A app.jobs.celery_app worker --loglevel=INFO
```

### Frontend

```bash
cd frontend
npm ci
npm run dev        # http://localhost:3000, proxies /api to BACKEND_URL (default http://localhost:8000)
```

## Configuration

All configuration is via environment variables (see [`.env.example`](.env.example)).
Important ones:

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Enables the AI assistant. **Server-side only**; never sent to the browser. |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | Claude model used by the assistant. |
| `ANTHROPIC_EFFORT` | `high` | Reasoning effort (`low`…`max`). |
| `ANTHROPIC_ENABLE_FALLBACKS` | `true` | Server-side refusal fallback (beta `server-side-fallback-2026-07-01`). |
| `DATABASE_URL` | SQLite file | `postgresql+psycopg://…` for PostgreSQL. |
| `JOB_BACKEND` | `inline` | `inline` (threads), `eager` (sync, tests), `celery`. |
| `KICAD_EXEC_MODE` | `local` | `local` subprocesses or per-command `docker` containers. |
| `KICAD_PYTHON` | `python3` | Interpreter able to `import pcbnew`. |
| `STORAGE_ROOT` | `./data/storage` | Artifact storage (local backend; S3 interface planned). |

**AI setup:** create an API key in the Anthropic Console, put it in `.env` as
`ANTHROPIC_API_KEY=…`, and restart the backend. The UI's assistant panel and
`GET /api/ai/status` report whether it is configured. Every other feature works
without AI.

## Architecture

```
Browser (Next.js, React, Tailwind)
   │  /api/* (proxied by Next.js; no backend URL or secret in client code)
   ▼
FastAPI API ─── PostgreSQL: projects, immutable revisions, jobs, checks, artifacts, AI messages
   │    │
   │    └── AI orchestrator ── LLMProvider interface ── ClaudeProvider (Anthropic SDK)
   ▼
Job queue (Celery/Redis | thread pool | eager)
   ▼
EDA worker ── EdaEngine interface ── KiCadEngine
                 │  fixed argument vectors, timeouts, per-job working directory
                 ├── kicad-cli (netlist, ERC, DRC, Gerber, drill)
                 └── KiCad Python scripts (pcbnew: build .kicad_pcb, DRC on KiCad 7)
                     as subprocesses or in fresh network-less kicad/kicad containers
```

Key decisions (details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)):

- **Canonical design document** holds design intent using *KiCad identifiers only*
  (library symbol IDs, footprint IDs, pin numbers read from KiCad's libraries). It does
  not replace KiCad's electrical semantics: native files are generated from it and KiCad
  decides validity.
- **Typed, validated operations** are the only way to change a design (UI and AI alike).
  Each applied batch creates an **immutable revision**; undo/redo move the head pointer.
- **KiCad is the judge.** After generating the project, KiCad exports the netlist of the
  generated schematic and it is compared pin-by-pin with the design intent. ERC/DRC
  results are KiCad's own reports, stored per revision with the method and KiCad version
  that produced them.
- **The frontend is engine-independent.** It only consumes REST render models
  (schematic/PCB) and check results.
- **AI never edits directly.** Claude proposes operations, the backend dry-runs them,
  and the user applies or rejects them; destructive changes need explicit confirmation.

Repository layout:

```
backend/
  app/
    api/          REST routes (projects, design ops, render models, jobs, artifacts, library, AI)
    design/       canonical design model + validated operations
    library/      S-expression parser, KiCad symbol/footprint readers, curated catalog
    kicad/        EDA engine interface, KiCad engine, schematic writer, runners, capability detection,
                  report parsers, scripts/ (run inside KiCad's Python)
    render/       schematic & PCB render models for the browser
    services/     projects/revisions, validation status, EDA job pipeline
    jobs/         job queue (eager/thread/Celery)
    ai/           provider interface, Claude provider, orchestrator (tools, proposals)
    templates/    starter circuits (expressed as operations)
    storage/      storage interface + local implementation
  alembic/        database migrations
  tests/          unit, API and KiCad integration tests
frontend/
  src/app/        dashboard and editor routes
  src/components/ editor (canvases, sidebars, AI panel), dashboard, UI primitives
  src/lib/        API client & types, geometry, editor state
  e2e/            Playwright end-to-end tests
docs/             architecture, KiCad integration findings, AI design, roadmap, screenshots
```

## Validation levels

Every revision carries an explicit level, shown in the UI and the API:

| Level | Meaning |
|---|---|
| `preview` | The design renders. Nothing has been checked by KiCad. |
| `structural` | KiCad generated and re-loaded the native project **and** KiCad's netlist of the generated schematic matches the design intent exactly. |
| `rules_passed` | KiCad **ERC and DRC** ran on this revision with **zero errors**. |
| `verified` | Human engineering sign-off. **Never set automatically.** |

If a check cannot run on the configured engine (e.g. ERC on KiCad 7), it is reported as
`unavailable` with the reason, and the higher level cannot be reached.

## What works (milestone 1)

- Project dashboard: create (empty or from template), open, rename, delete (type-to-confirm).
- Editor workspace: schematic, PCB and 3D views; left sidebar (library, nets, history,
  tool support matrix); right sidebar (inspector, validation, board settings); AI panel;
  top bar with save status, undo/redo, view switch, validation badge, validate/export;
  dark and light themes.
- Schematic: symbols drawn from KiCad library data; select, drag, rotate (R), delete
  (with confirmation), place curated parts, connect pins (W) via net labels, assign/rename/
  delete nets, no-connect flags.
- PCB: real footprint geometry from KiCad libraries; move/rotate footprints with grid
  snapping, manual track routing with 45° constraint and short-circuit guard, vias,
  layer visibility, preview ratsnest, board outline and net-class rules.
- 3D: approximate preview (board, pads, tracks, courtyard-based bodies; clearly labelled).
- KiCad integration: capability detection, native `.kicad_sch`/`.kicad_pcb`/`.kicad_pro`
  generation, project library tables, netlist cross-check, ERC, DRC (+ schematic parity on
  KiCad 8+), Gerber + drill + BOM export, project ZIP download.
- AI: Claude provider behind a provider-independent interface; tools for reading the
  design, the part catalog, templates and real validation reports; validated proposals
  with apply/reject and destructive-change confirmation; clear "not configured" state.
- Persistence: PostgreSQL (or SQLite) with Alembic migrations; local artifact storage.
- Jobs: persisted job records with progress/logs; Celery, thread-pool or eager backends.

## Testing

```bash
# backend: unit + API + KiCad integration tests (KiCad tests skip if KiCad is unavailable)
cd backend && KICAD_PYTHON=python3.12 pytest
# against KiCad 9 in Docker
KICAD_EXEC_MODE=docker KICAD_SYMBOL_DIR=$PWD/data/kicad9-libs/symbols \
  KICAD_FOOTPRINT_DIR=$PWD/data/kicad9-libs/footprints pytest
# against PostgreSQL
TEST_DATABASE_URL=postgresql+psycopg://pcbai:pcbai@localhost:5432/pcbai_test pytest
ruff check app tests

# frontend
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
# end-to-end (requires the stack running on :3000 / :8000)
npx playwright test     # set PLAYWRIGHT_CHROMIUM_PATH to use a preinstalled Chromium
```

Results at the end of milestone 1 are recorded in [docs/ROADMAP.md](docs/ROADMAP.md).

## Known limitations

- The part library is intentionally small (13 curated parts, 3 templates). Parts must
  have a verified symbol↔footprint pin mapping; multi-unit symbols are not supported yet.
- Schematic connectivity uses short wire stubs with net labels; free-form wire drawing,
  buses and hierarchical sheets are not implemented.
- PCB: front-side placement only; no copper zones; no autorouter (planned via an external
  router such as Freerouting, not a custom one).
- The 3D view is approximate; KiCad GLB/STEP export with 3D model libraries is planned.
- Native KiCad files are generated *from* the design document. Editing a downloaded
  project in KiCad and re-importing it is not supported yet.
- No authentication / multi-user support yet.
- ERC is not available with KiCad 7 (no headless ERC). Use KiCad 8+ or the Docker runner.

## Screenshots

| Schematic | PCB layout |
|---|---|
| ![Schematic](docs/screenshots/schematic.png) | ![PCB](docs/screenshots/pcb.png) |
| **3D preview (approximate)** | **Dark theme** |
| ![3D](docs/screenshots/3d.png) | ![Dark](docs/screenshots/schematic-dark.png) |

## Further documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — modules, interfaces, data model, decisions
- [docs/KICAD_INTEGRATION.md](docs/KICAD_INTEGRATION.md) — investigated KiCad capabilities (7.0.11 vs 9.0.9)
- [docs/AI.md](docs/AI.md) — assistant design, tools, safety rules
- [docs/ROADMAP.md](docs/ROADMAP.md) — phases, test results, next steps
