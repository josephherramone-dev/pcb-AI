"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleSlash,
  Download,
  ExternalLink,
  FileArchive,
  Loader2,
  PlayCircle,
  Trash2,
  XCircle,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Badge, Button, Dialog, Input, Label, SectionTitle } from "@/components/ui/primitives";
import { LEVEL_INFO } from "@/components/validation-badge";
import { api } from "@/lib/api";
import { useEditor } from "@/lib/editor-store";
import { NET_NAME_RE } from "@/lib/geometry";
import type { CheckResult, DesignResponse, Job, Operation, ValidationLevel } from "@/lib/types";
import { cn, formatBytes } from "@/lib/utils";

type Apply = (ops: Operation[], message?: string) => void;

export function RightSidebar({ pid, design, jobs, onApply, onStartJob, startingJob }: { pid: string; design: DesignResponse | undefined; jobs: Job[] | undefined; onApply: Apply; onStartJob: (k: "validate" | "export") => void; startingJob: boolean }) {
  const { rightTab, setRightTab } = useEditor();
  const errors = Object.values(design?.validation.checks ?? {}).filter((c) => c && c.status !== "passed").length;
  return (
    <aside className="flex h-full w-[300px] shrink-0 flex-col border-l border-border bg-panel">
      <div className="flex border-b border-border text-[12px]">
        {(
          [
            ["inspector", "Inspector"],
            ["checks", "Validation"],
            ["board", "Board"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setRightTab(id)}
            data-testid={`right-tab-${id}`}
            className={cn("flex-1 py-2.5 font-medium", rightTab === id ? "border-b-2 border-accent text-text" : "border-b-2 border-transparent text-faint hover:text-muted")}
          >
            {label}
            {id === "checks" && errors > 0 && <span className="ml-1 rounded bg-err-soft px-1 text-[10px] text-err">{errors}</span>}
          </button>
        ))}
      </div>
      <div className="scrollbar-thin flex-1 overflow-y-auto">
        {!design ? null : rightTab === "inspector" ? (
          <Inspector design={design} onApply={onApply} />
        ) : rightTab === "checks" ? (
          <ChecksPanel pid={pid} design={design} jobs={jobs} onStartJob={onStartJob} startingJob={startingJob} />
        ) : (
          <BoardPanel key={design.revision.id} design={design} onApply={onApply} />
        )}
      </div>
    </aside>
  );
}

// ------------------------------------------------------------------ Inspector
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[88px_1fr] items-center gap-2 px-3 py-1">
      <span className="text-[11.5px] text-faint">{label}</span>
      <div className="min-w-0 text-[12.5px]">{children}</div>
    </div>
  );
}

function NumberInput({ value, onCommit, step = 0.1, testId }: { value: number; onCommit: (v: number) => void; step?: number; testId?: string }) {
  // Draft text while editing; otherwise always show the current design value.
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft === null) return;
    const n = Number(draft);
    if (Number.isFinite(n) && n !== value) onCommit(n);
    setDraft(null);
  };
  return (
    <Input
      type="number"
      step={step}
      value={draft ?? String(value)}
      data-testid={testId}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      className="h-7 px-2 font-mono text-[12px]"
    />
  );
}

function Inspector({ design, onApply }: { design: DesignResponse; onApply: Apply }) {
  const { selection, select } = useEditor();
  const d = design.design;
  if (selection?.kind === "component") {
    const c = d.components.find((x) => x.ref === selection.ref);
    if (c) return <ComponentInspector key={c.ref} design={design} refdes={c.ref} onApply={onApply} />;
  }
  if (selection?.kind === "pin") return <PinInspector key={`${selection.ref}.${selection.pin}`} design={design} refdes={selection.ref} pin={selection.pin} onApply={onApply} />;
  if (selection?.kind === "net") {
    const n = d.nets.find((x) => x.name === selection.name);
    if (n) return <NetInspector key={n.name} design={design} name={n.name} onApply={onApply} />;
  }
  if (selection?.kind === "track") {
    const t = d.tracks.find((x) => x.id === selection.id);
    if (t)
      return (
        <div>
          <SectionTitle>Track</SectionTitle>
          <Field label="Net">
            <button className="font-mono text-accent" onClick={() => select({ kind: "net", name: t.net })}>
              {t.net}
            </button>
          </Field>
          <Field label="Layer">{t.layer}</Field>
          <Field label="Width">{t.width} mm</Field>
          <Field label="Length">{Math.hypot(t.end.x - t.start.x, t.end.y - t.start.y).toFixed(3)} mm</Field>
          <div className="p-3">
            <Button variant="outline" size="sm" onClick={() => onApply([{ op: "delete_track", id: t.id }], "Delete track")}>
              <Trash2 className="h-3.5 w-3.5" /> Delete segment
            </Button>
          </div>
        </div>
      );
  }
  if (selection?.kind === "via") {
    const v = d.vias.find((x) => x.id === selection.id);
    if (v)
      return (
        <div>
          <SectionTitle>Via</SectionTitle>
          <Field label="Net">{v.net}</Field>
          <Field label="Size">
            {v.diameter} / {v.drill} mm
          </Field>
          <div className="p-3">
            <Button variant="outline" size="sm" onClick={() => onApply([{ op: "delete_via", id: v.id }], "Delete via")}>
              <Trash2 className="h-3.5 w-3.5" /> Delete via
            </Button>
          </div>
        </div>
      );
  }
  return <DesignSummary design={design} />;
}

function DesignSummary({ design }: { design: DesignResponse }) {
  const d = design.design;
  const select = useEditor((s) => s.select);
  return (
    <div>
      <SectionTitle>Design</SectionTitle>
      <Field label="Components">{d.components.length}</Field>
      <Field label="Nets">{d.nets.length}</Field>
      <Field label="Tracks / vias">
        {d.tracks.length} / {d.vias.length}
      </Field>
      <Field label="Board">
        {d.board.width} × {d.board.height} mm, {d.board.copper_layers} layers
      </Field>
      <div className="px-3 pt-2 text-[11.5px] text-faint">Select a symbol, pin, label, footprint or track to inspect it.</div>
      <DesignChecks design={design} onPick={(ref) => ref && select({ kind: "component", ref })} />
    </div>
  );
}

function DesignChecks({ design, onPick }: { design: DesignResponse; onPick: (ref: string | null) => void }) {
  const checks = design.design_checks;
  return (
    <div className="mt-2">
      <SectionTitle>
        Design model checks <span className="ml-1 normal-case text-faint">(preliminary, not ERC/DRC)</span>
      </SectionTitle>
      {checks.length === 0 ? (
        <div className="px-3 text-[12px] text-muted">No issues found in the design document.</div>
      ) : (
        checks.slice(0, 50).map((c, i) => (
          <button key={i} onClick={() => onPick(c.ref)} className="flex w-full items-start gap-2 px-3 py-1 text-left text-[12px] hover:bg-hover">
            {c.severity === "error" ? <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-err" /> : <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />}
            <span>{c.message}</span>
          </button>
        ))
      )}
    </div>
  );
}

function ComponentInspector({ design, refdes, onApply }: { design: DesignResponse; refdes: string; onApply: Apply }) {
  const c = design.design.components.find((x) => x.ref === refdes)!;
  const part = useQuery({ queryKey: ["part", c.part_id], queryFn: () => api.part(c.part_id) });
  const [value, setValue] = useState(c.value);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { select } = useEditor();
  const netOf = (pin: string) => design.design.nets.find((n) => n.pins.some((p) => p.ref === c.ref && p.pin === pin))?.name;
  const nc = (pin: string) => design.design.no_connects.some((p) => p.ref === c.ref && p.pin === pin);

  return (
    <div data-testid="component-inspector">
      <SectionTitle>
        Component <span className="ml-1 font-mono normal-case text-text">{c.ref}</span>
      </SectionTitle>
      <Field label="Part">{part.data?.name ?? c.part_id}</Field>
      <Field label="Symbol">
        <span className="font-mono text-[11.5px]">{c.lib_symbol}</span>
      </Field>
      <Field label="Footprint">
        <span className="break-all font-mono text-[11px]">{c.footprint ?? "— (not on board)"}</span>
      </Field>
      <Field label="Value">
        {part.data?.value_editable ? (
          <Input
            value={value}
            data-testid="value-input"
            onChange={(e) => setValue(e.target.value)}
            onBlur={() => value.trim() && value !== c.value && onApply([{ op: "set_value", ref: c.ref, value: value.trim() }], `Set ${c.ref} value`)}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
            className="h-7 px-2"
          />
        ) : (
          <span>{c.value}</span>
        )}
      </Field>
      {part.data?.datasheet && (
        <Field label="Datasheet">
          <a className="inline-flex items-center gap-1 text-accent hover:underline" href={part.data.datasheet} target="_blank" rel="noreferrer">
            Open <ExternalLink className="h-3 w-3" />
          </a>
        </Field>
      )}
      <SectionTitle>Schematic placement</SectionTitle>
      <div className="grid grid-cols-3 gap-1.5 px-3">
        <NumberInput value={c.schematic.x} step={1.27} onCommit={(x) => onApply([{ op: "move_symbol", ref: c.ref, x, y: c.schematic.y }])} />
        <NumberInput value={c.schematic.y} step={1.27} onCommit={(y) => onApply([{ op: "move_symbol", ref: c.ref, x: c.schematic.x, y }])} />
        <select
          className="h-7 rounded-md border border-border bg-panel px-1 text-[12px]"
          value={c.schematic.rotation}
          onChange={(e) => onApply([{ op: "move_symbol", ref: c.ref, x: c.schematic.x, y: c.schematic.y, rotation: Number(e.target.value) }])}
        >
          {[0, 90, 180, 270].map((r) => (
            <option key={r} value={r}>
              {r}°
            </option>
          ))}
        </select>
      </div>
      {c.pcb && (
        <>
          <SectionTitle>PCB placement (front)</SectionTitle>
          <div className="grid grid-cols-3 gap-1.5 px-3">
            <NumberInput value={c.pcb.x} onCommit={(x) => onApply([{ op: "move_footprint", ref: c.ref, x, y: c.pcb!.y }])} />
            <NumberInput value={c.pcb.y} onCommit={(y) => onApply([{ op: "move_footprint", ref: c.ref, x: c.pcb!.x, y }])} />
            <NumberInput value={c.pcb.rotation} step={90} onCommit={(rotation) => onApply([{ op: "move_footprint", ref: c.ref, x: c.pcb!.x, y: c.pcb!.y, rotation }])} />
          </div>
        </>
      )}
      <SectionTitle>Pins</SectionTitle>
      <table className="mx-3 mb-2 w-[calc(100%-1.5rem)] text-[12px]">
        <tbody>
          {part.data?.pins.map((p) => {
            const net = netOf(p.number);
            return (
              <tr key={p.number} className="border-b border-border/50 last:border-0">
                <td className="py-1 pr-2 font-mono text-muted">{p.number}</td>
                <td className="pr-2 font-mono">{p.name === "~" ? "—" : p.name}</td>
                <td className="text-right">
                  {net ? (
                    <button className="font-mono text-accent hover:underline" onClick={() => select({ kind: "net", name: net })}>
                      {net}
                    </button>
                  ) : nc(p.number) ? (
                    <span className="text-faint">no-connect</span>
                  ) : (
                    <button className="text-faint hover:text-text" onClick={() => select({ kind: "pin", ref: c.ref, pin: p.number })}>
                      unconnected
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="p-3">
        <Button variant="outline" size="sm" className="text-err" onClick={() => setConfirmDelete(true)} data-testid="delete-component">
          <Trash2 className="h-3.5 w-3.5" /> Remove {c.ref}
        </Button>
      </div>
      <ConfirmRemove open={confirmDelete} refdes={c.ref} onClose={() => setConfirmDelete(false)} onConfirm={() => onApply([{ op: "remove_component", ref: c.ref }], `Remove ${c.ref}`)} />
    </div>
  );
}

export function ConfirmRemove({ open, refdes, onClose, onConfirm }: { open: boolean; refdes: string; onClose: () => void; onConfirm: () => void }) {
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={`Remove ${refdes}?`}
      description="The component and its pin connections are removed in a new revision. You can undo or restore the previous revision."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger"
            data-testid="confirm-remove"
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            Remove
          </Button>
        </>
      }
    />
  );
}

function PinInspector({ design, refdes, pin, onApply }: { design: DesignResponse; refdes: string; pin: string; onApply: Apply }) {
  const c = design.design.components.find((x) => x.ref === refdes);
  const part = useQuery({ queryKey: ["part", c?.part_id], queryFn: () => api.part(c!.part_id), enabled: !!c });
  const net = design.design.nets.find((n) => n.pins.some((p) => p.ref === refdes && p.pin === pin));
  const isNc = design.design.no_connects.some((p) => p.ref === refdes && p.pin === pin);
  const [target, setTarget] = useState("");
  const info = part.data?.pins.find((p) => p.number === pin);
  const valid = NET_NAME_RE.test(target);
  if (!c) return null;
  return (
    <div data-testid="pin-inspector">
      <SectionTitle>
        Pin <span className="ml-1 font-mono normal-case text-text">{refdes}.{pin}</span>
      </SectionTitle>
      <Field label="Name">{info && info.name !== "~" ? info.name : "—"}</Field>
      <Field label="Type">{info?.electrical_type ?? "—"}</Field>
      <Field label="Net">{net ? <span className="font-mono">{net.name}</span> : isNc ? "no-connect" : <span className="text-faint">unconnected</span>}</Field>
      <div className="grid gap-2 p-3">
        {net ? (
          <Button variant="outline" size="sm" onClick={() => onApply([{ op: "disconnect", pins: [{ ref: refdes, pin }] }], `Disconnect ${refdes}.${pin}`)}>
            Disconnect from {net.name}
          </Button>
        ) : (
          <>
            <Label>Connect to net</Label>
            <div className="flex gap-1.5">
              <Input list="net-names" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="existing or new net" className="h-7" data-testid="net-input" />
              <Button
                size="sm"
                variant="primary"
                disabled={!valid || isNc}
                onClick={() => onApply([{ op: "connect", net: target, pins: [{ ref: refdes, pin }] }], `Connect ${refdes}.${pin}`)}
                data-testid="net-connect"
              >
                Connect
              </Button>
            </div>
            <datalist id="net-names">
              {design.design.nets.map((n) => (
                <option key={n.name} value={n.name} />
              ))}
            </datalist>
            {target && !valid && <div className="text-[11px] text-err">Use 1–40 characters: A–Z a–z 0–9 _ + - .</div>}
            <Button variant="ghost" size="sm" onClick={() => onApply([{ op: "set_no_connect", pin: { ref: refdes, pin }, enabled: !isNc }])}>
              <CircleSlash className="h-3.5 w-3.5" /> {isNc ? "Clear no-connect flag" : "Mark as intentionally unconnected"}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function NetInspector({ design, name, onApply }: { design: DesignResponse; name: string; onApply: Apply }) {
  const net = design.design.nets.find((n) => n.name === name)!;
  const [newName, setNewName] = useState(name);
  const [confirm, setConfirm] = useState(false);
  const select = useEditor((s) => s.select);
  const tracks = design.design.tracks.filter((t) => t.net === name).length;
  return (
    <div data-testid="net-inspector">
      <SectionTitle>
        Net <span className="ml-1 font-mono normal-case text-text">{name}</span>
      </SectionTitle>
      <div className="flex gap-1.5 px-3">
        <Input value={newName} onChange={(e) => setNewName(e.target.value)} className="h-7 font-mono" />
        <Button size="sm" disabled={newName === name || !NET_NAME_RE.test(newName)} onClick={() => onApply([{ op: "rename_net", name, new_name: newName }], `Rename ${name}`)}>
          Rename
        </Button>
      </div>
      <SectionTitle>{net.pins.length} pins · {tracks} track segments</SectionTitle>
      {net.pins.map((p) => (
        <button key={`${p.ref}.${p.pin}`} className="flex w-full justify-between px-3 py-1 text-[12px] hover:bg-hover" onClick={() => select({ kind: "pin", ref: p.ref, pin: p.pin })}>
          <span className="font-mono">
            {p.ref}.{p.pin}
          </span>
        </button>
      ))}
      <div className="p-3">
        <Button variant="outline" size="sm" className="text-err" onClick={() => setConfirm(true)}>
          <Trash2 className="h-3.5 w-3.5" /> Delete net
        </Button>
      </div>
      <Dialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Delete net ${name}?`}
        description="All pins are disconnected and its tracks and vias are removed in a new revision."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                onApply([{ op: "delete_net", name }], `Delete net ${name}`);
                setConfirm(false);
                select(null);
              }}
            >
              Delete
            </Button>
          </>
        }
      />
    </div>
  );
}

// ------------------------------------------------------------------ Checks
const CHECK_LABELS: Record<CheckResult["check"], string> = {
  kicad_project: "Native KiCad project",
  netlist_match: "Netlist cross-check",
  erc: "Electrical rules (ERC)",
  drc: "Design rules (DRC)",
};

const LADDER: ValidationLevel[] = ["preview", "structural", "rules_passed", "verified"];

function StatusIcon({ status }: { status: CheckResult["status"] | "pending" }) {
  if (status === "passed") return <CheckCircle2 className="h-4 w-4 text-ok" />;
  if (status === "failed") return <XCircle className="h-4 w-4 text-err" />;
  if (status === "error") return <AlertTriangle className="h-4 w-4 text-err" />;
  if (status === "unavailable") return <CircleSlash className="h-4 w-4 text-faint" />;
  return <span className="h-4 w-4 rounded-full border border-dashed border-border-strong" />;
}

function ChecksPanel({ pid, design, jobs, onStartJob, startingJob }: { pid: string; design: DesignResponse; jobs: Job[] | undefined; onStartJob: (k: "validate" | "export") => void; startingJob: boolean }) {
  const v = design.validation;
  const levelIdx = LADDER.indexOf(v.level);
  const active = jobs?.find((j) => j.status === "queued" || j.status === "running");
  const lastFailed = jobs?.[0]?.status === "failed" ? jobs[0] : null;
  const artifacts = useQuery({ queryKey: ["artifacts", pid, design.revision.id], queryFn: () => api.artifacts(pid, design.revision.id) });

  return (
    <div data-testid="checks-panel">
      <SectionTitle>Revision #{design.revision.number} status</SectionTitle>
      <ol className="mx-3 grid gap-1">
        {LADDER.map((lvl, i) => (
          <li
            key={lvl}
            className={cn(
              "flex items-start gap-2 rounded-md border px-2 py-1.5 text-[12px]",
              i === levelIdx ? "border-accent/50 bg-accent-soft" : i < levelIdx ? "border-transparent text-muted" : "border-transparent text-faint",
            )}
          >
            <span className={cn("mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold", i <= levelIdx ? "bg-accent text-accent-fg" : "border border-border-strong")}>
              {i < levelIdx ? "✓" : i + 1}
            </span>
            <div>
              <div className="font-medium">{LEVEL_INFO[lvl].short}</div>
              {i === levelIdx && <div className="text-[11px] text-muted">{LEVEL_INFO[lvl].long}</div>}
            </div>
          </li>
        ))}
      </ol>

      <div className="grid grid-cols-2 gap-2 p-3">
        <Button variant="primary" onClick={() => onStartJob("validate")} loading={startingJob || active?.kind === "validate"} disabled={!!active} data-testid="run-validation">
          <PlayCircle className="h-3.5 w-3.5" /> Run KiCad checks
        </Button>
        <Button variant="outline" onClick={() => onStartJob("export")} loading={active?.kind === "export"} disabled={!!active} data-testid="run-export">
          <FileArchive className="h-3.5 w-3.5" /> Export files
        </Button>
      </div>
      {active && (
        <div className="mx-3 mb-2 flex items-center gap-2 rounded-md bg-info-soft px-2 py-1.5 text-[12px] text-muted" data-testid="job-progress">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> {active.kind}: {active.progress}
        </div>
      )}
      {lastFailed && !active && (
        <div className="mx-3 mb-2 rounded-md border border-err/30 bg-err-soft px-2 py-1.5 text-[12px] text-err">Last job failed: {lastFailed.error}</div>
      )}

      <SectionTitle>KiCad checks</SectionTitle>
      {(Object.keys(CHECK_LABELS) as CheckResult["check"][]).map((k) => (
        <CheckCard key={k} name={k} check={v.checks[k]} />
      ))}

      {v.next_steps.length > 0 && (
        <>
          <SectionTitle>What is missing</SectionTitle>
          <ul className="mx-3 mb-2 list-disc space-y-1 pl-4 text-[11.5px] text-muted">
            {v.next_steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </>
      )}

      <SectionTitle>Downloads for this revision</SectionTitle>
      {artifacts.data && artifacts.data.length === 0 && <div className="px-3 pb-2 text-[12px] text-faint">Run checks or export to generate files.</div>}
      {latestArtifacts(artifacts.data).map((a) => (
        <a key={a.id} href={a.download_url} className="flex items-center gap-2 px-3 py-1.5 text-[12px] hover:bg-hover" data-testid={`artifact-${a.kind}`}>
          <Download className="h-3.5 w-3.5 text-faint" />
          <span className="min-w-0 flex-1 truncate">{a.filename}</span>
          <span className="text-[11px] text-faint">{formatBytes(a.size)}</span>
        </a>
      ))}
      <div className="h-4" />
    </div>
  );
}

/** Several jobs can produce the same file kind for a revision; show the newest of each. */
function latestArtifacts<T extends { kind: string; created_at: string }>(list: T[] | undefined): T[] {
  const seen = new Set<string>();
  return [...(list ?? [])]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .filter((a) => (seen.has(a.kind) ? false : (seen.add(a.kind), true)));
}

function CheckCard({ name, check }: { name: CheckResult["check"]; check: CheckResult | undefined }) {
  const [open, setOpen] = useState(false);
  const focusOn = useEditor((s) => s.focusOn);
  const status = check?.status ?? "pending";
  return (
    <div className="mx-3 mb-1.5 rounded-md border border-border" data-testid={`check-${name}`} data-status={status}>
      <button className="flex w-full items-start gap-2 px-2 py-1.5 text-left" onClick={() => setOpen(!open)}>
        <StatusIcon status={status} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-[12.5px] font-medium">
            {CHECK_LABELS[name]}
            {check?.summary?.errors ? <Badge tone="err">{check.summary.errors} err</Badge> : null}
            {check?.summary?.warnings ? <Badge tone="warn">{check.summary.warnings} warn</Badge> : null}
          </div>
          <div className="text-[11.5px] text-muted">{check ? check.message : "Not run on this revision"}</div>
        </div>
        {check && (open ? <ChevronDown className="h-4 w-4 text-faint" /> : <ChevronRight className="h-4 w-4 text-faint" />)}
      </button>
      {open && check && (
        <div className="border-t border-border px-2 py-1.5 text-[11.5px]">
          <div className="text-faint">
            {check.method ?? "—"} {check.engine_version ? `· KiCad ${check.engine_version}` : ""}
          </div>
          {check.report_artifact_id && (
            <a className="mt-1 inline-flex items-center gap-1 text-accent hover:underline" href={`/api/artifacts/${check.report_artifact_id}/download`}>
              <Download className="h-3 w-3" /> Raw KiCad report
            </a>
          )}
          <div className="mt-1 grid gap-1">
            {check.violations.slice(0, 100).map((viol, i) => {
              const loc = viol.items.find((it) => it.x != null && it.y != null);
              return (
                <div key={i} className="rounded bg-panel-2 px-1.5 py-1">
                  <div className="flex items-center gap-1">
                    <span className={cn("font-medium", viol.severity === "error" ? "text-err" : "text-warn")}>{viol.severity}</span>
                    <span className="font-mono text-[10.5px] text-faint">{viol.type}</span>
                  </div>
                  <div>{viol.description}</div>
                  {viol.items.map((it, j) => (
                    <div key={j} className="truncate text-[11px] text-muted" title={it.description}>
                      · {it.description}
                    </div>
                  ))}
                  {loc && name === "drc" && (
                    <button className="mt-0.5 text-[11px] text-accent hover:underline" onClick={() => focusOn("pcb", loc.x!, loc.y!)}>
                      Show on board ({loc.x!.toFixed(2)}, {loc.y!.toFixed(2)})
                    </button>
                  )}
                  {loc && name === "erc" && (
                    <button className="mt-0.5 text-[11px] text-accent hover:underline" onClick={() => focusOn("schematic", loc.x!, loc.y!)}>
                      Show in schematic
                    </button>
                  )}
                </div>
              );
            })}
            {check.violations.length > 100 && <div className="text-faint">… {check.violations.length - 100} more in the raw report</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Board
function BoardPanel({ design, onApply }: { design: DesignResponse; onApply: Apply }) {
  const b = design.design.board;
  const [title, setTitle] = useState(design.design.title);
  return (
    <div>
      <SectionTitle>Title</SectionTitle>
      <div className="flex gap-1.5 px-3">
        <Input value={title} onChange={(e) => setTitle(e.target.value)} className="h-7" />
        <Button size="sm" disabled={title === design.design.title} onClick={() => onApply([{ op: "set_title", title }])}>
          Save
        </Button>
      </div>
      <SectionTitle>Board outline (rectangle, mm)</SectionTitle>
      <Field label="Width">
        <NumberInput value={b.width} step={1} testId="board-width" onCommit={(width) => onApply([{ op: "set_board", width, height: b.height }], "Resize board")} />
      </Field>
      <Field label="Height">
        <NumberInput value={b.height} step={1} onCommit={(height) => onApply([{ op: "set_board", width: b.width, height }], "Resize board")} />
      </Field>
      <Field label="Origin X">
        <NumberInput value={b.origin.x} step={1} onCommit={(origin_x) => onApply([{ op: "set_board", width: b.width, height: b.height, origin_x }])} />
      </Field>
      <Field label="Origin Y">
        <NumberInput value={b.origin.y} step={1} onCommit={(origin_y) => onApply([{ op: "set_board", width: b.width, height: b.height, origin_y }])} />
      </Field>
      <Field label="Copper">{b.copper_layers} layers (F.Cu, B.Cu)</Field>
      <SectionTitle>Default net class rules (mm)</SectionTitle>
      {(["clearance", "track_width", "via_diameter", "via_drill"] as const).map((k) => (
        <Field key={k} label={k.replace("_", " ")}>
          <NumberInput value={b.rules[k]} step={0.05} onCommit={(val) => onApply([{ op: "set_rules", [k]: val }], `Set ${k}`)} />
        </Field>
      ))}
      <p className="px-3 pt-2 text-[11.5px] text-faint">
        These values are written to the KiCad project&apos;s Default net class and used by KiCad DRC. Check your manufacturer&apos;s capabilities before ordering.
      </p>
    </div>
  );
}

