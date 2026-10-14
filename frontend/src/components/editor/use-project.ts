"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useEditor } from "@/lib/editor-store";
import type { DesignResponse, Operation } from "@/lib/types";

export function useDesign(pid: string) {
  return useQuery({ queryKey: ["design", pid], queryFn: () => api.design(pid) });
}

export function useSchematic(pid: string, revisionId: string | undefined) {
  return useQuery({
    queryKey: ["schematic", pid, revisionId],
    queryFn: () => api.schematic(pid),
    enabled: !!revisionId,
    placeholderData: (prev) => prev,
  });
}

export function usePcb(pid: string, revisionId: string | undefined) {
  return useQuery({
    queryKey: ["pcb", pid, revisionId],
    queryFn: () => api.pcb(pid),
    enabled: !!revisionId,
    placeholderData: (prev) => prev,
  });
}

export function useInvalidateProject(pid: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["design", pid] });
    qc.invalidateQueries({ queryKey: ["revisions", pid] });
    qc.invalidateQueries({ queryKey: ["artifacts", pid] });
    qc.invalidateQueries({ queryKey: ["projects"] });
  };
}

/** Apply validated operations to the head revision (optimistic concurrency on the base revision). */
export function useApplyOps(pid: string) {
  const qc = useQueryClient();
  const invalidate = useInvalidateProject(pid);
  const notify = useEditor((s) => s.notify);
  return useMutation({
    mutationFn: async ({ ops, message }: { ops: Operation[]; message?: string }) => {
      const design = await qc.ensureQueryData({ queryKey: ["design", pid], queryFn: () => api.design(pid) });
      return api.applyOperations(pid, design.revision.id, ops, message ?? "");
    },
    onSuccess: (res) => {
      // Record the new head immediately so a quick follow-up edit uses the right base revision.
      qc.setQueryData<DesignResponse>(["design", pid], (old) => (old ? { ...old, revision: res.revision } : old));
      invalidate();
    },
    onError: (e) => {
      const err = e as ApiError;
      notify("error", err.status === 409 ? `${err.message}` : `Rejected: ${err.message}`);
      if (err.status === 409) invalidate();
    },
  });
}

export function useJobs(pid: string) {
  const qc = useQueryClient();
  const invalidate = useInvalidateProject(pid);
  return useQuery({
    queryKey: ["jobs", pid],
    queryFn: async () => {
      const prev = qc.getQueryData<Awaited<ReturnType<typeof api.jobs>>>(["jobs", pid]);
      const jobs = await api.jobs(pid);
      // When a job finishes, refresh validation status and artifacts.
      if (prev?.some((p) => (p.status === "queued" || p.status === "running") && jobs.find((j) => j.id === p.id && (j.status === "succeeded" || j.status === "failed")))) {
        invalidate();
      }
      return jobs;
    },
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === "queued" || j.status === "running") ? 1000 : false),
  });
}

export function useStartJob(pid: string) {
  const qc = useQueryClient();
  const notify = useEditor((s) => s.notify);
  return useMutation({
    mutationFn: (kind: "validate" | "export") => api.startJob(pid, kind),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs", pid] }),
    onError: (e) => notify("error", (e as Error).message),
  });
}
