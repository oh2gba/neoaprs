import { describe, expect, it } from "vitest";
import { isMoving, speedPoints, tripHours, tripStart } from "@/lib/speed";
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

  it("is not a station that sits still on both sides of the date line", () => {
    const still = station("ZK1AAA", {
      track: [
        [ago(900), 0.0, 179.9999],
        [ago(600), 0.0, -179.9999],
        [ago(300), 0.0, 179.9999],
      ],
    });
    expect(isMoving(still, NOW)).toBe(false);
    const driving = station("ZK1BBB", {
      track: [
        [ago(900), 0.0, 179.99],
        [ago(300), 0.0, -179.99],
      ],
    });
    expect(isMoving(driving, NOW)).toBe(true);
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

describe("speed: the trip the graph spans", () => {
  const car = (oldest: number) =>
    station("OH2ZMA-9", {
      speed_kmh: 50,
      track: [
        [ago(oldest), 60.17, 24.94],
        [ago(60), 60.2, 24.95],
      ],
    });

  it("begins at the oldest point of the station's track, the trail the map draws, and the daemon is asked for the whole hours that cover it", () => {
    expect(tripStart(car(90 * 60), NOW)).toBe(NOW - 90 * 60_000);
    expect(tripHours(car(90 * 60), NOW)).toBe(2);
    expect(tripHours(car(3 * HOUR), NOW)).toBe(3);
  });

  it("is a quarter of an hour at least, for a short track or none yet, and a week at most", () => {
    expect(tripStart(car(120), NOW)).toBe(NOW - 15 * 60_000);
    expect(tripStart(station("OH2ZMA-9", { speed_kmh: 50, track: [] }), NOW)).toBe(NOW - 15 * 60_000);
    expect(tripHours(car(120), NOW)).toBe(1);
    expect(tripStart(car(10 * 24 * HOUR), NOW)).toBe(NOW - 168 * HOUR * 1000);
    expect(tripHours(car(10 * 24 * HOUR), NOW)).toBe(168);
  });
});

describe("speed: the line of the graph", () => {
  const from = NOW - 2 * HOUR * 1000;

  it("is the trip to now, with no point before the answer came", () => {
    expect(speedPoints(null, from, NOW)).toEqual({ from, to: NOW, points: [] });
  });

  it("has a point for each speed of the answer since the trip began, at its time (the answer's whole hours may go back further)", () => {
    const series = {
      type: "speed_series" as const,
      call: "OH2ZMA-9",
      hours: 3,
      points: [[ago(150 * 60), 30] as [string, number], [ago(HOUR), 66.7] as [string, number], [ago(60), 0] as [string, number]],
    };
    expect(speedPoints(series, from, NOW).points).toEqual([
      { t: NOW - HOUR * 1000, v: 66.7 },
      { t: NOW - 60_000, v: 0 },
    ]);
  });
});
