import { describe, expect, it } from "vitest";
import { EASE_MS } from "@/lib/layers/glide";
import { positionAt, satelliteMarks } from "@/lib/layers/satellite";
import { easedAt, nextEases } from "@/lib/layers/satelliteease";
import type { SatelliteMark } from "@/protocol/protocol";
import { DURING, satelliteMark } from "@/test/satellitefixtures";

/** The ISS's points as a new message has them: `dLat` degrees off the last message's. */
const moved = (dLat: number): SatelliteMark => {
  const mark = satelliteMark();
  return { ...mark, points: mark.points.map((point) => ({ ...point, lat: point.lat + dLat })) };
};

describe("nextEases: a satellite's mark eased onto a new message's points", () => {
  it("starts where the last points had it and ends on the new ones", () => {
    const was = [satelliteMark()];
    const now = [moved(0.006)];
    const eases = nextEases(was, new Map(), now, DURING);
    const at = (ms: number) => satelliteMarks(now, [], ms, (id, place) => easedAt(place, eases.get(id), ms));
    const start = at(DURING).features[0].geometry.coordinates;
    expect(start[1]).toBeCloseTo(positionAt(was[0].points, DURING)?.[1] ?? NaN, 9);
    const end = at(DURING + EASE_MS).features[0].geometry.coordinates;
    expect(end[1]).toBeCloseTo(positionAt(now[0].points, DURING + EASE_MS)?.[1] ?? NaN, 9);
  });

  it("jumps a difference of more than half a degree, and eases nothing for a satellite that is new", () => {
    expect(nextEases([satelliteMark()], new Map(), [moved(2)], DURING).size).toBe(0);
    expect(nextEases([], new Map(), [satelliteMark()], DURING).size).toBe(0);
  });
});
