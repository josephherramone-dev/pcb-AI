import { CheckCircle2, CircleDashed, ShieldCheck, Wrench } from "lucide-react";
import { Badge, Tip } from "@/components/ui/primitives";
import type { ValidationLevel } from "@/lib/types";

export const LEVEL_INFO: Record<ValidationLevel, { short: string; long: string; tone: "neutral" | "accent" | "ok" }> = {
  preview: {
    short: "Preview",
    long: "Rendered preview only. Nothing in this revision has been checked by KiCad.",
    tone: "neutral",
  },
  structural: {
    short: "Structurally valid",
    long: "KiCad generated and re-loaded the native project, and KiCad's netlist matches the design intent. ERC/DRC have not both passed.",
    tone: "accent",
  },
  rules_passed: {
    short: "ERC + DRC passed",
    long: "KiCad ERC and DRC reported no errors for this revision. This is not a full engineering verification.",
    tone: "ok",
  },
  verified: {
    short: "Engineering verified",
    long: "Verified by a human engineer.",
    tone: "ok",
  },
};

const ICONS = { preview: CircleDashed, structural: Wrench, rules_passed: CheckCircle2, verified: ShieldCheck };

export function ValidationBadge({ level, compact = false }: { level: ValidationLevel; compact?: boolean }) {
  const info = LEVEL_INFO[level];
  const Icon = ICONS[level];
  return (
    <Tip content={info.long}>
      <span data-testid="validation-badge" data-level={level}>
        <Badge tone={info.tone}>
          <Icon className="h-3 w-3" />
          {compact ? info.short.split(" ")[0] : info.short}
        </Badge>
      </span>
    </Tip>
  );
}
