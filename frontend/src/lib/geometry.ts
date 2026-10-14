// Geometry helpers shared by the schematic and PCB canvases.
// Conventions match KiCad and the backend (backend/app/kicad/schematic_layout.py):
//  - library symbol coordinates have Y pointing up;
//  - schematic and PCB coordinates have Y pointing down (millimetres);
//  - rotations are counter-clockwise as seen on screen.

import type { Operation, Point } from "./types";

export const SCHEMATIC_GRID = 1.27;

export function snap(v: number, grid: number): number {
  return Math.round(Math.round(v / grid) * grid * 10000) / 10000;
}

/** Rotate a point counter-clockwise on screen (Y axis down) by `deg` degrees. */
export function rotateScreen(x: number, y: number, deg: number): [number, number] {
  const a = (deg * Math.PI) / 180;
  const c = Math.round(Math.cos(a) * 1e12) / 1e12;
  const s = Math.round(Math.sin(a) * 1e12) / 1e12;
  return [x * c + y * s, -x * s + y * c];
}

/** Library (Y up) point -> absolute schematic coordinates for a placed symbol. */
export function libToSheet(placement: { x: number; y: number; rotation: number }, x: number, y: number): [number, number] {
  const [rx, ry] = rotateScreen(x, -y, placement.rotation);
  return [round4(placement.x + rx), round4(placement.y + ry)];
}

/** Footprint-local point -> absolute board coordinates. */
export function fpToBoard(placement: { x: number; y: number; rotation: number }, x: number, y: number): [number, number] {
  const [rx, ry] = rotateScreen(x, y, placement.rotation);
  return [round4(placement.x + rx), round4(placement.y + ry)];
}

export function round4(v: number): number {
  return Math.round(v * 10000) / 10000;
}

/** SVG path for a circular arc through three points. */
export function arcPath(start: [number, number], mid: [number, number], end: [number, number]): string {
  const [ax, ay] = start;
  const [bx, by] = mid;
  const [cx, cy] = end;
  const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  if (Math.abs(d) < 1e-9) return `M ${ax} ${ay} L ${cx} ${cy}`;
  const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d;
  const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d;
  const r = Math.hypot(ax - ux, ay - uy);
  // Orientation of (start, mid, end) decides the sweep direction.
  const cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
  const sweep = cross > 0 ? 1 : 0;
  // Large arc if the mid point lies on the far side of the chord from the centre.
  const side = (px: number, py: number) => (cx - ax) * (py - ay) - (cy - ay) * (px - ax);
  const large = Math.sign(side(bx, by)) === Math.sign(side(ux, uy)) ? 1 : 0;
  return `M ${ax} ${ay} A ${r} ${r} 0 ${large} ${sweep} ${cx} ${cy}`;
}

/** Constrain a track segment to horizontal, vertical or 45 degrees. */
export function constrain45(from: Point, to: Point): Point {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const adx = Math.abs(dx);
  const ady = Math.abs(dy);
  if (adx > ady * 2.414) return { x: to.x, y: from.y };
  if (ady > adx * 2.414) return { x: from.x, y: to.y };
  const m = Math.max(adx, ady);
  return { x: from.x + Math.sign(dx) * m, y: from.y + Math.sign(dy) * m };
}

export function distToSegment(p: Point, a: Point, b: Point): number {
  const vx = b.x - a.x;
  const vy = b.y - a.y;
  const len2 = vx * vx + vy * vy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * vx + (p.y - a.y) * vy) / len2));
  return Math.hypot(p.x - (a.x + t * vx), p.y - (a.y + t * vy));
}

/** Valid net name per backend rules. */
export const NET_NAME_RE = /^[A-Za-z0-9_+\-.]{1,40}$/;

export function autoNetName(ref: string, pin: string, existing: Set<string>): string {
  const base = `N_${ref.replace(/[^A-Za-z0-9]/g, "")}_${pin.replace(/[^A-Za-z0-9]/g, "")}`.slice(0, 36);
  let name = base;
  let i = 2;
  while (existing.has(name)) name = `${base}_${i++}`;
  return name;
}

export function describeOperation(op: Operation): string {
  switch (op.op) {
    case "add_component":
      return `Add ${op.part_id}${op.ref ? ` as ${op.ref}` : ""}${op.value ? ` (${op.value})` : ""}`;
    case "remove_component":
      return `Remove ${op.ref}`;
    case "set_value":
      return `Set ${op.ref} value to ${op.value}`;
    case "move_symbol":
      return `Move symbol ${op.ref} to (${op.x}, ${op.y})${op.rotation != null ? ` rot ${op.rotation}°` : ""}`;
    case "move_footprint":
      return `Move footprint ${op.ref} to (${op.x}, ${op.y})${op.rotation != null ? ` rot ${op.rotation}°` : ""}`;
    case "connect":
      return `Connect ${op.pins.map((p) => `${p.ref}.${p.pin}`).join(", ")} to net ${op.net}`;
    case "disconnect":
      return `Disconnect ${op.pins.map((p) => `${p.ref}.${p.pin}`).join(", ")}`;
    case "rename_net":
      return `Rename net ${op.name} to ${op.new_name}`;
    case "delete_net":
      return `Delete net ${op.name}`;
    case "set_no_connect":
      return `${op.enabled ? "Mark" : "Unmark"} ${op.pin.ref}.${op.pin.pin} as no-connect`;
    case "add_track":
      return `Add ${op.points.length - 1} track segment(s) on ${op.layer} for ${op.net}`;
    case "delete_track":
      return `Delete track ${op.id}`;
    case "add_via":
      return `Add via on ${op.net} at (${op.x}, ${op.y})`;
    case "delete_via":
      return `Delete via ${op.id}`;
    case "set_board":
      return `Set board to ${op.width} × ${op.height} mm`;
    case "set_rules":
      return `Update design rules`;
    case "set_title":
      return `Set title to "${op.title}"`;
    case "load_template":
      return `Load template ${op.template_id}`;
  }
}
