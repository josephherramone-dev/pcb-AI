"use client";

import { Info } from "lucide-react";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { useCapabilities } from "@/components/engine-status";
import { fpToBoard } from "@/lib/geometry";
import type { PcbRender } from "@/lib/types";

const BOARD_THICKNESS = 1.6;

// Approximate body heights (mm) used only for this preview, chosen by footprint family.
function bodyHeight(footprint: string): number {
  if (footprint.includes("PinHeader")) return 8.5;
  if (footprint.includes("CP_Radial")) return 11;
  if (footprint.includes("DIP")) return 3.3;
  if (footprint.includes("SW_PUSH")) return 3.5;
  if (footprint.includes("SOT-223")) return 1.7;
  if (footprint.includes("SOT-23")) return 1.1;
  return 0.8;
}

export function Board3D({ data }: { data: PcbRender | undefined }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const caps = useCapabilities();
  const glb = caps.data?.eda.features.glb;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !data) return;
    const width = mount.clientWidth || 800;
    const height = mount.clientHeight || 600;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x151a22);
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 5000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const sun = new THREE.DirectionalLight(0xffffff, 1.1);
    sun.position.set(40, 80, 60);
    scene.add(sun);

    // KiCad coordinates (Y down) -> three.js (x, z) plane with Y up.
    const { origin, width: bw, height: bh, outline } = data.board;
    const cx = origin.x + bw / 2;
    const cy = origin.y + bh / 2;
    const toX = (x: number) => x - cx;
    const toZ = (y: number) => y - cy;

    const shape = new THREE.Shape(outline.map(([x, y]) => new THREE.Vector2(toX(x), -toZ(y))));
    const boardGeom = new THREE.ExtrudeGeometry(shape, { depth: BOARD_THICKNESS, bevelEnabled: false });
    boardGeom.rotateX(-Math.PI / 2);
    const board = new THREE.Mesh(boardGeom, new THREE.MeshStandardMaterial({ color: 0x1f6b3a, roughness: 0.8 }));
    scene.add(board);

    const copper = new THREE.MeshStandardMaterial({ color: 0xd4a640, metalness: 0.6, roughness: 0.35 });
    const topY = BOARD_THICKNESS;
    const disposables: { dispose: () => void }[] = [boardGeom, copper];

    for (const c of data.components) {
      const fp = data.footprints[c.footprint];
      if (!fp) continue;
      for (const pad of fp.pads) {
        const [px, py] = fpToBoard(c, pad.x, pad.y);
        const g = pad.shape === "circle" ? new THREE.CylinderGeometry(pad.width / 2, pad.width / 2, 0.04, 24) : new THREE.BoxGeometry(pad.width, 0.04, pad.height);
        disposables.push(g);
        const m = new THREE.Mesh(g, copper);
        m.position.set(toX(px), topY + 0.02, toZ(py));
        m.rotation.y = ((c.rotation + pad.angle) * Math.PI) / 180;
        scene.add(m);
      }
      if (fp.courtyard) {
        const [x1, y1, x2, y2] = fp.courtyard;
        const w = Math.max(x2 - x1 - 0.5, 0.3);
        const d = Math.max(y2 - y1 - 0.5, 0.3);
        const h = bodyHeight(c.footprint);
        const g = new THREE.BoxGeometry(w, h, d);
        const mat = new THREE.MeshStandardMaterial({ color: 0x2b2f36, roughness: 0.6, transparent: true, opacity: 0.85 });
        disposables.push(g, mat);
        const body = new THREE.Mesh(g, mat);
        const [bx, by] = fpToBoard(c, (x1 + x2) / 2, (y1 + y2) / 2);
        body.position.set(toX(bx), topY + h / 2 + 0.05, toZ(by));
        body.rotation.y = (c.rotation * Math.PI) / 180;
        scene.add(body);
      }
    }
    const trackMat = new THREE.MeshStandardMaterial({ color: 0xc8553d, metalness: 0.5, roughness: 0.4 });
    disposables.push(trackMat);
    for (const t of data.tracks) {
      const len = Math.hypot(t.end.x - t.start.x, t.end.y - t.start.y);
      const g = new THREE.BoxGeometry(len, 0.035, t.width);
      disposables.push(g);
      const m = new THREE.Mesh(g, trackMat);
      const y = t.layer === "F.Cu" ? topY + 0.02 : -0.02;
      m.position.set(toX((t.start.x + t.end.x) / 2), y, toZ((t.start.y + t.end.y) / 2));
      m.rotation.y = -Math.atan2(t.end.y - t.start.y, t.end.x - t.start.x);
      scene.add(m);
    }

    // Distance chosen so the board fits both the vertical and horizontal field of view.
    const span = Math.hypot(bw, bh);
    const vfov = (camera.fov * Math.PI) / 180;
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
    const dist = (span / 2 / Math.tan(Math.min(vfov, hfov) / 2)) * 1.15;
    camera.position.copy(new THREE.Vector3(0.45, 0.75, 0.85).normalize().multiplyScalar(dist));
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, BOARD_THICKNESS, 0);
    controls.enableDamping = true;
    controls.update();

    let frame = 0;
    const loop = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(loop);
    };
    loop();

    const ro = new ResizeObserver(() => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    ro.observe(mount);

    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      controls.dispose();
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
  }, [data]);

  return (
    <div className="relative h-full w-full" data-testid="board-3d">
      <div ref={mountRef} className="h-full w-full" />
      <div className="absolute left-3 top-3 max-w-md rounded-md border border-white/15 bg-black/60 px-3 py-2 text-[11px] text-white/85">
        <div className="mb-0.5 flex items-center gap-1.5 font-medium text-white">
          <Info className="h-3.5 w-3.5" /> Approximate 3D preview
        </div>
        Board outline, pads and tracks are drawn from the design. Component bodies are boxes derived from footprint courtyards with estimated heights — not
        manufacturer 3D models.{" "}
        {glb?.available
          ? "KiCad GLB export is available on this engine; model-accurate 3D views are planned next (3D model libraries are not installed yet)."
          : `KiCad GLB export is not available on this engine (${glb?.reason ?? "unknown"}).`}
      </div>
    </div>
  );
}
