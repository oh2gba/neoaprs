import { describe, expect, it } from "vitest";
import { EASE_MS, easeOut, glidePosition, nextGlide, reckon, reckoned, type Report } from "@/lib/layers/glide";

const KM_PER_DEG = (6371.0088 * Math.PI) / 180;
const T0 = Date.parse("2026-11-27T12:00:00Z");
const STOP = 20;

const report = (extra: Partial<Report> = {}): Report => ({
  lon: 24.9,
  lat: 60.2,
  atMs: T0,
  courseDeg: 90,
  speedKmh: 360,
  ...extra,
});

describe("reckon: dead reckoning on the sphere", () => {
  it("goes north along a meridian by the distance covered", () => {
    const [lon, lat] = reckon(25, 60, 0, 100, 3600);
    expect(lon).toBeCloseTo(25, 9);
    expect(lat).toBeCloseTo(60 + 100 / KM_PER_DEG, 6);
  });

  it("goes east along the equator by the distance covered", () => {
    const [lon, lat] = reckon(0, 0, 90, KM_PER_DEG, 3600);
    expect(lon).toBeCloseTo(1, 9);
    expect(lat).toBeCloseTo(0, 9);
  });

  it("follows a great circle: due east at 60 N it drifts south of the parallel", () => {
    const [, lat] = reckon(0, 60, 90, 1000, 3600);
    expect(lat).toBeLessThan(60);
    expect(lat).toBeCloseTo(58.79, 1);
  });

  it("crosses the antimeridian into the western longitudes", () => {
    const [lon] = reckon(179.99, 0, 90, KM_PER_DEG, 3600);
    expect(lon).toBeCloseTo(-179.01, 6);
  });
});

describe("reckoned: where a report puts the thing", () => {
  it("is the reported place at the report's time, and carried on after it", () => {
    expect(reckoned(report(), T0, STOP)).toEqual([24.9, 60.2]);
    const [lon, lat] = reckoned(report(), T0 + 10_000, STOP);
    const km = 360 * (10 / 3600);
    expect(lat).toBeCloseTo(60.2, 3);
    expect((lon - 24.9) * KM_PER_DEG * Math.cos((60.2 * Math.PI) / 180)).toBeCloseTo(km, 2);
  });

  it("stops where the reckoning had carried it once the report is older than the stop", () => {
    const atStop = reckoned(report(), T0 + STOP * 1000, STOP);
    expect(reckoned(report(), T0 + STOP * 1000 + 60_000, STOP)).toEqual(atStop);
    expect(atStop[0]).toBeGreaterThan(24.9);
  });

  it("does not move a thing without course, without speed or standing still", () => {
    for (const still of [{ courseDeg: null }, { speedKmh: null }, { speedKmh: 0.4 }])
      expect(reckoned(report(still), T0 + 10_000, STOP)).toEqual([24.9, 60.2]);
  });

  it("does not go back for a report whose time is after the clock", () => {
    expect(reckoned(report(), T0 - 5000, STOP)).toEqual([24.9, 60.2]);
  });
});

describe("easeOut", () => {
  it("runs from 0 to 1, fast first, and holds outside", () => {
    expect(easeOut(-1)).toBe(0);
    expect(easeOut(0)).toBe(0);
    expect(easeOut(0.5)).toBeCloseTo(0.875, 9);
    expect(easeOut(1)).toBe(1);
    expect(easeOut(3)).toBe(1);
  });
});

describe("nextGlide: onto a new report without a jump", () => {
  it("draws the first report at once", () => {
    const glide = nextGlide(undefined, report(), T0, STOP);
    expect(glidePosition(glide, T0, STOP)).toEqual([24.9, 60.2]);
  });

  it("keeps the glide for the same report", () => {
    const glide = nextGlide(undefined, report(), T0, STOP);
    expect(nextGlide(glide, report(), T0 + 5000, STOP)).toBe(glide);
  });

  it("starts where the thing was drawn and ends on the new report's reckoning", () => {
    const first = nextGlide(undefined, report(), T0, STOP);
    const now = T0 + 5000;
    const before = glidePosition(first, now, STOP);
    // the new report puts it 200 m further north than the reckoning had it
    const next = report({ atMs: now, lon: before[0], lat: before[1] + 0.2 / KM_PER_DEG });
    const glide = nextGlide(first, next, now, STOP);
    const start = glidePosition(glide, now, STOP);
    expect(start[0]).toBeCloseTo(before[0], 9);
    expect(start[1]).toBeCloseTo(before[1], 9);
    const later = now + EASE_MS;
    expect(glidePosition(glide, later, STOP)).toEqual(reckoned(next, later, STOP));
    const half = glidePosition(glide, now + EASE_MS / 2, STOP)[1] - reckoned(next, now + EASE_MS / 2, STOP)[1];
    expect(half).toBeLessThan(0);
    expect(half).toBeGreaterThan(-0.2 / KM_PER_DEG);
  });

  it("eases across the antimeridian the short way", () => {
    const first = nextGlide(undefined, report({ lon: 179.9999, courseDeg: null }), T0, STOP);
    const glide = nextGlide(first, report({ lon: -179.9999, courseDeg: null, atMs: T0 + 5000 }), T0 + 5000, STOP);
    const [lon] = glidePosition(glide, T0 + 5000 + EASE_MS / 2, STOP);
    expect(Math.abs(lon)).toBeGreaterThan(179.999);
  });

  it("jumps to a report far from where the thing was drawn", () => {
    const first = nextGlide(undefined, report(), T0, STOP);
    const far = report({ lon: 26.5, atMs: T0 + 5000 });
    const glide = nextGlide(first, far, T0 + 5000, STOP);
    const [lon, lat] = glidePosition(glide, T0 + 5000, STOP);
    expect(lon).toBeCloseTo(26.5, 9);
    expect(lat).toBeCloseTo(60.2, 9);
  });
});
