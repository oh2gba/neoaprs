import { describe, expect, it } from "vitest";
import { circleBounds, rangeFeatures } from "@/lib/rangecircles";

const EARTH_RADIUS_KM = 6371.0088;

function km(a: number[], b: number[]): number {
  const rad = (d: number) => (d * Math.PI) / 180;
  const [lonA = 0, latA = 0] = a;
  const [lonB = 0, latB = 0] = b;
  const h = Math.sin(rad(latB - latA) / 2) ** 2 + Math.cos(rad(latA)) * Math.cos(rad(latB)) * Math.sin(rad(lonB - lonA) / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
}

describe("the range circle of a digipeater", () => {
  it("is one closed polygon for each, every point at its range from its station", () => {
    const { features } = rangeFeatures([
      { call: "OH2RCH-2", lat: 60.2, lon: 24.9, km: 21.4 },
      { call: "OH2RCH-3", lat: 61, lon: 25, km: 40 },
    ]);
    expect(features.map((f) => f.properties)).toEqual([
      { call: "OH2RCH-2", km: 21.4 },
      { call: "OH2RCH-3", km: 40 },
    ]);
    const ring = features[0]?.geometry.coordinates[0] ?? [];
    expect(ring.length).toBeGreaterThan(60);
    expect(ring[0]).toEqual(ring.at(-1));
    for (const point of ring) expect(km([24.9, 60.2], point)).toBeCloseTo(21.4, 1);
  });

  it("is none for no digipeater and none for a range of nothing", () => {
    expect(rangeFeatures([]).features).toEqual([]);
    expect(rangeFeatures([{ call: "X", lat: 60, lon: 24, km: 0 }]).features).toEqual([]);
  });
});

describe("the box round a range circle", () => {
  it("has the circle's ring inside it, touching all four sides", () => {
    const box = circleBounds({ lat: 60.2, lon: 24.9, km: 21.4 });
    const [[west = 0, south = 0] = [], [east = 0, north = 0] = []] = box ?? [];
    expect(north - south).toBeCloseTo((2 * 21.4) / 111.2, 1); // (a degree of latitude is 111.2 km)
    expect((north + south) / 2).toBeCloseTo(60.2, 2);
    expect((east + west) / 2).toBeCloseTo(24.9, 2);
    expect(east - west).toBeGreaterThan(north - south); // (a degree of longitude is shorter at 60 N)
  });

  it("runs on past the date line instead of wrapping, and is none for a range of nothing", () => {
    const [[west = 0] = [], [east = 0] = []] = circleBounds({ lat: 0, lon: 179.9, km: 100 }) ?? [];
    expect(east).toBeGreaterThan(180);
    expect(east - west).toBeLessThan(2);
    expect(circleBounds({ lat: 60, lon: 24, km: 0 })).toBeNull();
  });
});
