import { describe, expect, it } from "vitest";
import {
  TRAIL_GAP_SEC,
  TRAIL_MAX_AGE_SEC,
  TRAIL_MAX_POINTS,
  forgetTrails,
  growTrails,
  trailKey,
  trailLines,
  type TrailPoint,
  type Trails,
} from "@/lib/layers/trail";
import { NOW, ago } from "@/test/fixtures";
import { aircraft, layerThings, ship } from "@/test/layerfixtures";

const KEY = trailKey("aircraft", "a");

describe("growTrails", () => {
  it("adds a point when a thing's place changed and none when it did not", () => {
    const trails: Trails = new Map();
    growTrails(trails, [layerThings("aircraft", [aircraft({ id: "a", lat: 60.1, lon: 24.1, at: ago(20) })])], NOW);
    growTrails(trails, [layerThings("aircraft", [aircraft({ id: "a", lat: 60.1, lon: 24.1, at: ago(10) })])], NOW);
    expect(trails.get(KEY)).toHaveLength(1);
    growTrails(trails, [layerThings("aircraft", [aircraft({ id: "a", lat: 60.2, lon: 24.1, at: ago(5) })])], NOW);
    expect(trails.get(KEY)?.map((point) => [point[0], point[1]])).toEqual([
      [24.1, 60.1],
      [24.1, 60.2],
    ]);
  });

  it("keeps the trails of aircraft and of ships apart, each by its id", () => {
    const trails: Trails = new Map();
    growTrails(
      trails,
      [
        layerThings("aircraft", [aircraft({ id: "a", at: ago(1) })]),
        layerThings("ships", [ship({ id: "a", at: ago(1) })]),
      ],
      NOW,
    );
    expect([...trails.keys()].sort()).toEqual(["aircraft:a", "ships:a"]);
  });

  it("drops the points older than 30 minutes and keeps the others", () => {
    const trails: Trails = new Map();
    growTrails(
      trails,
      [layerThings("aircraft", [aircraft({ id: "a", lat: 60.1, at: ago(TRAIL_MAX_AGE_SEC - 1) })])],
      NOW,
    );
    growTrails(trails, [layerThings("aircraft", [aircraft({ id: "a", lat: 60.2, at: ago(1) })])], NOW + 5000);
    expect(trails.get(KEY)).toHaveLength(1);
    expect(trails.get(KEY)?.[0]?.[1]).toBe(60.2);
  });

  it("keeps the last 400 points of a thing", () => {
    const trails: Trails = new Map();
    for (let i = 0; i < TRAIL_MAX_POINTS + 25; i++)
      growTrails(trails, [layerThings("aircraft", [aircraft({ id: "a", lat: 60 + i / 1000, at: ago(1) })])], NOW);
    const points = trails.get(KEY) ?? [];
    expect(points).toHaveLength(TRAIL_MAX_POINTS);
    expect(points.at(-1)?.[1]).toBeCloseTo(60 + (TRAIL_MAX_POINTS + 24) / 1000);
  });

  it("keeps a trail through tables that are empty for a while (the tab hidden), and forgets it only by age", () => {
    const trails: Trails = new Map();
    growTrails(trails, [layerThings("aircraft", [aircraft({ id: "a", lon: 24.1, at: ago(60) })])], NOW);
    growTrails(trails, [layerThings("aircraft", [])], NOW + 1000);
    growTrails(trails, [], NOW + 2000);
    expect(trails.get(KEY)).toHaveLength(1);
    growTrails(trails, [layerThings("aircraft", [aircraft({ id: "a", lon: 24.2, at: ago(-600) })])], NOW + 600_000);
    expect(trails.get(KEY)?.map((point) => point[0])).toEqual([24.1, 24.2]);
    growTrails(trails, [], NOW + (TRAIL_MAX_AGE_SEC + 61) * 1000);
    expect(trails.get(KEY)?.map((point) => point[0])).toEqual([24.2]);
    growTrails(trails, [], NOW + (TRAIL_MAX_AGE_SEC + 700) * 1000);
    expect(trails.size).toBe(0);
  });

  it("takes the points the daemon kept, before the table's own, without a point twice", () => {
    const trails: Trails = new Map();
    const kept = layerThings("aircraft", [aircraft({ id: "a", lon: 24.3, lat: 60.3, at: ago(1) })], {
      trails: [
        {
          id: "a",
          points: [
            [24.1, 60.3, ago(120)],
            [24.2, 60.3, ago(60)],
            [24.3, 60.3, ago(1)],
          ],
        },
      ],
    });
    growTrails(trails, [kept], NOW);
    expect(trails.get(KEY)?.map((point) => point[0])).toEqual([24.1, 24.2, 24.3]);
  });

  it("forgets every trail of a layer the operator switched off", () => {
    const trails: Trails = new Map();
    growTrails(
      trails,
      [layerThings("aircraft", [aircraft({ id: "a", at: ago(1) })]), layerThings("ships", [ship({ at: ago(1) })])],
      NOW,
    );
    forgetTrails(trails, "aircraft");
    expect([...trails.keys()]).toEqual(["ships:230123456"]);
  });
});

describe("trailLines", () => {
  const point = (lon: number, lat: number, secondsAgo: number): TrailPoint => [lon, lat, NOW - secondsAgo * 1000];

  it("is no line for none or one point", () => {
    expect(trailLines(KEY, [], NOW).features).toEqual([]);
    expect(trailLines(KEY, [point(24, 60, 5)], NOW).features).toEqual([]);
  });

  it("draws the points in order, the oldest end the faintest", () => {
    const { features } = trailLines(
      KEY,
      [
        point(24, 60, 1500),
        point(24.1, 60, 1300),
        point(24.2, 60, 1100),
        point(24.3, 60, 900),
        point(24.4, 60, 700),
        point(24.5, 60, 500),
        point(24.6, 60, 300),
        point(24.7, 60, 100),
        point(24.8, 60, 5),
      ],
      NOW,
    );
    expect(features.length).toBeGreaterThan(2);
    expect(features[0]?.geometry.coordinates[0]).toEqual([24, 60]);
    expect(features.at(-1)?.geometry.coordinates.at(-1)).toEqual([24.8, 60]);
    const opacities = features.map((feature) => feature.properties.opacity);
    expect(opacities[0]).toBeLessThan(opacities.at(-1) ?? 0);
    expect(opacities.at(-1)).toBe(1);
  });

  it("draws no line across a gap of more than a few minutes", () => {
    const gap = TRAIL_GAP_SEC + 1;
    const { features } = trailLines(
      KEY,
      [point(24, 60, 600 + gap), point(24.01, 60, 600 + gap - 3), point(25, 61, 500), point(25.01, 61, 497)],
      NOW,
    );
    expect(features.map((feature) => feature.geometry.coordinates)).toEqual([
      [
        [24, 60],
        [24.01, 60],
      ],
      [
        [25, 61],
        [25.01, 61],
      ],
    ]);
  });

  it("joins stretches that are as far apart as the gap allows", () => {
    const { features } = trailLines(KEY, [point(24, 60, 400), point(24.1, 60, 400 - TRAIL_GAP_SEC)], NOW);
    expect(features).toHaveLength(1);
  });
});

describe("trailLines over the date line", () => {
  it("carries the longitude on past 180", () => {
    const points: TrailPoint[] = [
      [179.9, 60, NOW - 120_000],
      [-179.9, 60, NOW - 60_000],
    ];
    const line = trailLines(KEY, points, NOW).features[0]?.geometry.coordinates;
    expect(line).toEqual([
      [179.9, 60],
      [180.1, 60],
    ]);
  });
});
