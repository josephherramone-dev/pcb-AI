import { describe, expect, it } from "vitest";
import { arcPath, autoNetName, constrain45, describeOperation, distToSegment, fpToBoard, libToSheet, snap } from "./geometry";

describe("libToSheet", () => {
  // Same expectations as backend/tests/test_operations.py::test_pin_positions_follow_rotation
  // (Device:R pin 1 is at library (0, 3.81)).
  it.each([
    [0, [100.33, 96.52]],
    [90, [96.52, 100.33]],
    [180, [100.33, 104.14]],
    [270, [104.14, 100.33]],
  ])("rotation %i", (rotation, expected) => {
    const [x, y] = libToSheet({ x: 100.33, y: 100.33, rotation }, 0, 3.81);
    expect(x).toBeCloseTo(expected[0], 4);
    expect(y).toBeCloseTo(expected[1], 4);
  });
});

describe("fpToBoard", () => {
  it("rotates pads counter-clockwise on screen", () => {
    const [x, y] = fpToBoard({ x: 10, y: 10, rotation: 90 }, 1, 0);
    expect(x).toBeCloseTo(10, 6);
    expect(y).toBeCloseTo(9, 6);
  });
});

describe("snap", () => {
  it("snaps to the schematic grid", () => {
    expect(snap(100, 1.27)).toBeCloseTo(100.33, 4);
    expect(snap(-0.5, 1.27)).toBeCloseTo(0, 4);
  });
});

describe("constrain45", () => {
  it("keeps horizontal, vertical and diagonal directions", () => {
    expect(constrain45({ x: 0, y: 0 }, { x: 10, y: 1 })).toEqual({ x: 10, y: 0 });
    expect(constrain45({ x: 0, y: 0 }, { x: 1, y: 10 })).toEqual({ x: 0, y: 10 });
    expect(constrain45({ x: 0, y: 0 }, { x: 5, y: -4 })).toEqual({ x: 5, y: -5 });
  });
});

describe("arcPath", () => {
  it("draws a semicircle through three points", () => {
    const p = arcPath([-1, 0], [0, 1], [1, 0]);
    expect(p.startsWith("M -1 0 A 1 1 0")).toBe(true);
  });
  it("falls back to a line for collinear points", () => {
    expect(arcPath([0, 0], [1, 0], [2, 0])).toBe("M 0 0 L 2 0");
  });
});

describe("misc", () => {
  it("measures distance to a segment", () => {
    expect(distToSegment({ x: 0, y: 1 }, { x: -1, y: 0 }, { x: 1, y: 0 })).toBeCloseTo(1);
  });
  it("creates unique valid net names", () => {
    expect(autoNetName("R1", "2", new Set(["N_R1_2"]))).toBe("N_R1_2_2");
  });
  it("describes operations", () => {
    expect(describeOperation({ op: "connect", net: "GND", pins: [{ ref: "R1", pin: "1" }] })).toBe(
      "Connect R1.1 to net GND",
    );
  });
});
