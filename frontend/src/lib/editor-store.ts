import { create } from "zustand";
import type { PinRef } from "./types";

export type View = "schematic" | "pcb" | "3d";
export type Selection =
  | { kind: "component"; ref: string }
  | { kind: "pin"; ref: string; pin: string }
  | { kind: "net"; name: string }
  | { kind: "track"; id: string }
  | { kind: "via"; id: string }
  | null;

export type SchTool = { kind: "select" } | { kind: "wire" } | { kind: "place"; partId: string };
export type PcbTool = "select" | "track" | "via";

export interface Notice {
  id: number;
  tone: "error" | "info" | "ok";
  text: string;
}

interface EditorState {
  view: View;
  selection: Selection;
  schTool: SchTool;
  pcbTool: PcbTool;
  pcbLayer: "F.Cu" | "B.Cu";
  pcbGrid: number;
  layers: Record<string, boolean>;
  aiOpen: boolean;
  rightTab: "inspector" | "checks" | "board";
  leftTab: "library" | "nets" | "history" | "tools";
  wireStart: PinRef | null;
  focus: { view: View; x: number; y: number; n: number } | null;
  cursor: { x: number; y: number } | null;
  notices: Notice[];
  setView: (v: View) => void;
  select: (s: Selection) => void;
  setSchTool: (t: SchTool) => void;
  setPcbTool: (t: PcbTool) => void;
  setPcbLayer: (l: "F.Cu" | "B.Cu") => void;
  setPcbGrid: (g: number) => void;
  toggleLayer: (l: string) => void;
  setAiOpen: (o: boolean) => void;
  setRightTab: (t: EditorState["rightTab"]) => void;
  setLeftTab: (t: EditorState["leftTab"]) => void;
  setWireStart: (p: PinRef | null) => void;
  focusOn: (view: View, x: number, y: number) => void;
  setCursor: (c: { x: number; y: number } | null) => void;
  notify: (tone: Notice["tone"], text: string) => void;
  dismiss: (id: number) => void;
  reset: () => void;
}

let noticeId = 0;

const initial = {
  view: "schematic" as View,
  selection: null as Selection,
  schTool: { kind: "select" } as SchTool,
  pcbTool: "select" as PcbTool,
  pcbLayer: "F.Cu" as const,
  pcbGrid: 0.25,
  layers: { "F.Cu": true, "B.Cu": true, "F.SilkS": true, "F.Fab": false, "F.CrtYd": true, "Edge.Cuts": true, Ratsnest: true },
  aiOpen: true,
  rightTab: "inspector" as const,
  leftTab: "library" as const,
  wireStart: null,
  focus: null,
  cursor: null,
  notices: [] as Notice[],
};

export const useEditor = create<EditorState>((set) => ({
  ...initial,
  setView: (view) => set({ view, wireStart: null }),
  select: (selection) => set({ selection }),
  setSchTool: (schTool) => set({ schTool, wireStart: null }),
  setPcbTool: (pcbTool) => set({ pcbTool }),
  setPcbLayer: (pcbLayer) => set({ pcbLayer }),
  setPcbGrid: (pcbGrid) => set({ pcbGrid }),
  toggleLayer: (l) => set((s) => ({ layers: { ...s.layers, [l]: !s.layers[l] } })),
  setAiOpen: (aiOpen) => set({ aiOpen }),
  setRightTab: (rightTab) => set({ rightTab }),
  setLeftTab: (leftTab) => set({ leftTab }),
  setWireStart: (wireStart) => set({ wireStart }),
  focusOn: (view, x, y) => set((s) => ({ view, focus: { view, x, y, n: (s.focus?.n ?? 0) + 1 } })),
  setCursor: (cursor) => set({ cursor }),
  notify: (tone, text) =>
    set((s) => ({ notices: [...s.notices.slice(-3), { id: ++noticeId, tone, text }] })),
  dismiss: (id) => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })),
  reset: () => set({ ...initial }),
}));
