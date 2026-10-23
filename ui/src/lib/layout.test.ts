import { describe, expect, it } from "vitest";
import { MAP_MIN, PANEL_MIN, clampWidth, panelMax } from "@/lib/layout";

describe("panelMax", () => {
  it("is 80 % of a wide page", () => {
    expect(panelMax(3000)).toBe(2400);
    expect(panelMax(1800)).toBe(1440);
    expect(panelMax(1801)).toBe(1440);
  });
  it("leaves the map its 360 px where 80 % would not", () => {
    expect(panelMax(1600)).toBe(1240);
    expect(panelMax(1000)).toBe(640);
    expect(panelMax(900)).toBe(540);
    expect(1000 - panelMax(1000)).toBeGreaterThanOrEqual(MAP_MIN);
    expect(900 - panelMax(900)).toBeGreaterThanOrEqual(MAP_MIN);
  });
  it("is never less than the least", () => {
    expect(panelMax(640)).toBe(PANEL_MIN);
    expect(panelMax(300)).toBe(PANEL_MIN);
  });
});

describe("clampWidth", () => {
  it("keeps a width inside the limits", () => {
    expect(clampWidth(100, 1600)).toBe(PANEL_MIN);
    expect(clampWidth(5000, 4000)).toBe(3200);
    expect(clampWidth(401.4, 1600)).toBe(401);
  });
  it("lets the drag go to 80 % of the window", () => {
    expect(clampWidth(1200, 3000)).toBe(1200);
    expect(clampWidth(2500, 3000)).toBe(2400);
  });
  it("leaves the map 360 px on a smaller window", () => {
    expect(clampWidth(1500, 1600)).toBe(1240);
    expect(clampWidth(900, 800)).toBe(440);
    expect(clampWidth(900, 300)).toBe(PANEL_MIN);
  });
});
