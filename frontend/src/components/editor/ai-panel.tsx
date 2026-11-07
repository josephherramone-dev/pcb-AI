"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, Check, HelpCircle, KeyRound, Send, Sparkles, Wrench, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Badge, Button, Dialog, Spinner } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useEditor } from "@/lib/editor-store";
import { describeOperation } from "@/lib/geometry";
import type { AiMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useInvalidateProject } from "./use-project";

const SUGGESTIONS = [
  "Review this design and list anything that looks unconnected or risky.",
  "Explain the latest DRC results and suggest fixes.",
  "Add a 100 nF decoupling capacitor next to U1.",
];

export function AiPanel({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["ai-status"], queryFn: api.aiStatus, staleTime: 60_000 });
  const messages = useQuery({ queryKey: ["ai", pid], queryFn: () => api.aiMessages(pid) });
  const [text, setText] = useState("");
  const [pendingText, setPendingText] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const setAiOpen = useEditor((s) => s.setAiOpen);

  const send = useMutation({
    mutationFn: (content: string) => api.sendAiMessage(pid, content),
    onMutate: (content) => setPendingText(content),
    onSettled: () => {
      setPendingText(null);
      qc.invalidateQueries({ queryKey: ["ai", pid] });
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.data, pendingText]);

  const configured = status.data?.configured;
  const submit = () => {
    const t = text.trim();
    if (!t || send.isPending) return;
    send.mutate(t);
    setText("");
  };

  return (
    <aside className="flex h-full w-[340px] shrink-0 flex-col border-l border-border bg-panel" data-testid="ai-panel">
      <div className="flex h-10 items-center gap-2 border-b border-border px-3">
        <Sparkles className="h-4 w-4 text-accent" />
        <span className="text-[13px] font-semibold">Design assistant</span>
        {status.data?.model && <span className="font-mono text-[10.5px] text-faint">{status.data.model}</span>}
        <div className="flex-1" />
        <Button variant="ghost" size="icon" onClick={() => setAiOpen(false)} aria-label="Close assistant">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div ref={scrollRef} className="scrollbar-thin flex-1 space-y-3 overflow-y-auto p-3">
        {status.data && !configured && (
          <div className="rounded-md border border-warn/40 bg-warn-soft p-3 text-[12px]" data-testid="ai-not-configured">
            <div className="mb-1 flex items-center gap-1.5 font-medium text-warn">
              <KeyRound className="h-3.5 w-3.5" /> Assistant not configured
            </div>
            <p className="text-muted">{status.data.message}</p>
            <ol className="mt-2 list-decimal space-y-0.5 pl-4 text-muted">
              <li>
                Copy <code className="font-mono">.env.example</code> to <code className="font-mono">.env</code>
              </li>
              <li>
                Set <code className="font-mono">ANTHROPIC_API_KEY=…</code> (server-side only)
              </li>
              <li>Restart the backend</li>
            </ol>
            <p className="mt-2 text-faint">All other features work without AI. The key is never sent to the browser.</p>
          </div>
        )}

        {messages.data?.length === 0 && configured && (
          <div className="text-[12px] text-muted">
            <p className="mb-2">
              Describe what you want to build or change. The assistant reads the design, the curated parts (with pinouts from KiCad libraries) and real KiCad check
              results, and <b>proposes</b> changes for you to review. Nothing is applied without your approval.
            </p>
            <div className="grid gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => setText(s)} className="rounded-md border border-border px-2 py-1.5 text-left hover:bg-hover">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.data?.map((m) => <MessageView key={m.id} pid={pid} m={m} />)}
        {pendingText && (
          <>
            <div className="ml-8 rounded-lg bg-accent-soft px-3 py-2 text-[12.5px]">{pendingText}</div>
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <Spinner className="h-3.5 w-3.5" /> Working — reading the design and validating any proposal…
            </div>
          </>
        )}
        {send.error && <div className="rounded-md border border-err/30 bg-err-soft px-2 py-1.5 text-[12px] text-err">{(send.error as ApiError).message}</div>}
      </div>

      <div className="border-t border-border p-2">
        <div className="flex items-end gap-1.5 rounded-md border border-border bg-panel-2 p-1.5 focus-within:border-accent">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={2}
            disabled={!configured}
            placeholder={configured ? "Describe a circuit or a change…" : "Configure ANTHROPIC_API_KEY to enable"}
            className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent px-1 text-[12.5px] outline-none placeholder:text-faint"
            data-testid="ai-input"
          />
          <Button variant="primary" size="icon" onClick={submit} disabled={!configured || !text.trim()} loading={send.isPending} aria-label="Send">
            {!send.isPending && <Send className="h-3.5 w-3.5" />}
          </Button>
        </div>
        <div className="mt-1 px-1 text-[10.5px] text-faint">AI (Claude by Anthropic): your messages, the design and its check results are sent to Anthropic to generate answers. Output can be wrong; proposals are checked against the KiCad libraries, not verified electrically.</div>
      </div>
    </aside>
  );
}

function MessageView({ pid, m }: { pid: string; m: AiMessage }) {
  if (m.role === "user") return <div className="ml-8 whitespace-pre-wrap rounded-lg bg-accent-soft px-3 py-2 text-[12.5px]">{m.content}</div>;
  const tools = m.meta.tool_calls ?? [];
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Bot className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
        <div className="min-w-0 flex-1 whitespace-pre-wrap text-[12.5px] leading-relaxed">{m.content || <span className="text-faint">(no text)</span>}</div>
      </div>
      {tools.length > 0 && (
        <div className="ml-6 flex flex-wrap gap-1">
          {tools.map((t, i) => (
            <span key={i} className={cn("inline-flex items-center gap-1 rounded border px-1 text-[10px]", t.ok ? "border-border text-faint" : "border-err/30 text-err")}>
              <Wrench className="h-2.5 w-2.5" />
              {t.tool}
            </span>
          ))}
        </div>
      )}
      {m.meta.questions && m.meta.questions.length > 0 && (
        <div className="ml-6 rounded-md border border-accent/30 bg-accent-soft/50 p-2 text-[12px]">
          <div className="mb-1 flex items-center gap-1 font-medium text-accent">
            <HelpCircle className="h-3.5 w-3.5" /> Questions
          </div>
          <ul className="list-disc space-y-0.5 pl-4">
            {m.meta.questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </div>
      )}
      {m.proposal && <ProposalCard pid={pid} m={m} />}
    </div>
  );
}

function ProposalCard({ pid, m }: { pid: string; m: AiMessage }) {
  const p = m.proposal!;
  const qc = useQueryClient();
  const invalidate = useInvalidateProject(pid);
  const notify = useEditor((s) => s.notify);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const destructive = p.destructive_operations.length > 0;
  const apply = useMutation({
    mutationFn: (confirm: boolean) => api.applyProposal(pid, m.id, confirm),
    onSuccess: (r) => {
      invalidate();
      notify("ok", `Applied as revision #${r.revision.number}. Run KiCad checks to validate it.`);
    },
    onError: (e) => notify("error", (e as Error).message),
    onSettled: () => qc.invalidateQueries({ queryKey: ["ai", pid] }),
  });
  const reject = useMutation({
    mutationFn: () => api.rejectProposal(pid, m.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["ai", pid] }),
  });
  const statusTone = { pending: "accent", applied: "ok", rejected: "neutral", stale: "warn" } as const;

  return (
    <div className="ml-6 rounded-md border border-border bg-panel-2" data-testid="ai-proposal">
      <div className="flex items-center gap-2 border-b border-border px-2.5 py-1.5">
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium">{p.title}</span>
        {m.proposal_status && <Badge tone={statusTone[m.proposal_status]}>{m.proposal_status}</Badge>}
      </div>
      <div className="space-y-2 px-2.5 py-2 text-[12px]">
        {p.summary && <p className="text-muted">{p.summary}</p>}
        <ol className="list-decimal space-y-0.5 pl-4 font-mono text-[11px]">
          {p.operations.map((op, i) => (
            <li key={i} className={cn(p.destructive_operations.includes(i) && "text-err")}>
              {describeOperation(op)}
            </li>
          ))}
        </ol>
        {p.assumptions.length > 0 && (
          <div>
            <div className="text-[11px] font-medium text-faint">Assumptions</div>
            <ul className="list-disc pl-4 text-muted">
              {p.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
        )}
        {p.preview_warnings.length > 0 && (
          <div className="text-[11px] text-warn">
            {p.preview_warnings.length} design-model warning(s) after applying (e.g. {p.preview_warnings[0].message})
          </div>
        )}
        <div className="text-[10.5px] text-faint">Validated against revision #{p.base_revision_number} and the KiCad libraries · not yet checked by ERC/DRC</div>
      </div>
      {m.proposal_status === "pending" && (
        <div className="flex gap-1.5 border-t border-border px-2.5 py-1.5">
          <Button
            size="sm"
            variant={destructive ? "danger" : "primary"}
            loading={apply.isPending}
            onClick={() => (destructive ? setConfirmOpen(true) : apply.mutate(false))}
            data-testid="apply-proposal"
          >
            {destructive ? <AlertTriangle className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5" />} Apply
          </Button>
          <Button size="sm" variant="ghost" loading={reject.isPending} onClick={() => reject.mutate()}>
            Reject
          </Button>
        </div>
      )}
      {m.proposal_status === "stale" && <div className="border-t border-border px-2.5 py-1.5 text-[11px] text-warn">The design changed since this proposal. Ask again to get an updated proposal.</div>}
      <Dialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Apply destructive changes?"
        description="This proposal removes or replaces existing design content. A new revision is created; the previous one remains available in History."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                apply.mutate(true);
                setConfirmOpen(false);
              }}
            >
              Apply anyway
            </Button>
          </>
        }
      >
        <ul className="list-disc pl-4 text-[12px] text-err">
          {p.destructive_operations.map((i) => (
            <li key={i}>{describeOperation(p.operations[i])}</li>
          ))}
        </ul>
      </Dialog>
    </div>
  );
}
