import type {
  AiMessage,
  AiStatus,
  Artifact,
  Capabilities,
  DesignResponse,
  Job,
  Operation,
  PartDetail,
  PartSummary,
  PcbRender,
  ProjectSummary,
  RevisionInfo,
  SchematicRender,
  TemplateSummary,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; operation_error?: { message: string } };
    if (d.operation_error) return d.operation_error.message;
    if (d.message) return d.message;
    if (Array.isArray(detail)) return detail.map((e) => (e as { msg?: string }).msg ?? String(e)).join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(res.status, messageFrom(detail, `${res.status} ${res.statusText}`), detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  capabilities: () => request<Capabilities>("/api/system/capabilities"),
  projects: () => request<ProjectSummary[]>("/api/projects"),
  createProject: (body: { name: string; description?: string; template_id?: string | null }) =>
    request<ProjectSummary>("/api/projects", json(body)),
  updateProject: (id: string, body: { name?: string; description?: string }) =>
    request<ProjectSummary>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteProject: (id: string, confirm: string) =>
    request<void>(`/api/projects/${id}?confirm=${encodeURIComponent(confirm)}`, { method: "DELETE" }),

  design: (id: string) => request<DesignResponse>(`/api/projects/${id}/design`),
  schematic: (id: string) => request<SchematicRender>(`/api/projects/${id}/render/schematic`),
  pcb: (id: string) => request<PcbRender>(`/api/projects/${id}/render/pcb`),
  applyOperations: (id: string, base_revision_id: string, operations: Operation[], message = "") =>
    request<{ revision: RevisionInfo }>(`/api/projects/${id}/operations`, json({ base_revision_id, operations, message })),
  undo: (id: string) => request<{ revision: RevisionInfo }>(`/api/projects/${id}/undo`, { method: "POST" }),
  redo: (id: string) => request<{ revision: RevisionInfo }>(`/api/projects/${id}/redo`, { method: "POST" }),
  revisions: (id: string) => request<RevisionInfo[]>(`/api/projects/${id}/revisions`),
  restoreRevision: (id: string, revisionId: string) =>
    request<{ revision: RevisionInfo }>(`/api/projects/${id}/revisions/${revisionId}/restore`, { method: "POST" }),

  startJob: (id: string, kind: "validate" | "export") => request<Job>(`/api/projects/${id}/jobs`, json({ kind })),
  jobs: (id: string) => request<Job[]>(`/api/projects/${id}/jobs`),
  job: (jobId: string) => request<Job>(`/api/jobs/${jobId}?include_log=true`),
  artifacts: (id: string, revisionId?: string) =>
    request<Artifact[]>(`/api/projects/${id}/artifacts${revisionId ? `?revision_id=${revisionId}` : ""}`),

  parts: (q?: string) =>
    request<{ parts: PartSummary[]; categories: string[] }>(`/api/library/parts${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  part: (partId: string) => request<PartDetail>(`/api/library/parts/${partId}`),
  templates: () => request<TemplateSummary[]>("/api/templates"),

  aiStatus: () => request<AiStatus>("/api/ai/status"),
  aiMessages: (id: string) => request<AiMessage[]>(`/api/projects/${id}/ai/messages`),
  sendAiMessage: (id: string, content: string) => request<AiMessage>(`/api/projects/${id}/ai/messages`, json({ content })),
  applyProposal: (id: string, messageId: string, confirm_destructive: boolean) =>
    request<{ revision: RevisionInfo }>(`/api/projects/${id}/ai/messages/${messageId}/apply`, json({ confirm_destructive })),
  rejectProposal: (id: string, messageId: string) =>
    request<AiMessage>(`/api/projects/${id}/ai/messages/${messageId}/reject`, { method: "POST" }),
};
