// Types mirroring the backend REST API (backend/app/api). The frontend only
// depends on this contract, never on the EDA engine directly.

export type ValidationLevel = "preview" | "structural" | "rules_passed" | "verified";
export type CheckStatus = "passed" | "failed" | "error" | "unavailable";

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  head_revision_id: string | null;
  head_revision_number: number | null;
  component_count: number;
  validation_level: ValidationLevel;
}

export interface RevisionInfo {
  id: string;
  number: number;
  parent_id: string | null;
  author: "user" | "ai" | "system";
  message: string;
  operation_count: number;
  created_at: string;
  is_head?: boolean;
}

export interface PinRef {
  ref: string;
  pin: string;
}

export interface Point {
  x: number;
  y: number;
}

export interface Component {
  ref: string;
  part_id: string;
  lib_symbol: string;
  footprint: string | null;
  value: string;
  in_bom: boolean;
  on_board: boolean;
  schematic: { x: number; y: number; rotation: 0 | 90 | 180 | 270 };
  pcb: { x: number; y: number; rotation: number; side: "front" } | null;
  properties: Record<string, string>;
}

export interface Net {
  name: string;
  pins: PinRef[];
}

export interface Track {
  id: string;
  net: string;
  layer: "F.Cu" | "B.Cu";
  width: number;
  start: Point;
  end: Point;
}

export interface Via {
  id: string;
  net: string;
  at: Point;
  diameter: number;
  drill: number;
}

export interface DesignRules {
  clearance: number;
  track_width: number;
  via_diameter: number;
  via_drill: number;
}

export interface Board {
  origin: Point;
  width: number;
  height: number;
  copper_layers: number;
  rules: DesignRules;
}

export interface DesignDocument {
  schema_version: number;
  title: string;
  components: Component[];
  nets: Net[];
  no_connects: PinRef[];
  board: Board;
  tracks: Track[];
  vias: Via[];
}

export interface Violation {
  category: string;
  severity: "error" | "warning" | "exclusion";
  type: string;
  description: string;
  items: { description: string; x: number | null; y: number | null }[];
}

export interface CheckResult {
  id: string;
  check: "kicad_project" | "netlist_match" | "erc" | "drc";
  status: CheckStatus;
  message: string;
  method: string | null;
  engine_version: string | null;
  summary: { errors?: number; warnings?: number; total?: number };
  violations: Violation[];
  report_artifact_id: string | null;
  job_id: string | null;
  created_at: string;
}

export interface ValidationStatus {
  revision_id: string;
  level: ValidationLevel;
  label: string;
  levels: Record<ValidationLevel, string>;
  checks: Partial<Record<CheckResult["check"], CheckResult>>;
  next_steps: string[];
}

export interface DesignCheck {
  severity: "error" | "warning";
  code: string;
  ref: string | null;
  message: string;
}

export interface DesignResponse {
  project: ProjectSummary;
  revision: RevisionInfo;
  is_head: boolean;
  can_undo: boolean;
  can_redo: boolean;
  design: DesignDocument;
  validation: ValidationStatus;
  design_checks: DesignCheck[];
}

// ---- schematic render model (library coordinates: Y up) --------------------
export type SymbolGraphic =
  | { kind: "rect"; x1: number; y1: number; x2: number; y2: number; fill: string; stroke_width: number }
  | { kind: "polyline"; points: [number, number][]; fill: string; stroke_width: number }
  | { kind: "circle"; cx: number; cy: number; r: number; fill: string; stroke_width: number }
  | { kind: "arc"; start: [number, number]; mid: [number, number]; end: [number, number]; fill: string; stroke_width: number }
  | { kind: "text"; text: string; x: number; y: number; angle: number };

export interface SymbolPin {
  number: string;
  name: string;
  electrical_type: string;
  x: number;
  y: number;
  angle: number;
  length: number;
  hidden: boolean;
}

export interface SymbolRender {
  lib_id: string;
  graphics: SymbolGraphic[];
  pins: SymbolPin[];
  pin_names_hidden: boolean;
  pin_numbers_hidden: boolean;
  pin_name_offset: number;
  is_power: boolean;
}

export interface SchematicRender {
  revision_id: string;
  kind: "preview";
  page: { width: number; height: number; paper: string };
  symbols: Record<string, SymbolRender>;
  components: {
    ref: string;
    part_id: string;
    lib_symbol: string;
    value: string;
    footprint: string | null;
    x: number;
    y: number;
    rotation: number;
    in_bom: boolean;
    on_board: boolean;
    fields: { name: string; value: string; x: number; y: number; angle: number; hidden: boolean }[];
  }[];
  pins: { ref: string; number: string; name: string; electrical_type: string; x: number; y: number; net: string | null; no_connect: boolean }[];
  wires: { net: string; x1: number; y1: number; x2: number; y2: number }[];
  labels: { net: string; x: number; y: number; angle: number; justify: "left" | "right" }[];
  no_connects: Point[];
  nets: Net[];
}

// ---- PCB render model (KiCad coordinates: Y down) ---------------------------
export interface PadRender {
  number: string;
  type: string;
  shape: string;
  x: number;
  y: number;
  angle: number;
  width: number;
  height: number;
  layers: string[];
  drill: number | null;
  roundrect_ratio: number;
}

export type FootprintGraphic =
  | { kind: "line"; layer: string; width: number; start: [number, number]; end: [number, number] }
  | { kind: "rect"; layer: string; width: number; start: [number, number]; end: [number, number] }
  | { kind: "circle"; layer: string; width: number; center: [number, number]; radius: number }
  | { kind: "arc"; layer: string; width: number; start: [number, number]; mid: [number, number]; end: [number, number] }
  | { kind: "poly"; layer: string; width: number; points: [number, number][] };

export interface FootprintRender {
  lib_id: string;
  description: string;
  pads: PadRender[];
  graphics: FootprintGraphic[];
  courtyard: [number, number, number, number] | null;
  has_3d_model_reference: boolean;
}

export interface PcbRender {
  revision_id: string;
  kind: "preview";
  board: { outline: [number, number][]; origin: Point; width: number; height: number; rules: DesignRules; copper_layers: number };
  footprints: Record<string, FootprintRender>;
  components: { ref: string; value: string; footprint: string; x: number; y: number; rotation: number; side: string; pad_nets: Record<string, string> }[];
  pads: { ref: string; number: string; net: string | null; x: number; y: number; r: number }[];
  tracks: Track[];
  vias: Via[];
  nets: string[];
  ratsnest: { net: string; x1: number; y1: number; x2: number; y2: number }[];
  ratsnest_note: string;
}

export interface PartSummary {
  id: string;
  name: string;
  category: string;
  available: boolean;
  lib_symbol?: string;
  footprint?: string | null;
  ref_prefix?: string;
  default_value?: string;
  value_editable?: boolean;
  description?: string;
  keywords?: string;
  datasheet?: string | null;
  footprint_description?: string | null;
  notes?: string;
  source?: string;
  error?: string;
}

export interface PartDetail extends PartSummary {
  pins: { number: string; name: string; electrical_type: string; unit: number }[];
  pads: string[];
  symbol: SymbolRender;
  footprint_render: FootprintRender | null;
}

export interface TemplateSummary {
  id: string;
  name: string;
  description: string;
  assumptions: string[];
}

export interface Job {
  id: string;
  project_id: string;
  revision_id: string | null;
  kind: "validate" | "export";
  status: "queued" | "running" | "succeeded" | "failed";
  progress: string;
  error: string | null;
  result: { checks?: Record<string, string>; artifacts?: string[]; validation_level?: ValidationLevel };
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  log?: string;
}

export interface Artifact {
  id: string;
  revision_id: string;
  job_id: string | null;
  kind: string;
  filename: string;
  size: number;
  created_at: string;
  download_url: string;
}

export interface Feature {
  available: boolean;
  method: string | null;
  reason: string | null;
}

export interface Capabilities {
  eda: {
    engine: string;
    runner: { mode: string; [k: string]: string };
    kicad_cli_available: boolean;
    kicad_version: string | null;
    pcbnew_version: string | null;
    features: Record<string, Feature>;
    notes: string[];
  };
  library: Record<string, string | boolean>;
  ai: AiStatus;
  jobs: { backend: string };
}

export interface AiStatus {
  provider: string;
  configured: boolean;
  model?: string;
  message: string;
}

export interface Proposal {
  title: string;
  summary: string;
  assumptions: string[];
  operations: Operation[];
  destructive_operations: number[];
  base_revision_id: string;
  base_revision_number: number;
  preview_warnings: DesignCheck[];
}

export interface AiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  proposal: Proposal | null;
  proposal_status: "pending" | "applied" | "rejected" | "stale" | null;
  applied_revision_id: string | null;
  meta: {
    questions?: string[];
    tool_calls?: { tool: string; ok: boolean }[];
    stop_reason?: string;
    model?: string | null;
    error?: string | null;
  };
  created_at: string;
}

// Design operations (validated by the backend; see backend/app/design/operations.py)
export type Operation =
  | { op: "add_component"; part_id: string; ref?: string; value?: string; x: number; y: number; rotation?: number; pcb_x?: number; pcb_y?: number }
  | { op: "remove_component"; ref: string }
  | { op: "set_value"; ref: string; value: string }
  | { op: "move_symbol"; ref: string; x: number; y: number; rotation?: number }
  | { op: "move_footprint"; ref: string; x: number; y: number; rotation?: number }
  | { op: "connect"; net: string; pins: PinRef[] }
  | { op: "disconnect"; pins: PinRef[] }
  | { op: "rename_net"; name: string; new_name: string }
  | { op: "delete_net"; name: string }
  | { op: "set_no_connect"; pin: PinRef; enabled: boolean }
  | { op: "add_track"; net: string; layer: "F.Cu" | "B.Cu"; width?: number; points: Point[] }
  | { op: "delete_track"; id: string }
  | { op: "add_via"; net: string; x: number; y: number }
  | { op: "delete_via"; id: string }
  | { op: "set_board"; width: number; height: number; origin_x?: number; origin_y?: number }
  | { op: "set_rules"; clearance?: number; track_width?: number; via_diameter?: number; via_drill?: number }
  | { op: "set_title"; title: string }
  | { op: "load_template"; template_id: string };
