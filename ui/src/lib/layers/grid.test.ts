import { describe, expect, it } from "vitest";
import { MAX_CELLS, cellCount, gridFeatures, namedStep, type GridFeature, type GridView } from "@/lib/layers/grid";
import { positionToLocator } from "@/lib/locator";

/**
 * The part of the map a window of `w` by `h` pixels shows around a place at a zoom (512 px tiles,
 * Mercator).
 */
function viewAt(lat: number, lon: number, zoom: number, w = 1280, h = 800): GridView {
  const world = 512 * 2 ** zoom;
  const halfLon = ((w / 2) * 360) / world;
  const y = Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
  const latOf = (at: number) => ((2 * Math.atan(Math.exp(at)) - Math.PI / 2) * 180) / Math.PI;
  const dy = ((h / 2) * 2 * Math.PI) / world;
  return { west: lon - halfLon, east: lon + halfLon, south: latOf(y - dy), north: latOf(y + dy), zoom };
}

const ESPOO = { lat: 60.2231, lon: 24.7152 };
const names = (features: readonly GridFeature[]) =>
  features.flatMap((feature) =>
    feature.geometry.type === "Point" && "name" in feature.properties
      ? [{ name: feature.properties.name, at: feature.geometry.coordinates }]
      : [],
  );
const lines = (features: readonly GridFeature[], rank: 0 | 1) =>
  features.filter((feature) => "rank" in feature.properties && feature.properties.rank === rank);
const inView = (view: GridView, [lon, lat]: [number, number]) =>
  lon >= view.west && lon <= view.east && lat >= view.south && lat <= view.north;

describe("the locator grid", () => {
  it.each([
    [2, "field"],
    [4.5, "field"],
    [5, "square"],
    [8, "square"],
    [9, "square"],
    [10, "subsquare"],
    [15, "subsquare"],
  ] as const)("names the cells at zoom %s by the %s", (zoom, step) => {
    expect(namedStep(viewAt(ESPOO.lat, ESPOO.lon, zoom))).toBe(step);
  });

  it.each([2, 3, 5, 6, 8, 9, 10, 12, 15])(
    "names at most 400 cells at zoom %s, and the cell under the middle of the view has its name in sight",
    (zoom) => {
      const view = viewAt(ESPOO.lat, ESPOO.lon, zoom);
      const shown = names(gridFeatures(view).features);
      expect(shown.length).toBeGreaterThan(0);
      expect(shown.length).toBeLessThanOrEqual(MAX_CELLS);
      const chars = { field: 2, square: 4, subsquare: 6 }[namedStep(view)];
      const middle = positionToLocator(ESPOO.lat, ESPOO.lon).slice(0, chars);
      const own = shown.find((one) => one.name === middle);
      expect(own).toBeDefined();
      expect(inView(view, own?.at ?? [999, 999])).toBe(true);
      for (const one of shown) expect(inView(view, one.at)).toBe(true);
    },
  );

  it("has a name in sight at every zoom from 2 to 15, in steps of a quarter, on a phone and on a wide window, here and at the far ends of the world", () => {
    for (const place of [ESPOO, { lat: -33.9, lon: 18.4 }, { lat: 0.01, lon: -179.99 }, { lat: 71, lon: 179.9 }]) {
      for (const size of [
        [375, 600],
        [2560, 1440],
      ] as const) {
        for (let zoom = 2; zoom <= 15; zoom += 0.25) {
          const view = viewAt(place.lat, place.lon, zoom, ...size);
          const shown = names(gridFeatures(view).features);
          expect(shown.length, `zoom ${zoom} at ${place.lat}, ${place.lon}`).toBeGreaterThan(0);
          expect(shown.length).toBeLessThanOrEqual(MAX_CELLS);
          expect(shown.some((one) => inView(view, one.at))).toBe(true);
        }
      }
    }
  });

  it("gives every cell the name Copy locator gives a place inside it", () => {
    for (const zoom of [2, 5, 8, 9, 10, 15]) {
      const view = viewAt(ESPOO.lat, ESPOO.lon, zoom);
      const chars = { field: 2, square: 4, subsquare: 6 }[namedStep(view)];
      for (const one of names(gridFeatures(view).features)) {
        const [lon, lat] = one.at;
        expect(positionToLocator(lat, lon).slice(0, chars)).toBe(one.name);
      }
    }
  });

  it("is KP for Espoo far out, KP20 from zoom 5 and KP20if from zoom 10, as the locator of 6 characters writes them", () => {
    expect(names(gridFeatures(viewAt(ESPOO.lat, ESPOO.lon, 3)).features).map((one) => one.name)).toContain("KP");
    expect(names(gridFeatures(viewAt(ESPOO.lat, ESPOO.lon, 6)).features).map((one) => one.name)).toContain("KP20");
    expect(positionToLocator(ESPOO.lat, ESPOO.lon)).toBe("KP20if");
    expect(names(gridFeatures(viewAt(ESPOO.lat, ESPOO.lon, 12)).features).map((one) => one.name)).toContain("KP20if");
  });

  it("goes to the next coarser step where the finer would have more than 400 cells", () => {
    const huge = viewAt(ESPOO.lat, ESPOO.lon, 10, 8000, 6000);
    expect(cellCount(huge, "subsquare")).toBeGreaterThan(MAX_CELLS);
    expect(namedStep(huge)).toBe("square");
  });

  it("draws the subsquares' lines without names where squares are named and a subsquare is wide enough to be seen, and not far out", () => {
    for (const zoom of [8, 9]) {
      const features = gridFeatures(viewAt(ESPOO.lat, ESPOO.lon, zoom)).features;
      expect(lines(features, 1).length).toBeGreaterThan(0);
      expect(names(features).every((one) => one.name.length === 4)).toBe(true);
    }
    expect(lines(gridFeatures(viewAt(ESPOO.lat, ESPOO.lon, 5)).features, 1)).toEqual([]);
    expect(lines(gridFeatures(viewAt(ESPOO.lat, ESPOO.lon, 12)).features, 1)).toEqual([]);
  });

  it("draws the lines of the named cells across the view, each on a boundary of the step", () => {
    const view = viewAt(ESPOO.lat, ESPOO.lon, 6);
    const drawn = lines(gridFeatures(view).features, 0);
    expect(drawn.length).toBeGreaterThan(0);
    for (const line of drawn) {
      if (line.geometry.type !== "LineString") continue;
      const [[lon0, lat0] = [0, 0], [lon1, lat1] = [0, 0]] = line.geometry.coordinates;
      if (lon0 === lon1) expect(((lon0 + 180) / 2) % 1).toBeCloseTo(0, 9);
      else expect((lat0 + 90) % 1).toBeCloseTo(0, 9);
      expect(lat1).toBeGreaterThanOrEqual(lat0);
    }
  });

  describe("across the date line", () => {
    /** A longitude in -180..180, as the central copy of the world has it. */
    const wrapped = (lon: number) => ((((lon + 180) % 360) + 360) % 360) - 180;
    const view = (west: number, east: number, zoom = 5): GridView => ({ west, east, south: -44, north: -36, zoom });

    it.each([
      [170, 200],
      [190, 215],
      [-200, -150],
      [-215, -190],
    ])(
      "names the cells of a view from %s to %s in the copy of the world they are seen in, the cell under the middle always",
      (west, east) => {
        const shown = view(west, east);
        const named = names(gridFeatures(shown).features);
        expect(named.length).toBeGreaterThan(0);
        expect(named.length).toBeLessThanOrEqual(MAX_CELLS);
        for (const one of named) {
          expect(inView(shown, one.at)).toBe(true);
          expect(positionToLocator(one.at[1], wrapped(one.at[0])).slice(0, 4)).toBe(one.name);
        }
        const middle = positionToLocator(-40, wrapped((west + east) / 2)).slice(0, 4);
        expect(named.map((one) => one.name)).toContain(middle);
      },
    );

    it("names the cells on both sides of it and draws it as a line", () => {
      const features = gridFeatures(view(170, 200)).features;
      const named = names(features).map((one) => one.name);
      expect(named).toContain(positionToLocator(-40, 179.5).slice(0, 4));
      expect(named).toContain(positionToLocator(-40, -179.5).slice(0, 4));
      const meridians = lines(features, 0).flatMap((one) =>
        one.geometry.type === "LineString" && one.geometry.coordinates[0]?.[0] === one.geometry.coordinates[1]?.[0]
          ? [one.geometry.coordinates[0]?.[0]]
          : [],
      );
      expect(meridians).toContain(180);
      expect(meridians).toContain(190);
    });

    it("counts the 400 cells over both copies of the world together", () => {
      expect(cellCount(view(170, 200), "square")).toBe(
        cellCount(view(170, 180), "square") + cellCount(view(-180, -160), "square"),
      );
      expect(cellCount(view(190, 215), "square")).toBe(cellCount(view(-170, -145), "square"));
    });
  });

  it("is nothing for a view of no size", () => {
    expect(gridFeatures({ west: 10, east: 10, south: 50, north: 51, zoom: 8 }).features).toEqual([]);
  });
});
