"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useQuery } from "@tanstack/react-query";
import { CircuitBoard, Clock, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CreateProjectDialog, DeleteProjectDialog, RenameProjectDialog } from "@/components/dashboard/project-dialogs";
import { EngineStatusPanel } from "@/components/engine-status";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button, EmptyState, Spinner } from "@/components/ui/primitives";
import { ValidationBadge } from "@/components/validation-badge";
import { api } from "@/lib/api";
import type { ProjectSummary } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

export default function DashboardPage() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [createOpen, setCreateOpen] = useState(false);
  const [renaming, setRenaming] = useState<ProjectSummary | null>(null);
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-border bg-panel/90 backdrop-blur">
        <div className="mx-auto flex h-12 max-w-6xl items-center gap-3 px-4">
          <Logo />
          <div className="flex-1" />
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[1fr_300px]">
        <section>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold">Projects</h1>
              <p className="text-xs text-muted">Each project keeps an immutable revision history. Validation status is tracked per revision.</p>
            </div>
            <Button variant="primary" size="md" onClick={() => setCreateOpen(true)} data-testid="new-project">
              <Plus className="h-4 w-4" /> New project
            </Button>
          </div>

          {projects.isLoading && (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          )}
          {projects.error && (
            <div className="rounded-md border border-err/30 bg-err-soft p-4 text-sm text-err">
              Could not load projects: {(projects.error as Error).message}
            </div>
          )}
          {projects.data && projects.data.length === 0 && (
            <div className="rounded-lg border border-dashed border-border-strong bg-panel">
              <EmptyState
                icon={<CircuitBoard className="h-8 w-8" />}
                title="No projects yet"
                action={
                  <Button variant="primary" onClick={() => setCreateOpen(true)}>
                    <Plus className="h-4 w-4" /> Create your first project
                  </Button>
                }
              >
                Start from an empty design or a starter circuit such as an LED indicator, a 3.3 V regulator or an NE555 blinker. Every circuit is turned into a
                native KiCad project and checked by KiCad.
              </EmptyState>
            </div>
          )}
          {projects.data && projects.data.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2" data-testid="project-list">
              {projects.data.map((p) => (
                <ProjectCard key={p.id} project={p} onRename={() => setRenaming(p)} onDelete={() => setDeleting(p)} />
              ))}
            </div>
          )}
        </section>

        <aside className="grid h-fit gap-4">
          <div className="rounded-lg border border-border bg-panel p-4">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-faint">EDA engine</div>
            <EngineStatusPanel />
          </div>
          <div className="rounded-lg border border-border bg-panel p-4 text-xs text-muted">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-faint">Validation levels</div>
            <ol className="grid gap-2">
              <li>
                <ValidationBadge level="preview" /> <span className="ml-1">rendered, unchecked</span>
              </li>
              <li>
                <ValidationBadge level="structural" /> <span className="ml-1">KiCad project + netlist verified</span>
              </li>
              <li>
                <ValidationBadge level="rules_passed" /> <span className="ml-1">no ERC/DRC errors</span>
              </li>
              <li>
                <ValidationBadge level="verified" /> <span className="ml-1">human sign-off only</span>
              </li>
            </ol>
          </div>
        </aside>
      </main>

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
      {renaming && <RenameProjectDialog key={renaming.id} project={renaming} onClose={() => setRenaming(null)} />}
      {deleting && <DeleteProjectDialog key={deleting.id} project={deleting} onClose={() => setDeleting(null)} />}
    </div>
  );
}

function ProjectCard({ project, onRename, onDelete }: { project: ProjectSummary; onRename: () => void; onDelete: () => void }) {
  return (
    <div className="group relative rounded-lg border border-border bg-panel transition-colors hover:border-border-strong" data-testid="project-card">
      <Link href={`/projects/${project.id}`} className="block p-4">
        <div className="mb-1 flex items-start justify-between gap-2 pr-6">
          <div className="truncate text-sm font-semibold">{project.name}</div>
        </div>
        <div className="mb-3 line-clamp-2 min-h-[2.4em] text-xs text-muted">{project.description || "No description"}</div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-faint">
          <ValidationBadge level={project.validation_level} />
          <span>{project.component_count} components</span>
          <span>· rev {project.head_revision_number}</span>
          <span className="ml-auto inline-flex items-center gap-1">
            <Clock className="h-3 w-3" /> {timeAgo(project.updated_at)}
          </span>
        </div>
      </Link>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button className="absolute right-2 top-2 rounded p-1 text-faint hover:bg-hover hover:text-text" aria-label="Project actions" data-testid="project-menu">
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" className="z-50 min-w-36 rounded-md border border-border bg-panel p-1 text-[13px] shadow-lg">
            <DropdownMenu.Item onSelect={onRename} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 outline-none data-[highlighted]:bg-hover">
              <Pencil className="h-3.5 w-3.5" /> Rename
            </DropdownMenu.Item>
            <DropdownMenu.Item onSelect={onDelete} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-err outline-none data-[highlighted]:bg-err-soft" data-testid="project-delete">
              <Trash2 className="h-3.5 w-3.5" /> Delete…
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
    </div>
  );
}
