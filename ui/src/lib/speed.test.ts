import { describe, expect, it } from "vitest";
import { isMoving, speedPoints } from "@/lib/speed";
import { NOW, ago, station } from "@/test/fixtures";

const HOUR = 3600;

describe("speed: which station moves", () => {
  it("is one whose speed now is above 0", () => {
    expect(isMoving(station("OH2ZMA-9", { speed_kmh: 40 }), NOW)).toBe(true);
    expect(isMoving(station("OH2ZMA-9", { speed_kmh: 0 }), NOW)).toBe(false);
    expect(isMoving(station("OH2ZMA-9", { speed_kmh: null }), NOW)).toBe(false);
  });

  it("is one whose track of the last 24 hours went more than 100 m, though it stands still now", () => {
    const trip = station("OH2ZMA-9", {
      speed_kmh: 0,
      track: [
        [ago(2 * HOUR), 60.17, 24.94],
        [ago(HOUR), 60.2, 24.95],
        [ago(60), 60.2, 24.95],
      ],
    });
    expect(isMoving(trip, NOW)).toBe(true);
  });

  it("is not a fixed station, whose track gets a point every 5 minutes a few metres apart, nor one that moved only before the 24 hours", () => {
    const fixed = station("OH2RDG", {
      track: [
        [ago(900), 60.2, 24.95],
        [ago(600), 60.20003, 24.95004],
        [ago(300), 60.2, 24.95],
      ],
    });
    expect(isMoving(fixed, NOW)).toBe(false);
    const long = station("OH2ZMA-9", {
      track: [
        [ago(30 * HOUR), 60.0, 24.0],
        [ago(2 * HOUR), 60.2, 24.95],
        [ago(HOUR), 60.2, 24.95],
      ],
    });
    expect(isMoving(long, NOW)).toBe(false);
    expect(isMoving(station("OH2RDG", { track: [] }), NOW)).toBe(false);
  });
});

describe("speed: the line of the graph", () => {
  it("is the last 24 hours to now, with no point before the answer came", () => {
    expect(speedPoints(null, NOW)).toEqual({ from: NOW - 24 * HOUR * 1000, to: NOW, points: [] });
  });

  it("has a point for each speed of the answer, at its time", () => {
    const series = {
      type: "speed_series" as const,
      call: "OH2ZMA-9",
      hours: 24,
      points: [[ago(HOUR), 66.7] as [string, number], [ago(60), 0] as [string, number]],
    };
    expect(speedPoints(series, NOW).points).toEqual([
      { t: NOW - HOUR * 1000, v: 66.7 },
      { t: NOW - 60_000, v: 0 },
    ]);
  });
});
