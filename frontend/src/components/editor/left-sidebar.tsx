"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpen, Check, ExternalLink, GitCommitVertical, History, Network, Plus, Search, Wrench, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Button, EmptyState, Input, Kbd, SectionTitle, Spinner } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useEditor } from "@/lib/editor-store";
import type { DesignResponse, PartSummary } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { useInvalidateProject } from "./use-project";

const TABS = [
  { id: "library", icon: BookOpen, label: "Library" },
  { id: "nets", icon: Network, label: "Nets" },
  { id: "history", icon: History, label: "History" },
  { id: "tools", icon: Wrench, label: "Tools" },
] as const;

export function LeftSidebar({ pid, design }: { pid: string; design: DesignResponse | undefined }) {
  const { leftTab, setLeftTab } = useEditor();
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-border bg-panel">
      <div className="flex border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setLeftTab(t.id)}
            data-testid={`left-tab-${t.id}`}
            className={cn(
              "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium",
              leftTab === t.id ? "border-b-2 border-accent text-text" : "border-b-2 border-transparent text-faint hover:text-muted",
            )}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>
      <div className="scrollbar-thin flex-1 overflow-y-auto">
        {leftTab === "library" && <LibraryPanel />}
        {leftTab === "nets" && <NetsPanel design={design} />}
        {leftTab === "history" && <HistoryPanel pid={pid} design={design} />}
        {leftTab === "tools" && <ToolsPanel />}
      </div>
    </aside>
  );
}

function LibraryPanel() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const parts = useQuery({ queryKey: ["parts"], queryFn: () => api.parts() });
  const { setSchTool, setView, schTool } = useEditor();
  const filtered = useMemo(() => {
    const toks = q.toLowerCase().split(/\s+/).filter(Boolean);
    return (parts.data?.parts ?? []).filter((p) => toks.every((t) => `${p.name} ${p.id} ${p.category} ${p.description ?? ""} ${p.keywords ?? ""}`.toLowerCase().includes(t)));
  }, [parts.data, q]);
  const grouped = useMemo(() => {
    const m = new Map<string, PartSummary[]>();
    filtered.forEach((p) => m.set(p.category, [...(m.get(p.category) ?? []), p]));
    return [...m.entries()];
  }, [filtered]);

  return (
    <div className="pb-4">
      <div className="p-3 pb-1">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-faint" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search parts…" className="pl-8" data-testid="library-search" />
        </div>
        <p className="mt-2 text-[11px] leading-snug text-faint">
          Curated parts with verified KiCad symbol ↔ footprint pin mapping. Pins and datasheet links are read from the installed KiCad libraries.
        </p>
      </div>
      {parts.isLoading && (
        <div className="flex justify-center p-6">
          <Spinner />
        </div>
      )}
      {grouped.map(([cat, list]) => (
        <div key={cat}>
          <SectionTitle>{cat}</SectionTitle>
          {list.map((p) => (
            <div key={p.id} className="border-b border-border/60 last:border-0">
              <div className="group flex items-center gap-2 px-3 py-1.5 hover:bg-hover">
                <button className="min-w-0 flex-1 text-left" onClick={() => setOpen(open === p.id ? null : p.id)}>
                  <div className="truncate text-[12.5px]">{p.name}</div>
                  <div className="truncate font-mono text-[10.5px] text-faint">{p.lib_symbol}</div>
                </button>
                {p.available ? (
                  <Button
                    size="xs"
                    variant={schTool.kind === "place" && schTool.partId === p.id ? "primary" : "outline"}
                    data-testid={`place-${p.id}`}
                    onClick={() => {
                      setView("schematic");
                      setSchTool({ kind: "place", partId: p.id });
                    }}
                  >
                    <Plus className="h-3 w-3" /> Place
                  </Button>
                ) : (
                  <Badge tone="err">missing</Badge>
                )}
              </div>
              {open === p.id && <PartDetails partId={p.id} summary={p} />}
            </div>
          ))}
        </div>
      ))}
      {parts.data && filtered.length === 0 && <EmptyState title="No matching parts">The milestone-1 library is intentionally small. More parts are added once the end-to-end flow is proven.</EmptyState>}
    </div>
  );
}

function PartDetails({ partId, summary }: { partId: string; summary: PartSummary }) {
  const detail = useQuery({ queryKey: ["part", partId], queryFn: () => api.part(partId) });
  return (
    <div className="bg-panel-2 px-3 py-2 text-[11.5px]">
      <div className="text-muted">{summary.description || "No description in the KiCad library."}</div>
      <div className="mt-1.5 font-mono text-[10.5px] text-faint">{summary.footprint ?? "no footprint (schematic only)"}</div>
      {summary.datasheet && (
        <a href={summary.datasheet} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-accent hover:underline">
          Datasheet <ExternalLink className="h-3 w-3" />
        </a>
      )}
      {summary.notes && <div className="mt-1.5 text-faint">{summary.notes}</div>}
      {detail.data && (
        <table className="mt-2 w-full text-[11px]">
          <thead>
            <tr className="text-left text-faint">
              <th className="font-medium">Pin</th>
              <th className="font-medium">Name</th>
              <th className="font-medium">Type</th>
            </tr>
          </thead>
          <tbody>
            {detail.data.pins.map((pin) => (
              <tr key={pin.number}>
                <td className="font-mono">{pin.number}</td>
                <td className="font-mono">{pin.name === "~" ? "—" : pin.name}</td>
                <td className="text-muted">{pin.electrical_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function NetsPanel({ design }: { design: DesignResponse | undefined }) {
  const { selection, select } = useEditor();
  const nets = design?.design.nets ?? [];
  if (!nets.length) return <EmptyState title="No nets yet">Use the connect tool (W) in the schematic, or ask the assistant, to create connections.</EmptyState>;
  return (
    <div className="py-1">
      <SectionTitle>{nets.length} nets</SectionTitle>
      {nets.map((n) => (
        <button
          key={n.name}
          data-testid={`net-row-${n.name}`}
          onClick={() => select({ kind: "net", name: n.name })}
          className={cn("flex w-full items-center justify-between px-3 py-1.5 text-left hover:bg-hover", selection?.kind === "net" && selection.name === n.name && "bg-accent-soft")}
        >
          <span className="font-mono text-[12px]">{n.name}</span>
          <span className="text-[11px] text-faint">{n.pins.length} pins</span>
        </button>
      ))}
    </div>
  );
}

function HistoryPanel({ pid, design }: { pid: string; design: DesignResponse | undefined }) {
  const revs = useQuery({ queryKey: ["revisions", pid], queryFn: () => api.revisions(pid) });
  const invalidate = useInvalidateProject(pid);
  const notify = useEditor((s) => s.notify);
  const restore = useMutation({
    mutationFn: (id: string) => api.restoreRevision(pid, id),
    onSuccess: (r) => {
      invalidate();
      notify("ok", `Restored as revision #${r.revision.number}`);
    },
  });
  return (
    <div className="py-1">
      <SectionTitle>Revisions (immutable)</SectionTitle>
      {revs.data?.map((r) => (
        <div key={r.id} className={cn("group flex gap-2 px-3 py-1.5", r.id === design?.revision.id && "bg-accent-soft")}>
          <GitCommitVertical className={cn("mt-0.5 h-4 w-4 shrink-0", r.is_head ? "text-accent" : "text-faint")} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[11px] text-muted">#{r.number}</span>
              <Badge tone={r.author === "ai" ? "accent" : "neutral"} className="px-1 py-0 text-[10px]">
                {r.author}
              </Badge>
              {r.is_head && <span className="text-[10px] text-accent">current</span>}
            </div>
            <div className="truncate text-[12px]" title={r.message}>
              {r.message || "—"}
            </div>
            <div className="text-[10.5px] text-faint">{timeAgo(r.created_at)}</div>
          </div>
          {!r.is_head && (
            <Button size="xs" variant="ghost" className="opacity-0 group-hover:opacity-100" loading={restore.isPending && restore.variables === r.id} onClick={() => restore.mutate(r.id)}>
              Restore
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}

const TOOL_MATRIX: { group: string; items: [string, boolean, string?][] }[] = [
  {
    group: "Schematic",
    items: [
      ["Select, move, rotate symbols", true, "R rotates"],
      ["Place curated parts", true],
      ["Connect pins (net labels)", true, "W"],
      ["Assign/disconnect nets, no-connect flags", true],
      ["Free-form wire drawing", false, "planned"],
      ["Hierarchical sheets, buses", false, "planned"],
      ["Multi-unit symbols", false, "planned"],
    ],
  },
  {
    group: "PCB",
    items: [
      ["Move / rotate footprints", true, "R rotates 90°"],
      ["Manual track routing (45°)", true, "X"],
      ["Vias", true],
      ["Board outline & net-class rules", true],
      ["Back-side placement", false, "planned"],
      ["Copper zones / pours", false, "planned"],
      ["Autorouter", false, "planned (external, e.g. Freerouting)"],
    ],
  },
  {
    group: "Validation & output (by KiCad)",
    items: [
      ["Native project generation", true],
      ["Netlist cross-check", true],
      ["ERC / DRC", true, "depends on engine"],
      ["Gerber, drill, BOM, project ZIP", true],
    ],
  },
];

function ToolsPanel() {
  return (
    <div className="pb-4">
      {TOOL_MATRIX.map((g) => (
        <div key={g.group}>
          <SectionTitle>{g.group}</SectionTitle>
          {g.items.map(([label, ok, note]) => (
            <div key={label} className="flex items-start gap-2 px-3 py-1 text-[12px]">
              {ok ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok" /> : <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-faint" />}
              <span className={ok ? "" : "text-faint"}>
                {label}
                {note && <span className="ml-1 text-[11px] text-faint">({note})</span>}
              </span>
            </div>
          ))}
        </div>
      ))}
      <SectionTitle>Shortcuts</SectionTitle>
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 px-3 text-[12px] text-muted">
        <Kbd>Ctrl Z</Kbd> <span>Undo (moves to previous revision)</span>
        <Kbd>Ctrl ⇧ Z</Kbd> <span>Redo</span>
        <Kbd>R</Kbd> <span>Rotate selection</span>
        <Kbd>Del</Kbd> <span>Delete selection</span>
        <Kbd>W</Kbd> <span>Schematic connect tool</span>
        <Kbd>X</Kbd> <span>PCB route tool</span>
        <Kbd>1 2 3</Kbd> <span>Schematic / PCB / 3D</span>
        <Kbd>Esc</Kbd> <span>Cancel tool / clear selection</span>
      </div>
    </div>
  );
}
