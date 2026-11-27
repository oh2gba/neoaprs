import { describe, expect, it } from "vitest";
import { footprintRings, positionAt, satelliteFeatures, splitLine, wrapLon } from "@/lib/layers/satellite";
import { DURING, satelliteCard, satelliteMark } from "@/test/satellitefixtures";

const at = (iso: string) => Date.parse(iso);

describe("positionAt: the mark between the points the daemon sent", () => {
  it("moves along the line between two points by the time", () => {
    const [lon, lat] = positionAt(satelliteMark().points, DURING + 15000) ?? [NaN, NaN];
    expect(lon).toBeCloseTo(12.3, 5);
    expect(lat).toBeCloseTo(46.1, 5);
  });

  it("goes the short way over the antimeridian and stays inside -180..180", () => {
    const points = [
      { at: "2026-11-28T12:00:00Z", lat: 10, lon: 179 },
      { at: "2026-11-28T12:01:00Z", lat: 12, lon: -179 },
    ];
    const [lon, lat] = positionAt(points, at("2026-11-28T12:00:45Z")) ?? [NaN, NaN];
    expect(lon).toBeCloseTo(-179.5, 5);
    expect(lat).toBeCloseTo(11.5, 5);
  });

  it("stands at the first point before them and is gone after them", () => {
    expect(positionAt(satelliteMark().points, 0)).toEqual([9.89, 44.83]);
    expect(positionAt(satelliteMark().points, DURING + 3600000)).toBeNull();
    expect(positionAt([], DURING)).toBeNull();
  });
});

describe("splitLine: a track over the antimeridian", () => {
  it("is cut into two pieces that end and begin on the edge at the same latitude", () => {
    const pieces = splitLine([
      [170, 0],
      [179, 2],
      [-179, 4],
      [-170, 6],
    ]);
    expect(pieces).toHaveLength(2);
    expect(pieces[0]?.at(-1)?.[0]).toBe(180);
    expect(pieces[1]?.[0]?.[0]).toBe(-180);
    expect(pieces[0]?.at(-1)?.[1]).toBeCloseTo(3, 5);
    expect(pieces[1]?.[0]?.[1]).toBeCloseTo(3, 5);
  });

  it("leaves a line that does not cross whole, and goes west as well as east", () => {
    expect(
      splitLine([
        [10, 0],
        [20, 1],
      ]),
    ).toEqual([
      [
        [10, 0],
        [20, 1],
      ],
    ]);
    const west = splitLine([
      [-175, 0],
      [175, 1],
    ]);
    expect(west.map((piece) => piece[0]?.[0])).toEqual([-175, 180]);
  });
});

const lons = (rings: [number, number][][]): number[] => rings.flat().map(([lon]) => lon);

describe("footprintRings: the horizon circle on the ground", () => {
  it("is one closed ring round a satellite far from the antimeridian and the poles", () => {
    const rings = footprintRings(45, 10, 2250);
    expect(rings).toHaveLength(1);
    const ring = rings[0] ?? [];
    expect(ring[0]).toEqual(ring.at(-1));
    const north = Math.max(...ring.map(([, lat]) => lat));
    expect(north).toBeCloseTo(45 + (2250 / 6371.0088) * (180 / Math.PI), 1);
  });

  it("over the antimeridian is two polygons, each inside -180..180, that meet on the edge", () => {
    const rings = footprintRings(20, 178, 2250);
    expect(rings).toHaveLength(2);
    expect(lons(rings).every((lon) => lon >= -180 && lon <= 180)).toBe(true);
    expect(lons(rings)).toContain(180);
    expect(lons(rings)).toContain(-180);
  });

  it("over a pole runs round the whole world and is closed along the map's edge", () => {
    const rings = footprintRings(80, 30, 2250);
    const all = lons(rings);
    expect(Math.min(...all)).toBe(-180);
    expect(Math.max(...all)).toBe(180);
    expect(Math.max(...rings.flat().map(([, lat]) => lat))).toBeCloseTo(85.0511, 3);
    expect(Math.min(...rings.flat().map(([, lat]) => lat))).toBeGreaterThan(55);
  });

  it("wraps a longitude into -180..180", () => {
    expect([wrapLon(190), wrapLon(-190), wrapLon(180), wrapLon(0)]).toEqual([-170, 170, -180, 0]);
  });
});

describe("satelliteFeatures: what the map draws", () => {
  it("has every mark, and a track and a footprint only for the open cards", () => {
    const drawn = satelliteFeatures([satelliteMark(), satelliteMark(59112, "SONATE-2")], [satelliteCard()], DURING);
    expect(drawn.marks.features.map((f) => [f.properties.name, f.properties.open])).toEqual([
      ["ISS", true],
      ["SONATE-2", false],
    ]);
    expect(drawn.tracks.features.map((f) => f.properties.id)).toEqual([25544]);
    expect(drawn.footprints.features.map((f) => f.properties.id)).toEqual([25544]);
    // the track begins where the mark is now and leaves the points behind it out
    expect(drawn.tracks.features[0]?.geometry.coordinates[0]).toEqual([
      [11.5, 45.7],
      [14.8, 47.2],
    ]);
  });

  it("draws nothing of a satellite whose points have run out", () => {
    const drawn = satelliteFeatures([satelliteMark()], [satelliteCard()], DURING + 3600000);
    expect(drawn.marks.features).toEqual([]);
    expect(drawn.tracks.features).toEqual([]);
  });
});
