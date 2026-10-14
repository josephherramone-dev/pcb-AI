"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Pan/zoom state for an SVG canvas whose user units are millimetres.
 * Wheel zooms around the cursor; middle mouse, or left drag on the background, pans.
 */
export function useViewport(svgRef: RefObject<SVGSVGElement | null>, initial: ViewBox) {
  const [vb, setVb] = useState<ViewBox>(initial);
  const panning = useRef<{ sx: number; sy: number; vb: ViewBox } | null>(null);

  const toWorld = useCallback(
    (clientX: number, clientY: number) => {
      const svg = svgRef.current;
      if (!svg) return { x: 0, y: 0 };
      const ctm = svg.getScreenCTM();
      if (!ctm) return { x: 0, y: 0 };
      const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
      return { x: p.x, y: p.y };
    },
    [svgRef],
  );

  // Wheel zoom (non-passive listener so we can prevent page scroll).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const p = toWorld(e.clientX, e.clientY);
      const factor = Math.exp(e.deltaY * 0.0015);
      setVb((v) => {
        const w = Math.min(Math.max(v.w * factor, 2), 2000);
        const k = w / v.w;
        return { x: p.x - (p.x - v.x) * k, y: p.y - (p.y - v.y) * k, w, h: v.h * k };
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [svgRef, toWorld]);

  const startPan = useCallback(
    (e: React.PointerEvent) => {
      panning.current = { sx: e.clientX, sy: e.clientY, vb };
      (e.currentTarget as Element).setPointerCapture(e.pointerId);
    },
    [vb],
  );

  const movePan = useCallback(
    (e: React.PointerEvent) => {
      const p = panning.current;
      const svg = svgRef.current;
      if (!p || !svg) return false;
      const scale = p.vb.w / svg.clientWidth;
      setVb({ ...p.vb, x: p.vb.x - (e.clientX - p.sx) * scale, y: p.vb.y - (e.clientY - p.sy) * scale });
      return true;
    },
    [svgRef],
  );

  const endPan = useCallback(() => {
    const was = !!panning.current;
    panning.current = null;
    return was;
  }, []);

  const fit = useCallback(
    (box: ViewBox, margin = 0.08) => {
      const svg = svgRef.current;
      const aspect = svg && svg.clientHeight > 0 ? svg.clientWidth / svg.clientHeight : 16 / 9;
      let w = box.w * (1 + margin * 2);
      let h = box.h * (1 + margin * 2);
      if (w / h > aspect) h = w / aspect;
      else w = h * aspect;
      setVb({ x: box.x + box.w / 2 - w / 2, y: box.y + box.h / 2 - h / 2, w, h });
    },
    [svgRef],
  );

  const centerOn = useCallback((x: number, y: number, w?: number) => {
    setVb((v) => {
      const nw = w ?? v.w;
      const nh = (v.h * nw) / v.w;
      return { x: x - nw / 2, y: y - nh / 2, w: nw, h: nh };
    });
  }, []);

  // Keep aspect ratio in sync with element size.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const ro = new ResizeObserver(() => {
      if (svg.clientWidth === 0 || svg.clientHeight === 0) return;
      setVb((v) => ({ ...v, h: (v.w * svg.clientHeight) / svg.clientWidth }));
    });
    ro.observe(svg);
    return () => ro.disconnect();
  }, [svgRef]);

  return { vb, setVb, toWorld, startPan, movePan, endPan, fit, centerOn, isPanning: () => !!panning.current };
}
