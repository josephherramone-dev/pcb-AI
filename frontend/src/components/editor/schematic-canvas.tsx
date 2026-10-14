"use client";

import { Maximize, MousePointer2, Spline } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Kbd, Spinner, Tip } from "@/components/ui/primitives";
import { arcPath, autoNetName, libToSheet, SCHEMATIC_GRID, snap } from "@/lib/geometry";
import { useEditor } from "@/lib/editor-store";
import type { Operation, PinRef, SchematicRender, SymbolRender } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useViewport } from "./use-viewport";

type Comp = SchematicRender["components"][number];

const MIN_STROKE = 0.1524;

function SymbolBody({ symbol }: { symbol: SymbolRender }) {
  return (
    <>
      {symbol.graphics.map((g, i) => {
        if (g.kind === "text") return null;
        const sw = Math.max(g.stroke_width, MIN_STROKE);
        const fill = g.fill === "outline" ? "var(--sch-body)" : g.fill === "background" ? "var(--sch-body-fill)" : "none";
        const common = { stroke: "var(--sch-body)", strokeWidth: sw, fill, strokeLinejoin: "round" as const, strokeLinecap: "round" as const };
        switch (g.kind) {
          case "rect":
            return <rect key={i} x={Math.min(g.x1, g.x2)} y={Math.min(g.y1, g.y2)} width={Math.abs(g.x2 - g.x1)} height={Math.abs(g.y2 - g.y1)} {...common} />;
          case "polyline":
            return <polyline key={i} points={g.points.map((p) => p.join(",")).join(" ")} {...common} />;
          case "circle":
            return <circle key={i} cx={g.cx} cy={g.cy} r={g.r} {...common} />;
          case "arc":
            return <path key={i} d={arcPath(g.start, g.mid, g.end)} {...common} fill={fill === "none" ? "none" : fill} />;
        }
      })}
      {symbol.pins
        .filter((p) => !p.hidden && p.length > 0)
        .map((p) => {
          const a = (p.angle * Math.PI) / 180;
          return (
            <line
              key={p.number}
              x1={p.x}
              y1={p.y}
              x2={p.x + Math.cos(a) * p.length}
              y2={p.y + Math.sin(a) * p.length}
              stroke="var(--sch-pin)"
              strokeWidth={MIN_STROKE}
            />
          );
        })}
    </>
  );
}

function symbolBBox(symbol: SymbolRender): [number, number, number, number] {
  const xs: number[] = [];
  const ys: number[] = [];
  const add = (x: number, y: number) => {
    xs.push(x);
    ys.push(y);
  };
  for (const g of symbol.graphics) {
    if (g.kind === "rect") {
      add(g.x1, g.y1);
      add(g.x2, g.y2);
    } else if (g.kind === "polyline") g.points.forEach(([x, y]) => add(x, y));
    else if (g.kind === "circle") {
      add(g.cx - g.r, g.cy - g.r);
      add(g.cx + g.r, g.cy + g.r);
    } else if (g.kind === "arc") [g.start, g.mid, g.end].forEach(([x, y]) => add(x, y));
  }
  for (const p of symbol.pins) add(p.x, p.y);
  if (!xs.length) return [-1, -1, 1, 1];
  return [Math.min(...xs) - 0.5, Math.min(...ys) - 0.5, Math.max(...xs) + 0.5, Math.max(...ys) + 0.5];
}

function PinTexts({ comp, symbol }: { comp: Comp; symbol: SymbolRender }) {
  return (
    <>
      {symbol.pins
        .filter((p) => !p.hidden && p.length > 0)
        .map((p) => {
          const a = (p.angle * Math.PI) / 180;
          const [x0, y0] = libToSheet(comp, p.x, p.y);
          const [x1, y1] = libToSheet(comp, p.x + Math.cos(a) * p.length, p.y + Math.sin(a) * p.length);
          const len = Math.hypot(x1 - x0, y1 - y0) || 1;
          const dx = (x1 - x0) / len;
          const dy = (y1 - y0) / len;
          const vertical = Math.abs(dy) > 0.5;
          const showName = !symbol.pin_names_hidden && p.name !== "~" && p.name !== "";
          const showNum = !symbol.pin_numbers_hidden;
          const off = symbol.pin_name_offset || 0.5;
          const nx = x1 + dx * off;
          const ny = y1 + dy * off;
          const mx = (x0 + x1) / 2;
          const my = (y0 + y1) / 2;
          const nameAnchor = (vertical ? dy < 0 : dx > 0) ? "start" : "end";
          const name = p.name.replace(/~\{([^}]*)\}/g, "$1");
          return (
            <g key={p.number} className="canvas-text" fontSize={1.0}>
              {showName && (
                <text
                  x={nx}
                  y={ny}
                  fill="var(--sch-text)"
                  textAnchor={nameAnchor}
                  dominantBaseline="central"
                  transform={vertical ? `rotate(-90 ${nx} ${ny})` : undefined}
                >
                  {name}
                </text>
              )}
              {showNum && (
                <text
                  x={vertical ? mx - 0.4 : mx}
                  y={vertical ? my : my - 0.4}
                  fill="var(--sch-pin)"
                  fontSize={0.9}
                  textAnchor="middle"
                  transform={vertical ? `rotate(-90 ${mx - 0.4} ${my})` : undefined}
                >
                  {p.number}
                </text>
              )}
            </g>
          );
        })}
    </>
  );
}

export function SchematicCanvas({
  data,
  loading,
  onApply,
}: {
  data: SchematicRender | undefined;
  loading: boolean;
  onApply: (ops: Operation[], message?: string) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const { vb, toWorld, startPan, movePan, endPan, fit, centerOn } = useViewport(svgRef, { x: 0, y: 0, w: 297, h: 210 });
  const { selection, select, schTool, setSchTool, wireStart, setWireStart, notify, setCursor, focus } = useEditor();
  const [drag, setDrag] = useState<{ ref: string; sx: number; sy: number; dx: number; dy: number; moved: boolean } | null>(null);
  const [hoverPin, setHoverPin] = useState<string | null>(null);
  const [ghost, setGhost] = useState<{ x: number; y: number } | null>(null);
  const fitted = useRef(false);

  const fitAll = useCallback(() => {
    if (!data) return;
    const xs: number[] = [];
    const ys: number[] = [];
    for (const c of data.components) {
      const symbol = data.symbols[c.lib_symbol];
      if (!symbol) continue;
      const [x1, y1, x2, y2] = symbolBBox(symbol);
      for (const [lx, ly] of [[x1, y1], [x2, y2], [x1, y2], [x2, y1]]) {
        const [sx, sy] = libToSheet(c, lx, ly);
        xs.push(sx);
        ys.push(sy);
      }
    }
    for (const l of data.labels) {
      xs.push(l.x - 4, l.x + 4);
      ys.push(l.y);
    }
    if (!xs.length) return fit({ x: 0, y: 0, w: data.page.width, h: data.page.height }, 0.02);
    const minX = Math.min(...xs) - 4;
    const minY = Math.min(...ys) - 4;
    fit({ x: minX, y: minY, w: Math.max(...xs) + 4 - minX, h: Math.max(...ys) + 4 - minY }, 0.04);
  }, [data, fit]);

  useEffect(() => {
    if (data && !fitted.current) {
      fitted.current = true;
      fitAll();
    }
  }, [data, fitAll]);

  useEffect(() => {
    if (focus && focus.view === "schematic") centerOn(focus.x, focus.y, 60);
  }, [focus, centerOn]);

  const pinNet = useMemo(() => {
    const m = new Map<string, string>();
    data?.pins.forEach((p) => p.net && m.set(`${p.ref}.${p.number}`, p.net));
    return m;
  }, [data]);

  const highlightNet =
    selection?.kind === "net" ? selection.name : selection?.kind === "pin" ? pinNet.get(`${selection.ref}.${selection.pin}`) ?? null : null;

  const handlePinClick = (pin: PinRef) => {
    if (schTool.kind !== "wire") {
      select({ kind: "pin", ...pin });
      return;
    }
    if (!wireStart) {
      setWireStart(pin);
      return;
    }
    if (wireStart.ref === pin.ref && wireStart.pin === pin.pin) {
      setWireStart(null);
      return;
    }
    const a = pinNet.get(`${wireStart.ref}.${wireStart.pin}`);
    const b = pinNet.get(`${pin.ref}.${pin.pin}`);
    let op: Operation | null = null;
    if (!a && !b) {
      const name = autoNetName(wireStart.ref, wireStart.pin, new Set(data?.nets.map((n) => n.name)));
      op = { op: "connect", net: name, pins: [wireStart, pin] };
    } else if (a && !b) op = { op: "connect", net: a, pins: [pin] };
    else if (!a && b) op = { op: "connect", net: b, pins: [wireStart] };
    else if (a === b) notify("info", `Both pins are already on net ${a}.`);
    else notify("error", `Pins are on different nets (${a}, ${b}). Merging nets is not supported yet — disconnect one pin first.`);
    if (op) onApply([op], "Connect pins");
    setWireStart(null);
  };

  const onBackgroundDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button === 1 || (e.button === 0 && e.target === svgRef.current) || (e.button === 0 && (e.target as SVGElement).dataset.bg)) {
      if (e.button === 0 && schTool.kind === "place") {
        const p = toWorld(e.clientX, e.clientY);
        onApply([{ op: "add_component", part_id: schTool.partId, x: snap(p.x, SCHEMATIC_GRID), y: snap(p.y, SCHEMATIC_GRID) }], `Place ${schTool.partId}`);
        if (!e.shiftKey) setSchTool({ kind: "select" });
        return;
      }
      if (e.button === 0) {
        select(null);
        setWireStart(null);
      }
      startPan(e);
    }
  };

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const p = toWorld(e.clientX, e.clientY);
    setCursor({ x: Math.round(p.x * 100) / 100, y: Math.round(p.y * 100) / 100 });
    if (schTool.kind === "place" || schTool.kind === "wire") setGhost({ x: snap(p.x, SCHEMATIC_GRID), y: snap(p.y, SCHEMATIC_GRID) });
    if (movePan(e)) return;
    if (drag) {
      const dx = p.x - drag.sx;
      const dy = p.y - drag.sy;
      setDrag({ ...drag, dx, dy, moved: drag.moved || Math.hypot(dx, dy) > 0.5 });
    }
  };

  const onUp = () => {
    endPan();
    if (drag) {
      if (drag.moved) {
        const c = data?.components.find((x) => x.ref === drag.ref);
        if (c) onApply([{ op: "move_symbol", ref: c.ref, x: snap(c.x + drag.dx, SCHEMATIC_GRID), y: snap(c.y + drag.dy, SCHEMATIC_GRID) }], `Move ${c.ref}`);
      }
      setDrag(null);
    }
  };

  const wireStartPos = wireStart && data?.pins.find((p) => p.ref === wireStart.ref && p.number === wireStart.pin);

  return (
    <div className="relative h-full w-full overflow-hidden" style={{ background: "var(--sch-bg)" }}>
      <svg
        ref={svgRef}
        data-testid="schematic-canvas"
        className={cn("h-full w-full touch-none", schTool.kind !== "select" ? "cursor-crosshair" : "cursor-default")}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        onPointerDown={onBackgroundDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={() => {
          setCursor(null);
          setGhost(null);
        }}
        onContextMenu={(e) => e.preventDefault()}
      >
        <defs>
          <pattern id="sch-grid" width={SCHEMATIC_GRID * 2} height={SCHEMATIC_GRID * 2} patternUnits="userSpaceOnUse">
            <circle cx={0} cy={0} r={0.12} fill="var(--sch-grid)" />
          </pattern>
        </defs>
        <rect data-bg="1" x={vb.x} y={vb.y} width={vb.w} height={vb.h} fill="url(#sch-grid)" />
        {data && (
          <rect x={0} y={0} width={data.page.width} height={data.page.height} fill="none" stroke="var(--sch-sheet)" strokeWidth={0.3} pointerEvents="none" />
        )}

        {/* wires & labels (computed by the backend, identical to the .kicad_sch file) */}
        {data?.wires.map((w, i) => (
          <line
            key={`w${i}`}
            x1={w.x1}
            y1={w.y1}
            x2={w.x2}
            y2={w.y2}
            stroke={highlightNet === w.net ? "var(--sch-select)" : "var(--sch-wire)"}
            strokeWidth={highlightNet === w.net ? 0.35 : 0.2}
            strokeLinecap="round"
            pointerEvents="none"
          />
        ))}
        {data?.labels.map((l, i) => {
          const vertical = l.angle === 90 || l.angle === 270;
          const anchor = l.justify === "left" ? "start" : "end";
          return (
            <text
              key={`l${i}`}
              x={l.x}
              y={l.y - 0.3}
              fontSize={1.27}
              className="canvas-text cursor-pointer"
              fill={highlightNet === l.net ? "var(--sch-select)" : "var(--sch-label)"}
              fontWeight={highlightNet === l.net ? 700 : 500}
              textAnchor={anchor}
              transform={vertical ? `rotate(-90 ${l.x} ${l.y})` : undefined}
              onPointerDown={(e) => {
                e.stopPropagation();
                select({ kind: "net", name: l.net });
              }}
            >
              {l.net}
            </text>
          );
        })}
        {data?.no_connects.map((n, i) => (
          <g key={`nc${i}`} stroke="var(--sch-pin)" strokeWidth={0.2} pointerEvents="none">
            <line x1={n.x - 0.6} y1={n.y - 0.6} x2={n.x + 0.6} y2={n.y + 0.6} />
            <line x1={n.x - 0.6} y1={n.y + 0.6} x2={n.x + 0.6} y2={n.y - 0.6} />
          </g>
        ))}

        {/* symbols */}
        {data?.components.map((c) => {
          const symbol = data.symbols[c.lib_symbol];
          if (!symbol) return null;
          const dragging = drag?.ref === c.ref;
          const ox = dragging ? drag.dx : 0;
          const oy = dragging ? drag.dy : 0;
          const selected = selection?.kind === "component" && selection.ref === c.ref;
          const [bx1, by1, bx2, by2] = symbolBBox(symbol);
          return (
            <g key={c.ref} transform={`translate(${ox} ${oy})`} data-testid={`symbol-${c.ref}`} opacity={dragging ? 0.7 : 1}>
              <g
                transform={`translate(${c.x} ${c.y}) rotate(${-c.rotation}) scale(1 -1)`}
                className={schTool.kind === "select" ? "cursor-move" : undefined}
                onPointerDown={(e) => {
                  if (e.button !== 0 || schTool.kind !== "select") return;
                  e.stopPropagation();
                  select({ kind: "component", ref: c.ref });
                  const p = toWorld(e.clientX, e.clientY);
                  setDrag({ ref: c.ref, sx: p.x, sy: p.y, dx: 0, dy: 0, moved: false });
                  svgRef.current?.setPointerCapture(e.pointerId);
                }}
              >
                <rect x={bx1} y={by1} width={bx2 - bx1} height={by2 - by1} fill="transparent" />
                <SymbolBody symbol={symbol} />
                {selected && (
                  <rect x={bx1} y={by1} width={bx2 - bx1} height={by2 - by1} fill="none" stroke="var(--sch-select)" strokeWidth={0.2} strokeDasharray="0.8 0.5" />
                )}
              </g>
              <PinTexts comp={c} symbol={symbol} />
              {c.fields
                .filter((f) => !f.hidden)
                .map((f) => (
                  <text
                    key={f.name}
                    x={f.x}
                    y={f.y}
                    fontSize={1.27}
                    className="canvas-text"
                    fill={f.name === "Reference" ? "var(--sch-text)" : "var(--sch-label)"}
                    textAnchor="middle"
                    dominantBaseline="central"
                    transform={f.angle === 90 ? `rotate(-90 ${f.x} ${f.y})` : undefined}
                    pointerEvents="none"
                  >
                    {f.value}
                  </text>
                ))}
            </g>
          );
        })}

        {/* pin connection points (clickable) */}
        {data?.pins.map((p) => {
          const key = `${p.ref}.${p.number}`;
          const dragOffset = drag?.ref === p.ref ? drag : null;
          const isSel = selection?.kind === "pin" && selection.ref === p.ref && selection.pin === p.number;
          const isStart = wireStart?.ref === p.ref && wireStart.pin === p.number;
          const onNet = highlightNet && p.net === highlightNet;
          const show = hoverPin === key || isSel || isStart || schTool.kind === "wire";
          return (
            <circle
              key={key}
              data-testid={`pin-${key}`}
              cx={p.x + (dragOffset?.dx ?? 0)}
              cy={p.y + (dragOffset?.dy ?? 0)}
              r={show ? 0.55 : 0.35}
              fill={isStart || isSel ? "var(--sch-select)" : onNet ? "var(--sch-select)" : p.net ? "var(--sch-wire)" : "transparent"}
              stroke={show ? "var(--sch-select)" : "none"}
              strokeWidth={0.12}
              className="cursor-pointer"
              onPointerEnter={() => setHoverPin(key)}
              onPointerLeave={() => setHoverPin(null)}
              onPointerDown={(e) => {
                e.stopPropagation();
                handlePinClick({ ref: p.ref, pin: p.number });
              }}
            >
              <title>{`${p.ref} pin ${p.number}${p.name && p.name !== "~" ? ` (${p.name})` : ""} · ${p.electrical_type}${p.net ? ` · net ${p.net}` : " · unconnected"}`}</title>
            </circle>
          );
        })}

        {focus?.view === "schematic" && (
          <circle cx={focus.x} cy={focus.y} r={2} fill="none" stroke="#ff5a5a" strokeWidth={0.3} className="animate-pulse-soft" pointerEvents="none" />
        )}
        {schTool.kind === "wire" && wireStartPos && ghost && (
          <line x1={wireStartPos.x} y1={wireStartPos.y} x2={ghost.x} y2={ghost.y} stroke="var(--sch-select)" strokeWidth={0.2} strokeDasharray="0.6 0.4" pointerEvents="none" />
        )}
        {schTool.kind === "place" && ghost && (
          <g pointerEvents="none" stroke="var(--sch-select)" strokeWidth={0.2}>
            <line x1={ghost.x - 2} y1={ghost.y} x2={ghost.x + 2} y2={ghost.y} />
            <line x1={ghost.x} y1={ghost.y - 2} x2={ghost.x} y2={ghost.y + 2} />
          </g>
        )}
      </svg>

      {/* canvas overlay toolbar */}
      <div className="absolute left-3 top-3 flex items-center gap-1 rounded-md border border-border bg-panel/95 p-1 shadow-sm">
        <Tip content={<span>Select / move <Kbd>Esc</Kbd></span>}>
          <Button variant={schTool.kind === "select" ? "default" : "ghost"} size="icon" onClick={() => setSchTool({ kind: "select" })} aria-label="Select tool">
            <MousePointer2 className="h-4 w-4" />
          </Button>
        </Tip>
        <Tip content={<span>Connect two pins <Kbd>W</Kbd></span>}>
          <Button variant={schTool.kind === "wire" ? "default" : "ghost"} size="icon" onClick={() => setSchTool({ kind: "wire" })} aria-label="Connect tool" data-testid="tool-wire">
            <Spline className="h-4 w-4" />
          </Button>
        </Tip>
        <div className="mx-0.5 h-5 w-px bg-border" />
        <Tip content="Zoom to fit">
          <Button variant="ghost" size="icon" onClick={fitAll} aria-label="Zoom to fit">
            <Maximize className="h-4 w-4" />
          </Button>
        </Tip>
      </div>
      {schTool.kind !== "select" && (
        <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-md border border-accent/40 bg-accent-soft px-3 py-1 text-xs text-accent shadow-sm">
          {schTool.kind === "place" && <>Click to place <b>{schTool.partId}</b> · Shift-click to place several · Esc to cancel</>}
          {schTool.kind === "wire" && (wireStart ? <>Click the second pin to connect it to <b>{wireStart.ref}.{wireStart.pin}</b></> : <>Click a pin to start a connection</>)}
        </div>
      )}
      <div className="pointer-events-none absolute bottom-2 right-3 rounded bg-panel/80 px-2 py-0.5 text-[11px] text-muted">
        Preview rendered from KiCad library data · connectivity uses net labels
      </div>
      {loading && (
        <div className="absolute right-3 top-3">
          <Spinner />
        </div>
      )}
      {data && data.components.length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="max-w-sm rounded-lg border border-dashed border-border-strong bg-panel/90 p-5 text-center text-xs text-muted">
            <div className="mb-1 text-sm font-medium text-text">Empty schematic</div>
            Place parts from the <b>Library</b> panel, or describe the circuit to the AI assistant. Only parts with verified KiCad symbol/footprint pairs can be placed.
          </div>
        </div>
      )}
    </div>
  );
}
