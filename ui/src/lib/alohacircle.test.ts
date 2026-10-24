import { describe, expect, it } from "vitest";
import { alohaFeatures } from "@/lib/alohacircle";

const EARTH_RADIUS_KM = 6371.0088;

function km(a: [number, number], b: [number, number]): number {
  const rad = (d: number) => (d * Math.PI) / 180;
  const h = Math.sin(rad(b[1] - a[1]) / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(rad(b[0] - a[0]) / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
}

describe("the ring of the ALOHA circle", () => {
  it("is nothing without a position or a radius", () => {
    expect(alohaFeatures(null, 40).features).toEqual([]);
    expect(alohaFeatures({ lat: 60, lon: 24 }, null).features).toEqual([]);
    expect(alohaFeatures({ lat: 60, lon: 24 }, 0).features).toEqual([]);
  });

  it("is a closed line of points, each at the radius from the position", () => {
    const home = { lat: 60.17, lon: 24.94 };
    const [feature] = alohaFeatures(home, 42).features;
    const ring = feature?.geometry.coordinates ?? [];
    expect(ring.length).toBeGreaterThan(60);
    expect(ring[0]).toEqual(ring.at(-1));
    for (const point of ring) expect(km([home.lon, home.lat], point)).toBeCloseTo(42, 1);
    expect(feature?.properties.km).toBe(42);
  });

  it("starts due north of the position", () => {
    const [feature] = alohaFeatures({ lat: 60, lon: 24 }, 111.195).features;
    const [lon, lat] = feature?.geometry.coordinates[0] ?? [0, 0];
    expect(lon).toBeCloseTo(24, 6);
    expect(lat).toBeCloseTo(61, 2);
  });

  it("goes on past the date line instead of wrapping to the other side", () => {
    const [feature] = alohaFeatures({ lat: 0, lon: 179.9 }, 100).features;
    const longitudes = (feature?.geometry.coordinates ?? []).map(([lon]) => lon);
    for (let i = 1; i < longitudes.length; i++) expect(Math.abs((longitudes[i] ?? 0) - (longitudes[i - 1] ?? 0))).toBeLessThan(5);
    expect(Math.max(...longitudes)).toBeGreaterThan(180);
  });
});
