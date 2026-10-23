import { describe, expect, it } from "vitest";
import { MAP_MIN, PANEL_DEFAULT, PANEL_DEFAULT_WIDE, PANEL_MIN, cardCapacity, clampWidth, defaultPanelWidth, panelMax, sizeOf } from "@/lib/layout";

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

describe("sizeOf", () => {
  it("is a phone under 700 px, a tablet from 700 to 1100 px, a desktop from 1100 px", () => {
    expect([360, 375, 390, 699].map((w) => sizeOf(w, 800))).toEqual(["phone", "phone", "phone", "phone"]);
    expect([700, 768, 1024, 1099].map((w) => sizeOf(w, 800))).toEqual(["tablet", "tablet", "tablet", "tablet"]);
    expect([1100, 1280, 1920].map((w) => sizeOf(w, 900))).toEqual(["desktop", "desktop", "desktop"]);
  });
  it("is a phone held sideways when the window is short and not wide", () => {
    expect(sizeOf(844, 390)).toBe("phone");
    expect(sizeOf(932, 430)).toBe("phone");
    expect(sizeOf(999, 499)).toBe("phone");
    expect(sizeOf(1000, 499)).toBe("tablet");
    expect(sizeOf(900, 500)).toBe("tablet");
    expect(sizeOf(1280, 400)).toBe("desktop");
  });
  it("keeps a portrait tablet and a landscape one side by side", () => {
    expect([sizeOf(768, 1024), sizeOf(1024, 768)]).toEqual(["tablet", "tablet"]);
  });
});

describe("cardCapacity", () => {
  it("is one on a phone, two on a tablet and four on a desktop (the row that does not fit the map closes its oldest card by itself)", () => {
    expect([cardCapacity("phone"), cardCapacity("tablet"), cardCapacity("desktop")]).toEqual([1, 2, 4]);
  });
});

describe("defaultPanelWidth", () => {
  it("is 680 px on a window of 1280 px and more, so that the Messages tab has its two columns and the tabs their badges, and 480 px on a smaller one", () => {
    expect([defaultPanelWidth(1279), defaultPanelWidth(1280), defaultPanelWidth(1920)]).toEqual([PANEL_DEFAULT, PANEL_DEFAULT_WIDE, PANEL_DEFAULT_WIDE]);
    expect(PANEL_DEFAULT_WIDE).toBe(680);
  });
});
