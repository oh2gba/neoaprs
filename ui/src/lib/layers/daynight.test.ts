import { describe, expect, it } from "vitest";
import {
  MAX_LAT,
  SUN_DOWN,
  TWILIGHT_END,
  dayNightFeatures,
  sunAt,
  type DayNightCollection,
  type Sun,
} from "@/lib/layers/daynight";

const at = (month: number, day: number, hour = 0, minute = 0): number => Date.UTC(2026, month - 1, day, hour, minute);

/** The sun's altitude above the horizon at a place, the check of the shape of the night. */
function sunAltitude(sun: Sun, lat: number, lon: number): number {
  const rad = Math.PI / 180;
  const sinAlt =
    Math.sin(lat * rad) * Math.sin(sun.lat * rad) +
    Math.cos(lat * rad) * Math.cos(sun.lat * rad) * Math.cos((lon - sun.lon) * rad);
  return Math.asin(Math.max(-1, Math.min(1, sinAlt))) * (180 / Math.PI);
}
type Ring = number[][];
const rings = (collection: DayNightCollection, depth: "twilight" | "night"): Ring[] =>
  collection.features
    .find((one) => one.properties.depth === depth)
    ?.geometry.coordinates.flatMap((polygon) => polygon) ?? [];
const parts = (collection: DayNightCollection, depth: "twilight" | "night"): number => rings(collection, depth).length;
const points = (collection: DayNightCollection, depth: "twilight" | "night"): number[][] =>
  rings(collection, depth).flat();

function within(ring: Ring, lat: number, lon: number): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [lonI = 0, latI = 0] = ring[i] ?? [];
    const [lonJ = 0, latJ = 0] = ring[j] ?? [];
    if (latI > lat !== latJ > lat && lon < ((lonJ - lonI) * (lat - latI)) / (latJ - latI) + lonI) inside = !inside;
  }
  return inside;
}
const inside = (collection: DayNightCollection, depth: "twilight" | "night", lat: number, lon: number): boolean =>
  rings(collection, depth).some((ring) => within(ring, lat, lon));

describe("the sun", () => {
  it("puts the sun over the equator at the equinoxes", () => {
    expect(Math.abs(sunAt(at(3, 20, 14, 46)).lat)).toBeLessThan(0.05);
    expect(Math.abs(sunAt(at(9, 23, 0, 5)).lat)).toBeLessThan(0.05);
  });

  it("puts the sun over the tropics at the solstices", () => {
    const june = sunAt(at(6, 21, 8, 24));
    expect(june.lat).toBeCloseTo(23.44, 1);
    expect(Math.abs(june.lon - 54.45)).toBeLessThan(0.2);
    const december = sunAt(at(12, 21, 20, 50));
    expect(december.lat).toBeCloseTo(-23.44, 1);
    expect(Math.abs(december.lon + 132.94)).toBeLessThan(0.2);
  });

  it("gives the sun's longitude from the clock, across the date line", () => {
    expect(Math.abs(sunAt(at(3, 20, 12)).lon - 1.86)).toBeLessThan(0.2);
    expect(Math.abs(sunAt(at(12, 21, 0)).lon - 179.46)).toBeLessThan(0.2);
    expect(Math.abs(sunAt(at(6, 21, 0)).lon + 179.57)).toBeLessThan(0.2);
    for (let hour = 0; hour < 48; hour++) {
      const { lon } = sunAt(at(6, 21, hour));
      expect(lon).toBeGreaterThan(-180);
      expect(lon).toBeLessThanOrEqual(180);
    }
  });
});

interface Event {
  place: string;
  lat: number;
  lon: number;
  at: number;
  rises: boolean;
}
const PLACES = {
  Helsinki: [60.17, 24.94],
  Frankfurt: [50.11, 8.68],
  Sydney: [-33.87, 151.21],
  Suva: [-18.14, 178.44],
} as const;
const event = (place: keyof typeof PLACES, ms: number, rises: boolean): Event => ({
  place,
  lat: PLACES[place][0],
  lon: PLACES[place][1],
  at: ms,
  rises,
});

/** Three minutes before and after, the place is on the right side of the edge. */
function expectEdge(row: Event, depth: "twilight" | "night", limit: number): void {
  const label = `${row.place} ${new Date(row.at).toISOString()}`;
  for (const [offset, dark] of [
    [-3, row.rises],
    [3, !row.rises],
  ] as const) {
    const ms = row.at + offset * 60000;
    expect(inside(dayNightFeatures(ms), depth, row.lat, row.lon), `${label} ${offset}`).toBe(dark);
    expect(sunAltitude(sunAt(ms), row.lat, row.lon) < limit, `${label} ${offset} altitude`).toBe(dark);
  }
}

describe("the edge of the shade", () => {
  it("agrees with sunrise and sunset at three places at both solstices to within three minutes", () => {
    const rows = [
      event("Helsinki", at(6, 21, 0, 54), true),
      event("Helsinki", at(6, 21, 19, 50), false),
      event("Helsinki", at(12, 21, 7, 24), true),
      event("Helsinki", at(12, 21, 13, 13), false),
      event("Frankfurt", at(6, 21, 3, 15), true),
      event("Frankfurt", at(6, 21, 19, 39), false),
      event("Frankfurt", at(12, 21, 7, 22), true),
      event("Frankfurt", at(12, 21, 15, 25), false),
      event("Sydney", at(6, 20, 21, 0), true),
      event("Sydney", at(6, 21, 6, 54), false),
      event("Sydney", at(12, 20, 18, 41), true),
      event("Sydney", at(12, 21, 9, 5), false),
    ];
    for (const row of rows) expectEdge(row, "twilight", SUN_DOWN);
  });

  it("agrees with the end of civil twilight", () => {
    const rows = [
      event("Frankfurt", at(6, 21, 2, 30), true),
      event("Frankfurt", at(6, 21, 20, 24), false),
      event("Frankfurt", at(12, 21, 6, 43), true),
      event("Frankfurt", at(12, 21, 16, 4), false),
      event("Suva", at(12, 20, 17, 4), true),
      event("Suva", at(12, 21, 7, 5), false),
    ];
    for (const row of rows) expectEdge(row, "night", TWILIGHT_END);
  });

  it("has no night near the pole in summer", () => {
    const june = dayNightFeatures(at(6, 21, 8, 24));
    expect(Math.max(...points(june, "night").map(([, lat = 0]) => lat))).toBeLessThan(60.6);
    expect(Math.max(...points(june, "twilight").map(([, lat = 0]) => lat))).toBeLessThan(65.8);
    for (const lon of [-179.9, 0, 90]) {
      expect(inside(june, "twilight", -80, lon)).toBe(true);
      expect(inside(june, "night", -80, lon)).toBe(true);
    }
    const december = dayNightFeatures(at(12, 21, 20, 50));
    expect(Math.min(...points(december, "night").map(([, lat = 0]) => lat))).toBeGreaterThan(-60.6);
    expect(Math.min(...points(december, "twilight").map(([, lat = 0]) => lat))).toBeGreaterThan(-65.8);
    for (const lon of [-179.9, 0, 90]) {
      expect(inside(december, "twilight", 80, lon)).toBe(true);
      expect(inside(december, "night", 80, lon)).toBe(true);
    }
  });

  it("leaves both poles out of the night at an equinox", () => {
    const ms = at(3, 20, 14, 46);
    const night = dayNightFeatures(ms);
    expect(Math.max(...points(night, "night").map(([, lat = 0]) => Math.abs(lat)))).toBeLessThan(84.2);
    const antisolar = sunAt(ms).lon + 180;
    for (const lon of [antisolar, antisolar + 80, antisolar - 80]) {
      const wrapped = ((((lon + 180) % 360) + 360) % 360) - 180;
      expect(inside(night, "night", 0, wrapped)).toBe(true);
    }
    expect(inside(night, "night", 0, sunAt(ms).lon)).toBe(false);
  });

  it("shades both sides of the date line as one night", () => {
    const night = dayNightFeatures(at(3, 20, 12));
    expect(inside(night, "night", 0, 179.9)).toBe(true);
    expect(inside(night, "night", 0, -179.9)).toBe(true);
    const longitudes = points(night, "night").map(([lon = 0]) => lon);
    expect(Math.min(...longitudes)).toBe(-180);
    expect(Math.max(...longitudes)).toBe(180);
    expect(parts(night, "night")).toBe(2);
    const early = dayNightFeatures(at(3, 20, 0));
    const earlyLongitudes = points(early, "night").map(([lon = 0]) => lon);
    expect(parts(early, "night")).toBe(1);
    expect(Math.min(...earlyLongitudes)).toBeGreaterThan(-180);
    expect(Math.max(...earlyLongitudes)).toBeLessThan(180);
  });

  it("has closed rings on the map's own latitudes, and not too many points", () => {
    for (const [month, day] of [
      [6, 21],
      [3, 20],
    ] as const) {
      for (let hour = 0; hour < 24; hour++) {
        const collection = dayNightFeatures(at(month, day, hour));
        for (const depth of ["twilight", "night"] as const) {
          for (const ring of rings(collection, depth)) expect(ring[0]).toEqual(ring[ring.length - 1]);
          for (const [lon = 0, lat = 0] of points(collection, depth)) {
            expect(Math.abs(lat)).toBeLessThanOrEqual(MAX_LAT);
            expect(Math.abs(lon)).toBeLessThanOrEqual(180);
          }
          expect(points(collection, depth).length).toBeLessThanOrEqual(4000);
        }
      }
    }
  });
});

/** The longitudes where the shade's edge crosses the equator, not counting the date line. */
function equatorEdges(ms: number): number[] {
  const found: number[] = [];
  for (const ring of rings(dayNightFeatures(ms), "twilight")) {
    for (let i = 1; i < ring.length; i++) {
      const [lonA = 0, latA = 0] = ring[i - 1] ?? [];
      const [lonB = 0, latB = 0] = ring[i] ?? [];
      if (latA < 0 !== latB < 0 && Math.abs(lonA) < 179.99)
        found.push(lonA + ((lonB - lonA) * (0 - latA)) / (latB - latA));
    }
  }
  return found.sort((a, b) => a - b);
}

describe("the edge on the equator", () => {
  it("draws a steep edge at an equinox without a staircase", () => {
    const ms = at(3, 20, 14, 46);
    const sun = sunAt(ms);
    const edges = equatorEdges(ms);
    for (const side of [-1, 1]) {
      let [dark, lit] = [sun.lon + side * 100, sun.lon + side * 80];
      for (let i = 0; i < 40; i++) {
        const middle = (dark + lit) / 2;
        if (sunAltitude(sun, 0, middle) < SUN_DOWN) dark = middle;
        else lit = middle;
      }
      const truth = ((((dark + 180) % 360) + 360) % 360) - 180;
      expect(Math.min(...edges.map((edge) => Math.abs(edge - truth))), `side ${side}`).toBeLessThan(0.1);
    }
  });

  it("moves fifteen degrees an hour", () => {
    const [, eastAt12 = 0] = equatorEdges(at(6, 21, 12));
    const [, eastAt13 = 0] = equatorEdges(at(6, 21, 13));
    expect(Math.abs(eastAt12 - eastAt13 - 15)).toBeLessThan(0.1);
    const [, eastAt1201 = 0] = equatorEdges(at(6, 21, 12, 1));
    expect(Math.abs(eastAt12 - eastAt1201 - 0.25)).toBeLessThan(0.02);
  });
});
