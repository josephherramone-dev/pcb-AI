"use client";

import { CircleDot, Layers, Maximize, MousePointer2, Route } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Kbd, Spinner, Tip } from "@/components/ui/primitives";
import { arcPath, constrain45, distToSegment, snap } from "@/lib/geometry";
import { useEditor } from "@/lib/editor-store";
import type { FootprintGraphic, Operation, PadRender, PcbRender, Point } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useViewport } from "./use-viewport";

const LAYER_COLORS: Record<string, string> = {
  "F.SilkS": "var(--pcb-silk)",
  "F.CrtYd": "var(--pcb-crtyd)",
  "F.Fab": "var(--pcb-fab)",
  "B.SilkS": "var(--pcb-silk)",
  "B.CrtYd": "var(--pcb-crtyd)",
  "B.Fab": "var(--pcb-fab)",
};

function Pad({ pad, net, highlight, testId }: { pad: PadRender; net: string | undefined; highlight: boolean; testId: string }) {
  const smdBack = pad.type === "smd" && pad.layers.includes("B.Cu") && !pad.layers.includes("F.Cu");
  const color = pad.type === "thru_hole" ? "var(--pcb-pad)" : smdBack ? "var(--pcb-bcu)" : "var(--pcb-fcu)";
  const w = pad.width;
  const h = pad.height;
  let shape;
  if (pad.shape === "circle") shape = <circle r={w / 2} fill={color} />;
  else {
    const rx = pad.shape === "oval" ? Math.min(w, h) / 2 : pad.shape === "roundrect" ? Math.min(w, h) * pad.roundrect_ratio : 0;
    shape = <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={rx} fill={color} />;
  }
  return (
    <g transform={`translate(${pad.x} ${pad.y}) rotate(${-pad.angle})`} opacity={highlight ? 1 : 0.9} data-testid={testId}>
      {shape}
      {highlight && <rect x={-w / 2 - 0.08} y={-h / 2 - 0.08} width={w + 0.16} height={h + 0.16} fill="none" stroke="var(--pcb-select)" strokeWidth={0.08} />}
      {pad.drill ? <circle r={pad.drill / 2} fill="var(--pcb-bg)" /> : null}
      <title>{`Pad ${pad.number}${net ? ` · ${net}` : " · no net"}`}</title>
    </g>
  );
}

function Graphic({ g }: { g: FootprintGraphic }) {
  const stroke = LAYER_COLORS[g.layer] ?? "var(--pcb-fab)";
  const common = { stroke, strokeWidth: Math.max(g.width, 0.05), fill: "none", strokeLinecap: "round" as const };
  switch (g.kind) {
    case "line":
      return <line x1={g.start[0]} y1={g.start[1]} x2={g.end[0]} y2={g.end[1]} {...common} />;
    case "rect":
      return <rect x={Math.min(g.start[0], g.end[0])} y={Math.min(g.start[1], g.end[1])} width={Math.abs(g.end[0] - g.start[0])} height={Math.abs(g.end[1] - g.start[1])} {...common} />;
    case "circle":
      return <circle cx={g.center[0]} cy={g.center[1]} r={g.radius} {...common} />;
    case "arc":
      return <path d={arcPath(g.start, g.mid, g.end)} {...common} />;
    case "poly":
      return <polygon points={g.points.map((p) => p.join(",")).join(" ")} {...common} />;
  }
}

export function PcbCanvas({ data, loading, onApply }: { data: PcbRender | undefined; loading: boolean; onApply: (ops: Operation[], message?: string) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const { vb, toWorld, startPan, movePan, endPan, fit, centerOn } = useViewport(svgRef, { x: 90, y: 70, w: 70, h: 60 });
  const { selection, select, pcbTool, setPcbTool, pcbLayer, setPcbLayer, pcbGrid, layers, toggleLayer, notify, setCursor, focus } = useEditor();
  const [drag, setDrag] = useState<{ ref: string; sx: number; sy: number; dx: number; dy: number; moved: boolean } | null>(null);
  const [route, setRoute] = useState<{ net: string; points: Point[] } | null>(null);
  const [cursorPt, setCursorPt] = useState<Point | null>(null);
  const [showLayers, setShowLayers] = useState(false);
  const fitted = useRef(false);

  const fitBoard = useCallback(() => {
    if (!data) return;
    fit({ x: data.board.origin.x, y: data.board.origin.y, w: data.board.width, h: data.board.height }, 0.12);
  }, [data, fit]);

  useEffect(() => {
    if (data && !fitted.current) {
      fitted.current = true;
      fitBoard();
    }
  }, [data, fitBoard]);

  useEffect(() => {
    if (focus && focus.view === "pcb") centerOn(focus.x, focus.y, 20);
  }, [focus, centerOn]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea")) return;
      if (e.key === "Escape") setRoute(null);
      if (e.key === "Enter" && route) finishRoute(route);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const highlightNet = useMemo(() => {
    if (!data) return null;
    if (route) return route.net;
    if (selection?.kind === "net") return selection.name;
    if (selection?.kind === "track") return data.tracks.find((t) => t.id === selection.id)?.net ?? null;
    if (selection?.kind === "via") return data.vias.find((v) => v.id === selection.id)?.net ?? null;
    return null;
  }, [data, selection, route]);

  const padAt = (p: Point) => data?.pads.find((pad) => Math.hypot(pad.x - p.x, pad.y - p.y) <= Math.max(pad.r, 0.5));
  const trackAt = (p: Point) => data?.tracks.find((t) => distToSegment(p, t.start, t.end) <= Math.max(t.width / 2, 0.3));
  const viaAt = (p: Point) => data?.vias.find((v) => Math.hypot(v.at.x - p.x, v.at.y - p.y) <= v.diameter / 2);

  const snapPt = (p: Point): Point => ({ x: snap(p.x, pcbGrid), y: snap(p.y, pcbGrid) });

  function finishRoute(r: { net: string; points: Point[] }) {
    if (r.points.length >= 2) onApply([{ op: "add_track", net: r.net, layer: pcbLayer, points: r.points }], `Route ${r.net}`);
    setRoute(null);
  }

  const nextRoutePoint = (raw: Point, free: boolean): Point => {
    if (!route) return raw;
    const last = route.points[route.points.length - 1];
    const pad = padAt(raw);
    if (pad) return { x: pad.x, y: pad.y };
    const s = snapPt(raw);
    return free ? s : constrain45(last, s);
  };

  const onDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button === 1) return startPan(e);
    if (e.button !== 0 || !data) return;
    const p = toWorld(e.clientX, e.clientY);

    if (pcbTool === "track") {
      if (!route) {
        const pad = padAt(p);
        const tr = trackAt(p);
        if (pad?.net) setRoute({ net: pad.net, points: [{ x: pad.x, y: pad.y }] });
        else if (tr) setRoute({ net: tr.net, points: [snapPt(p)] });
        else if (pad) notify("info", `Pad ${pad.ref}.${pad.number} has no net. Connect it in the schematic first.`);
        else startPan(e);
        return;
      }
      const pt = nextRoutePoint(p, e.shiftKey);
      const pad = padAt(p);
      if (pad && pad.net && pad.net !== route.net) {
        notify("error", `Pad ${pad.ref}.${pad.number} is on net ${pad.net}; ending a ${route.net} track there would create a short.`);
        return;
      }
      const pts = [...route.points, pt];
      if (pad && pad.net === route.net && pts.length >= 2) finishRoute({ ...route, points: pts });
      else setRoute({ ...route, points: pts });
      return;
    }

    if (pcbTool === "via") {
      const tr = trackAt(p);
      const net = tr?.net ?? (selection?.kind === "net" ? selection.name : null) ?? highlightNet;
      if (!net) {
        notify("info", "Click on a track (or select a net) to choose the via's net.");
        return;
      }
      const s = snapPt(p);
      onApply([{ op: "add_via", net, x: s.x, y: s.y }], `Via on ${net}`);
      return;
    }

    // select tool
    const via = viaAt(p);
    if (via) return select({ kind: "via", id: via.id });
    const tr = trackAt(p);
    if (tr) return select({ kind: "track", id: tr.id });
    select(null);
    startPan(e);
  };

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const p = toWorld(e.clientX, e.clientY);
    setCursor({ x: Math.round(p.x * 100) / 100, y: Math.round(p.y * 100) / 100 });
    if (movePan(e)) return;
    if (route) setCursorPt(nextRoutePoint(p, e.shiftKey));
    if (drag) {
      const dx = p.x - drag.sx;
      const dy = p.y - drag.sy;
      setDrag({ ...drag, dx, dy, moved: drag.moved || Math.hypot(dx, dy) > 0.2 });
    }
  };

  const onUp = () => {
    endPan();
    if (drag && data) {
      if (drag.moved) {
        const c = data.components.find((x) => x.ref === drag.ref);
        if (c) onApply([{ op: "move_footprint", ref: c.ref, x: snap(c.x + drag.dx, pcbGrid), y: snap(c.y + drag.dy, pcbGrid) }], `Move ${c.ref}`);
      }
      setDrag(null);
    }
  };

  const ratsCount = data?.ratsnest.length ?? 0;

  return (
    <div className="relative h-full w-full overflow-hidden" style={{ background: "var(--pcb-bg)" }}>
      <svg
        ref={svgRef}
        data-testid="pcb-canvas"
        className={cn("h-full w-full touch-none", pcbTool !== "select" && "cursor-crosshair")}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onDoubleClick={() => route && finishRoute(route)}
        onPointerLeave={() => setCursor(null)}
        onContextMenu={(e) => {
          e.preventDefault();
          if (route) finishRoute(route);
        }}
      >
        {data && (
          <>
            <polygon points={data.board.outline.map((p) => p.join(",")).join(" ")} fill="var(--pcb-board)" />
            {layers["Edge.Cuts"] && (
              <polygon points={data.board.outline.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--pcb-edge)" strokeWidth={0.15} pointerEvents="none" />
            )}

            {(["B.Cu", "F.Cu"] as const).map((layer) =>
              layers[layer]
                ? data.tracks
                    .filter((t) => t.layer === layer)
                    .map((t) => {
                      const sel = selection?.kind === "track" && selection.id === t.id;
                      return (
                        <line
                          key={t.id}
                          x1={t.start.x}
                          y1={t.start.y}
                          x2={t.end.x}
                          y2={t.end.y}
                          stroke={layer === "F.Cu" ? "var(--pcb-fcu)" : "var(--pcb-bcu)"}
                          strokeWidth={t.width}
                          strokeLinecap="round"
                          opacity={highlightNet && t.net !== highlightNet ? 0.45 : layer === pcbLayer ? 0.95 : 0.6}
                          style={sel ? { filter: "drop-shadow(0 0 0.3px #fff)" } : undefined}
                        >
                          <title>{`${t.net} · ${t.layer} · ${t.width} mm`}</title>
                        </line>
                      );
                    })
                : null,
            )}

            {data.components.map((c) => {
              const fp = data.footprints[c.footprint];
              if (!fp) return null;
              const dragging = drag?.ref === c.ref;
              const selected = selection?.kind === "component" && selection.ref === c.ref;
              const cy = fp.courtyard;
              return (
                <g
                  key={c.ref}
                  data-testid={`footprint-${c.ref}`}
                  transform={`translate(${c.x + (dragging ? drag.dx : 0)} ${c.y + (dragging ? drag.dy : 0)}) rotate(${-c.rotation})`}
                  className={pcbTool === "select" ? "cursor-move" : undefined}
                  onPointerDown={(e) => {
                    if (pcbTool !== "select" || e.button !== 0) return;
                    e.stopPropagation();
                    select({ kind: "component", ref: c.ref });
                    const p = toWorld(e.clientX, e.clientY);
                    setDrag({ ref: c.ref, sx: p.x, sy: p.y, dx: 0, dy: 0, moved: false });
                    svgRef.current?.setPointerCapture(e.pointerId);
                  }}
                >
                  {cy && <rect x={cy[0]} y={cy[1]} width={cy[2] - cy[0]} height={cy[3] - cy[1]} fill="transparent" />}
                  {fp.graphics
                    .filter((g) => layers[g.layer])
                    .map((g, i) => (
                      <Graphic key={i} g={g} />
                    ))}
                  {fp.pads.map((pad, i) => (
                    <Pad key={`${pad.number}-${i}`} testId={`pad-${c.ref}.${pad.number}`} pad={pad} net={c.pad_nets[pad.number]} highlight={!!highlightNet && c.pad_nets[pad.number] === highlightNet} />
                  ))}
                  {selected && cy && (
                    <rect x={cy[0] - 0.2} y={cy[1] - 0.2} width={cy[2] - cy[0] + 0.4} height={cy[3] - cy[1] + 0.4} fill="none" stroke="var(--pcb-select)" strokeWidth={0.1} strokeDasharray="0.4 0.3" />
                  )}
                  {layers["F.SilkS"] && (
                    <text y={cy ? cy[1] - 0.6 : -2} fontSize={1} textAnchor="middle" fill="var(--pcb-silk)" className="canvas-text" transform={`rotate(${c.rotation})`} pointerEvents="none">
                      {c.ref}
                    </text>
                  )}
                </g>
              );
            })}

            {data.vias.map((v) => {
              const sel = selection?.kind === "via" && selection.id === v.id;
              return (
                <g key={v.id} opacity={highlightNet && v.net !== highlightNet ? 0.5 : 1}>
                  <circle cx={v.at.x} cy={v.at.y} r={v.diameter / 2} fill="var(--pcb-pad)" stroke={sel ? "var(--pcb-select)" : "none"} strokeWidth={0.08} />
                  <circle cx={v.at.x} cy={v.at.y} r={v.drill / 2} fill="var(--pcb-bg)" />
                </g>
              );
            })}

            {layers.Ratsnest &&
              data.ratsnest.map((r, i) => (
                <line key={`r${i}`} x1={r.x1} y1={r.y1} x2={r.x2} y2={r.y2} stroke="var(--pcb-rats)" strokeWidth={0.06} opacity={highlightNet && r.net !== highlightNet ? 0.25 : 0.8} pointerEvents="none" />
              ))}

            {route && (
              <polyline
                points={[...route.points, ...(cursorPt ? [cursorPt] : [])].map((p) => `${p.x},${p.y}`).join(" ")}
                fill="none"
                stroke={pcbLayer === "F.Cu" ? "var(--pcb-fcu)" : "var(--pcb-bcu)"}
                strokeWidth={data.board.rules.track_width}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={0.8}
                pointerEvents="none"
              />
            )}
            {focus?.view === "pcb" && (
              <circle cx={focus.x} cy={focus.y} r={1.2} fill="none" stroke="#ff5a5a" strokeWidth={0.2} className="animate-pulse-soft" pointerEvents="none" />
            )}
          </>
        )}
      </svg>

      <div className="absolute left-3 top-3 flex items-center gap-1 rounded-md border border-border bg-panel/95 p-1 shadow-sm">
        <Tip content={<span>Select / move <Kbd>Esc</Kbd> · rotate <Kbd>R</Kbd></span>}>
          <Button variant={pcbTool === "select" ? "default" : "ghost"} size="icon" onClick={() => setPcbTool("select")} aria-label="Select tool">
            <MousePointer2 className="h-4 w-4" />
          </Button>
        </Tip>
        <Tip content={<span>Route track <Kbd>X</Kbd> · Shift = free angle · double-click/Enter finish</span>}>
          <Button variant={pcbTool === "track" ? "default" : "ghost"} size="icon" onClick={() => setPcbTool("track")} aria-label="Route tool" data-testid="tool-track">
            <Route className="h-4 w-4" />
          </Button>
        </Tip>
        <Tip content="Place via (click on a track)">
          <Button variant={pcbTool === "via" ? "default" : "ghost"} size="icon" onClick={() => setPcbTool("via")} aria-label="Via tool">
            <CircleDot className="h-4 w-4" />
          </Button>
        </Tip>
        <div className="mx-0.5 h-5 w-px bg-border" />
        {(["F.Cu", "B.Cu"] as const).map((l) => (
          <button
            key={l}
            onClick={() => setPcbLayer(l)}
            className={cn("rounded px-1.5 py-1 text-[11px] font-medium", pcbLayer === l ? "bg-hover text-text" : "text-muted hover:text-text")}
            title={`Route on ${l}`}
          >
            <span className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: l === "F.Cu" ? "var(--pcb-fcu)" : "var(--pcb-bcu)" }} />
            {l}
          </button>
        ))}
        <select
          className="h-6 rounded border border-border bg-panel px-1 text-[11px] text-muted"
          value={pcbGrid}
          onChange={(e) => useEditor.getState().setPcbGrid(Number(e.target.value))}
          title="Snap grid"
        >
          {[0.05, 0.1, 0.25, 0.5, 1.27, 2.54].map((g) => (
            <option key={g} value={g}>
              grid {g} mm
            </option>
          ))}
        </select>
        <div className="mx-0.5 h-5 w-px bg-border" />
        <Tip content="Layers">
          <Button variant={showLayers ? "default" : "ghost"} size="icon" onClick={() => setShowLayers(!showLayers)} aria-label="Layers">
            <Layers className="h-4 w-4" />
          </Button>
        </Tip>
        <Tip content="Zoom to board">
          <Button variant="ghost" size="icon" onClick={fitBoard} aria-label="Zoom to board">
            <Maximize className="h-4 w-4" />
          </Button>
        </Tip>
      </div>
      {showLayers && (
        <div className="absolute left-3 top-14 w-44 rounded-md border border-border bg-panel p-2 text-xs shadow-lg">
          {Object.keys(layers).map((l) => (
            <label key={l} className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 hover:bg-hover">
              <input type="checkbox" checked={layers[l]} onChange={() => toggleLayer(l)} />
              {l}
            </label>
          ))}
        </div>
      )}
      {route && (
        <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-md border border-accent/40 bg-accent-soft px-3 py-1 text-xs text-accent">
          Routing <b>{route.net}</b> on {pcbLayer} · click to add corners · click a pad of the same net, double-click or Enter to finish · Esc cancels
        </div>
      )}
      <div className="pointer-events-none absolute bottom-2 right-3 rounded bg-black/50 px-2 py-0.5 text-[11px] text-white/80">
        {ratsCount > 0 ? `${ratsCount} unrouted connection${ratsCount === 1 ? "" : "s"} (preview ratsnest)` : "Preview ratsnest: no unrouted connections"} · KiCad DRC is authoritative
      </div>
      {loading && (
        <div className="absolute right-3 top-3">
          <Spinner />
        </div>
      )}
      {data && data.components.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="max-w-sm rounded-lg border border-dashed border-white/20 bg-black/40 p-5 text-center text-xs text-white/80">
            <div className="mb-1 text-sm font-medium text-white">No footprints yet</div>
            Footprints appear here when parts are added to the schematic.
          </div>
        </div>
      )}
    </div>
  );
}
