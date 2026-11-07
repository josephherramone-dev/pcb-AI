"use client";

import { useQuery } from "@tanstack/react-query";
import { Scale } from "lucide-react";
import { useState } from "react";
import { Dialog, Spinner } from "@/components/ui/primitives";

interface LegalInfo {
  engineering_disclaimer: string;
  ai_disclosure: string;
  kicad_library_notice: string;
  attributions: { name: string; role: string; license: string; url: string }[];
  not_affiliated: string;
}

/** "Legal & notices" link + dialog. Texts come from the backend (/api/legal) so they match exported files. */
export function LegalLink({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const info = useQuery({
    queryKey: ["legal"],
    queryFn: async (): Promise<LegalInfo> => (await fetch("/api/legal")).json(),
    enabled: open,
    staleTime: Infinity,
  });
  return (
    <>
      <button onClick={() => setOpen(true)} className={className ?? "inline-flex items-center gap-1 hover:text-text"} data-testid="legal-link">
        <Scale className="h-3 w-3" /> Legal & notices
      </button>
      <Dialog open={open} onOpenChange={setOpen} title="Legal & notices" width="max-w-2xl">
        {!info.data ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : (
          <div className="scrollbar-thin max-h-[65vh] space-y-4 overflow-y-auto text-[12.5px] leading-relaxed" data-testid="legal-content">
            <section>
              <h3 className="mb-1 font-semibold">No warranty — engineering responsibility</h3>
              <p className="text-muted">{info.data.engineering_disclaimer}</p>
            </section>
            <section>
              <h3 className="mb-1 font-semibold">AI assistant</h3>
              <p className="text-muted">{info.data.ai_disclosure}</p>
            </section>
            <section>
              <h3 className="mb-1 font-semibold">Third-party software and data</h3>
              <table className="w-full text-[12px]">
                <tbody>
                  {info.data.attributions.map((a) => (
                    <tr key={a.name} className="border-b border-border/60 align-top last:border-0">
                      <td className="py-1.5 pr-3 font-medium">
                        <a href={a.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                          {a.name}
                        </a>
                      </td>
                      <td className="py-1.5 pr-3 text-muted">{a.role}</td>
                      <td className="py-1.5 font-mono text-[11px]">{a.license}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-muted">{info.data.kicad_library_notice}</p>
              <p className="mt-2 text-faint">The full list of open-source dependencies and their licenses is in THIRD_PARTY_NOTICES.md in the source repository.</p>
            </section>
            <p className="text-faint">{info.data.not_affiliated}</p>
          </div>
        )}
      </Dialog>
    </>
  );
}
