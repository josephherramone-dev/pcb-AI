"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Box, CheckCircle2, CircuitBoard, Cloud, CloudOff, Cpu, FileArchive, Loader2, PanelRightClose, PanelRightOpen, Pencil, PlayCircle, Redo2, Sparkles, Trash2, Undo2, Workflow, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DeleteProjectDialog, RenameProjectDialog } from "@/components/dashboard/project-dialogs";
import { useCapabilities } from "@/components/engine-status";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button, EmptyState, Kbd, Spinner, Tip } from "@/components/ui/primitives";
import { ValidationBadge } from "@/components/validation-badge";
import { api } from "@/lib/api";
import { useEditor, type View } from "@/lib/editor-store";
import type { Operation } from "@/lib/types";
import { cn } from "@/lib/utils";
import { AiPanel } from "./ai-panel";
import { Board3D } from "./board-3d";
import { LeftSidebar } from "./left-sidebar";
import { PcbCanvas } from "./pcb-canvas";
import { ConfirmRemove, RightSidebar } from "./right-sidebar";
import { SchematicCanvas } from "./schematic-canvas";
import { useApplyOps, useDesign, useInvalidateProject, useJobs, usePcb, useSchematic, useStartJob } from "./use-project";

const VIEWS: { id: View; label: string; icon: typeof Workflow; key: string }[] = [
  { id: "schematic", label: "Schematic", icon: Workflow, key: "1" },
  { id: "pcb", label: "PCB", icon: CircuitBoard, key: "2" },
  { id: "3d", label: "3D", icon: Box, key: "3" },
];

export function EditorShell({ pid }: { pid: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const design = useDesign(pid);
  const rev = design.data?.revision.id;
  const schematic = useSchematic(pid, rev);
  const pcb = usePcb(pid, rev);
  const jobs = useJobs(pid);
  const applyOps = useApplyOps(pid);
  const startJob = useStartJob(pid);
  const invalidate = useInvalidateProject(pid);
  const editor = useEditor();
  const { view, setView, aiOpen, setAiOpen, selection, notices, dismiss, reset } = editor;
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  useEffect(() => reset, [reset]);

  const undo = useMutation({ mutationFn: () => api.undo(pid), onSuccess: invalidate, onError: (e) => editor.notify("info", (e as Error).message) });
  const redo = useMutation({ mutationFn: () => api.redo(pid), onSuccess: invalidate, onError: (e) => editor.notify("info", (e as Error).message) });

  const apply = (ops: Operation[], message?: string) => applyOps.mutate({ ops, message });

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target?.closest("input, textarea, select, [role=dialog]")) return;
      const mod = e.ctrlKey || e.metaKey;
      const d = design.data?.design;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo.mutate();
        else undo.mutate();
        return;
      }
      if (mod) return;
      const st = useEditor.getState();
      if (e.key === "Escape") {
        st.setSchTool({ kind: "select" });
        st.setPcbTool("select");
        st.select(null);
      } else if (e.key === "1" || e.key === "2" || e.key === "3") {
        setView(VIEWS[Number(e.key) - 1].id);
      } else if (e.key.toLowerCase() === "w" && st.view === "schematic") {
        st.setSchTool({ kind: "wire" });
      } else if (e.key.toLowerCase() === "x" && st.view === "pcb") {
        st.setPcbTool("track");
      } else if (e.key.toLowerCase() === "r" && st.selection?.kind === "component" && d) {
        const c = d.components.find((x) => x.ref === (st.selection as { ref: string }).ref);
        if (!c) return;
        if (st.view === "schematic") apply([{ op: "move_symbol", ref: c.ref, x: c.schematic.x, y: c.schematic.y, rotation: (c.schematic.rotation + 90) % 360 }], `Rotate ${c.ref}`);
        else if (st.view === "pcb" && c.pcb) apply([{ op: "move_footprint", ref: c.ref, x: c.pcb.x, y: c.pcb.y, rotation: (c.pcb.rotation + 90) % 360 }], `Rotate ${c.ref}`);
      } else if (e.key === "Delete" || e.key === "Backspace") {
        const s = st.selection;
        if (s?.kind === "component") setConfirmRemove(s.ref);
        else if (s?.kind === "track") {
          apply([{ op: "delete_track", id: s.id }], "Delete track");
          st.select(null);
        } else if (s?.kind === "via") {
          apply([{ op: "delete_via", id: s.id }], "Delete via");
          st.select(null);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (design.error) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState title="Project could not be loaded" action={<Button onClick={() => router.push("/")}>Back to projects</Button>}>
          {(design.error as Error).message}
        </EmptyState>
      </div>
    );
  }

  const d = design.data;
  const activeJob = jobs.data?.find((j) => j.status === "queued" || j.status === "running");
  const saving = applyOps.isPending || undo.isPending || redo.isPending;

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* ---------------------------------------------------------- top bar */}
      <header className="flex h-11 shrink-0 items-center gap-2 border-b border-border bg-panel px-3">
        <Logo />
        <div className="mx-1 h-5 w-px bg-border" />
        <button className="group flex min-w-0 items-center gap-1.5 rounded px-1.5 py-1 hover:bg-hover" onClick={() => setRenaming(true)} data-testid="project-title">
          <span className="max-w-[220px] truncate text-[13px] font-semibold">{d?.project.name ?? "…"}</span>
          <Pencil className="h-3 w-3 text-faint opacity-0 group-hover:opacity-100" />
        </button>
        {d && <span className="font-mono text-[11px] text-faint">rev #{d.revision.number}</span>}
        <span className="flex items-center gap-1 text-[11px] text-faint" data-testid="save-status">
          {saving ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" /> Saving…
            </>
          ) : applyOps.isError ? (
            <>
              <CloudOff className="h-3 w-3 text-err" /> Last change rejected
            </>
          ) : (
            <>
              <Cloud className="h-3 w-3" /> Saved
            </>
          )}
        </span>
        <div className="mx-1 h-5 w-px bg-border" />
        <Tip content={<span>Undo <Kbd>Ctrl Z</Kbd></span>}>
          <Button variant="ghost" size="icon" disabled={!d?.can_undo || saving} onClick={() => undo.mutate()} aria-label="Undo" data-testid="undo">
            <Undo2 className="h-4 w-4" />
          </Button>
        </Tip>
        <Tip content={<span>Redo <Kbd>Ctrl ⇧ Z</Kbd></span>}>
          <Button variant="ghost" size="icon" disabled={!d?.can_redo || saving} onClick={() => redo.mutate()} aria-label="Redo" data-testid="redo">
            <Redo2 className="h-4 w-4" />
          </Button>
        </Tip>

        <div className="flex-1" />
        <nav className="flex rounded-md border border-border bg-panel-2 p-0.5">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              data-testid={`view-${v.id}`}
              className={cn("flex items-center gap-1.5 rounded px-2.5 py-1 text-[12px] font-medium", view === v.id ? "bg-panel text-text shadow-sm" : "text-muted hover:text-text")}
            >
              <v.icon className="h-3.5 w-3.5" /> {v.label}
            </button>
          ))}
        </nav>
        <div className="flex-1" />

        {d && <ValidationBadge level={d.validation.level} />}
        <Button
          variant="primary"
          onClick={() => {
            startJob.mutate("validate");
            editor.setRightTab("checks");
          }}
          loading={startJob.isPending || activeJob?.kind === "validate"}
          disabled={!!activeJob}
          data-testid="top-validate"
        >
          <PlayCircle className="h-3.5 w-3.5" /> Validate
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            startJob.mutate("export");
            editor.setRightTab("checks");
          }}
          loading={activeJob?.kind === "export"}
          disabled={!!activeJob}
        >
          <FileArchive className="h-3.5 w-3.5" /> Export
        </Button>
        <div className="mx-1 h-5 w-px bg-border" />
        <Tip content="Delete project">
          <Button variant="ghost" size="icon" onClick={() => setDeleting(true)} aria-label="Delete project">
            <Trash2 className="h-4 w-4" />
          </Button>
        </Tip>
        <ThemeToggle />
        <Tip content={aiOpen ? "Hide assistant" : "Show assistant"}>
          <Button variant={aiOpen ? "default" : "ghost"} size="icon" onClick={() => setAiOpen(!aiOpen)} aria-label="Toggle assistant" data-testid="toggle-ai">
            {aiOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
          </Button>
        </Tip>
      </header>

      {/* ---------------------------------------------------------- body */}
      <div className="flex min-h-0 flex-1">
        <LeftSidebar pid={pid} design={d} />
        <main className="relative min-w-0 flex-1">
          {!d ? (
            <div className="flex h-full items-center justify-center">
              <Spinner />
            </div>
          ) : view === "schematic" ? (
            <SchematicCanvas data={schematic.data} loading={schematic.isFetching} onApply={apply} />
          ) : view === "pcb" ? (
            <PcbCanvas data={pcb.data} loading={pcb.isFetching} onApply={apply} />
          ) : (
            <Board3D data={pcb.data} />
          )}
          {d && !d.is_head && <div className="absolute inset-x-0 top-0 bg-warn-soft py-1 text-center text-xs text-warn">Viewing an old revision</div>}
          <div className="pointer-events-none absolute bottom-10 left-1/2 z-20 grid w-[min(560px,90%)] -translate-x-1/2 gap-1.5">
            {notices.map((n) => (
              <div
                key={n.id}
                data-testid="notice"
                className={cn(
                  "pointer-events-auto flex items-start gap-2 rounded-md border px-3 py-2 text-[12.5px] shadow-lg",
                  n.tone === "error" ? "border-err/40 bg-err-soft text-err" : n.tone === "ok" ? "border-ok/40 bg-ok-soft text-ok" : "border-border bg-panel text-text",
                )}
              >
                <span className="flex-1">{n.text}</span>
                <button onClick={() => dismiss(n.id)} aria-label="Dismiss">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </main>
        <RightSidebar pid={pid} design={d} jobs={jobs.data} onApply={apply} onStartJob={(k) => startJob.mutate(k)} startingJob={startJob.isPending} />
        {aiOpen && <AiPanel pid={pid} />}
        {!aiOpen && (
          <button
            onClick={() => setAiOpen(true)}
            className="flex w-8 shrink-0 flex-col items-center gap-2 border-l border-border bg-panel pt-3 text-faint hover:text-accent"
            aria-label="Open assistant"
          >
            <Sparkles className="h-4 w-4" />
            <span className="text-[11px] [writing-mode:vertical-rl]">Assistant</span>
          </button>
        )}
      </div>

      <StatusBar selection={selection} activeJob={activeJob ? `${activeJob.kind}: ${activeJob.progress}` : null} />

      {d && renaming && (
        <RenameProjectDialog
          project={d.project}
          onClose={() => {
            setRenaming(false);
            qc.invalidateQueries({ queryKey: ["design", pid] });
          }}
        />
      )}
      {d && deleting && <DeleteProjectDialog project={d.project} onClose={() => setDeleting(false)} onDeleted={() => router.push("/")} />}
      <ConfirmRemove
        open={!!confirmRemove}
        refdes={confirmRemove ?? ""}
        onClose={() => setConfirmRemove(null)}
        onConfirm={() => {
          apply([{ op: "remove_component", ref: confirmRemove! }], `Remove ${confirmRemove}`);
          editor.select(null);
        }}
      />
    </div>
  );
}

function StatusBar({ selection, activeJob }: { selection: ReturnType<typeof useEditor.getState>["selection"]; activeJob: string | null }) {
  const caps = useCapabilities();
  const cursor = useEditor((s) => s.cursor);
  const eda = caps.data?.eda;
  const erc = eda?.features.erc;
  const drc = eda?.features.drc;
  return (
    <footer className="flex h-6 shrink-0 items-center gap-4 border-t border-border bg-panel px-3 text-[11px] text-faint" data-testid="status-bar">
      <span className="flex items-center gap-1">
        <Cpu className="h-3 w-3" />
        {eda ? (eda.kicad_version ? `KiCad ${eda.kicad_version} · ${eda.runner.mode}` : "KiCad unavailable") : "detecting engine…"}
      </span>
      {erc && (
        <Tip content={erc.available ? erc.method : erc.reason} side="top">
          <span className={erc.available ? "text-ok" : "text-warn"}>ERC {erc.available ? "available" : "unavailable"}</span>
        </Tip>
      )}
      {drc && <span className={drc.available ? "text-ok" : "text-warn"}>DRC {drc.available ? "available" : "unavailable"}</span>}
      {activeJob && (
        <span className="flex items-center gap-1 text-accent">
          <Loader2 className="h-3 w-3 animate-spin" /> {activeJob}
        </span>
      )}
      {!activeJob && caps.data && (
        <span className="flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" /> jobs: {caps.data.jobs.backend}
        </span>
      )}
      <div className="flex-1" />
      {selection && <span>selected: {selection.kind === "component" ? selection.ref : selection.kind === "pin" ? `${selection.ref}.${selection.pin}` : selection.kind === "net" ? `net ${selection.name}` : selection.kind}</span>}
      {cursor && <span className="font-mono">x {cursor.x.toFixed(2)} y {cursor.y.toFixed(2)} mm</span>}
    </footer>
  );
}
