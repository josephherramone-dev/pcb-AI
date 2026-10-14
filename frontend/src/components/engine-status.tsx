"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Check, Cpu, X } from "lucide-react";
import { Spinner, Tip } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const FEATURE_LABELS: [string, string][] = [
  ["pcb_generation", "PCB generation"],
  ["schematic_netlist", "Netlist"],
  ["erc", "ERC"],
  ["drc", "DRC"],
  ["schematic_parity", "Sch/PCB parity"],
  ["gerbers", "Gerbers"],
  ["drill", "Drill"],
  ["glb", "3D GLB"],
];

export function useCapabilities() {
  return useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities, staleTime: 60_000 });
}

export function EngineStatusPanel() {
  const caps = useCapabilities();
  if (caps.isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted">
        <Spinner /> Detecting EDA engine…
      </div>
    );
  }
  if (caps.error || !caps.data) return <div className="text-xs text-err">Backend not reachable. Is the API running on port 8000?</div>;
  const { eda, ai } = caps.data;
  return (
    <div className="grid gap-3 text-xs">
      <div className="flex items-center gap-2">
        <Cpu className="h-4 w-4 text-faint" />
        <span className="font-medium">{eda.kicad_version ? `KiCad ${eda.kicad_version}` : "KiCad not available"}</span>
        <span className="text-faint">· {eda.runner.mode} runner</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {FEATURE_LABELS.map(([key, label]) => {
          const f = eda.features[key];
          if (!f) return null;
          return (
            <Tip key={key} content={f.available ? `Available via ${f.method}` : f.reason}>
              <span
                data-testid={`feature-${key}`}
                data-available={f.available}
                className={cn(
                  "inline-flex items-center gap-1 rounded border px-1.5 py-0.5",
                  f.available ? "border-ok/30 bg-ok-soft text-ok" : "border-border bg-info-soft text-faint line-through decoration-faint/60",
                )}
              >
                {f.available ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                {label}
              </span>
            </Tip>
          );
        })}
      </div>
      <div className="flex items-center gap-2">
        <Bot className="h-4 w-4 text-faint" />
        <span className={ai.configured ? "text-text" : "text-muted"}>{ai.configured ? `AI: ${ai.model}` : ai.message}</span>
      </div>
    </div>
  );
}
