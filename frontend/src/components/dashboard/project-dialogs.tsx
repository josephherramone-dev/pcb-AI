"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlus2, LayoutTemplate } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Dialog, Input, Label } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { ProjectSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

export function CreateProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.templates, enabled: open });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api.createProject({ name: name.trim(), description, template_id: template }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onOpenChange(false);
      router.push(`/projects/${p.id}`);
    },
  });
  const selected = templates.data?.find((t) => t.id === template);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New project"
      description="Start from an empty design or from a starter circuit."
      width="max-w-2xl"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()} data-testid="create-project-submit">
            Create project
          </Button>
        </>
      }
    >
      <div className="grid gap-3">
        <div className="grid gap-1.5">
          <Label>Name</Label>
          <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sensor breakout" data-testid="project-name-input" />
        </div>
        <div className="grid gap-1.5">
          <Label>Description</Label>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" />
        </div>
        <div className="grid gap-1.5">
          <Label>Start from</Label>
          <div className="grid grid-cols-2 gap-2">
            <TemplateCard active={template === null} onClick={() => setTemplate(null)} icon={<FilePlus2 className="h-4 w-4" />} title="Empty design" description="Blank schematic and a 50 × 40 mm board." />
            {templates.data?.map((t) => (
              <TemplateCard
                key={t.id}
                active={template === t.id}
                onClick={() => setTemplate(t.id)}
                icon={<LayoutTemplate className="h-4 w-4" />}
                title={t.name}
                description={t.description}
                testId={`template-${t.id}`}
              />
            ))}
          </div>
        </div>
        {selected && (
          <div className="rounded-md border border-warn/30 bg-warn-soft px-3 py-2 text-xs text-text">
            <div className="mb-1 font-medium text-warn">Template assumptions — not a verified design</div>
            <ul className="list-disc space-y-0.5 pl-4 text-muted">
              {selected.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
        )}
        {create.error && <div className="text-xs text-err">{(create.error as ApiError).message}</div>}
      </div>
    </Dialog>
  );
}

function TemplateCard({ active, onClick, icon, title, description, testId }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string; description: string; testId?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={cn(
        "flex gap-2.5 rounded-md border p-2.5 text-left transition-colors",
        active ? "border-accent bg-accent-soft" : "border-border hover:bg-hover",
      )}
    >
      <span className={cn("mt-0.5", active ? "text-accent" : "text-faint")}>{icon}</span>
      <span>
        <span className="block text-[13px] font-medium">{title}</span>
        <span className="block text-xs text-muted">{description}</span>
      </span>
    </button>
  );
}

export function RenameProjectDialog({ project, onClose }: { project: ProjectSummary | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const save = useMutation({
    mutationFn: () => api.updateProject(project!.id, { name: name.trim(), description }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["design", project!.id] });
      onClose();
    },
  });
  return (
    <Dialog
      open={!!project}
      onOpenChange={(o) => !o && onClose()}
      title="Rename project"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!name.trim()} loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid gap-3">
        <div className="grid gap-1.5">
          <Label>Name</Label>
          <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} data-testid="rename-input" />
        </div>
        <div className="grid gap-1.5">
          <Label>Description</Label>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        {save.error && <div className="text-xs text-err">{(save.error as ApiError).message}</div>}
      </div>
    </Dialog>
  );
}

export function DeleteProjectDialog({ project, onClose, onDeleted }: { project: ProjectSummary | null; onClose: () => void; onDeleted?: () => void }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState("");
  const del = useMutation({
    mutationFn: () => api.deleteProject(project!.id, confirm),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      onClose();
      onDeleted?.();
    },
  });
  return (
    <Dialog
      open={!!project}
      onOpenChange={(o) => !o && onClose()}
      title="Delete project"
      description="This permanently deletes the project, all revisions, check results and generated files."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" disabled={confirm !== project?.name} loading={del.isPending} onClick={() => del.mutate()} data-testid="confirm-delete">
            Delete permanently
          </Button>
        </>
      }
    >
      <div className="grid gap-1.5">
        <Label>
          Type <span className="font-mono normal-case text-text">{project?.name}</span> to confirm
        </Label>
        <Input autoFocus value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="delete-confirm-input" />
        {del.error && <div className="text-xs text-err">{(del.error as ApiError).message}</div>}
      </div>
    </Dialog>
  );
}
