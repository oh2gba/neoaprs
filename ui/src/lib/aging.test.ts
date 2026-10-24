import { describe, expect, it } from "vitest";
import {
  FADE_SPAN_NEVER_SEC,
  MARKER_STEPS,
  TRAIL_OLDEST,
  TRAIL_STEPS,
  DEFAULT_TIMEOUT_MIN,
  fadeFraction,
  markerStep,
  timeoutMin,
  timedOut,
  trailOpacity,
  type Aging,
} from "@/lib/aging";
import { NOW, ago, station } from "@/test/fixtures";

const aging = (defaultMin: number): Aging => ({ defaultMin });

describe("DEFAULT_TIMEOUT_MIN", () => {
  it("is three hours, fixed", () => {
    expect(DEFAULT_TIMEOUT_MIN).toBe(180);
  });
});

describe("timeoutMin", () => {
  it("is the same for every station, and never for our own station and our own objects", () => {
    expect(timeoutMin(aging(60), station("OH2PU-9"))).toBe(60);
    expect(timeoutMin(aging(60), station("OH2XYZ"))).toBe(60);
    expect(timeoutMin(aging(0), station("OH2XYZ"))).toBe(0);
    expect(timeoutMin(aging(60), station("ME", { is_me: true }))).toBe(0);
    expect(timeoutMin(aging(60), station("MINE", { kind: "object", own: true }))).toBe(0);
  });
});

describe("timedOut", () => {
  it("is a position older than the timeout of the station", () => {
    const old = station("A", { last_position_at: ago(61 * 60) });
    expect(timedOut(aging(60), old, NOW)).toBe(true);
    expect(timedOut(aging(60), station("A", { last_position_at: ago(59 * 60) }), NOW)).toBe(false);
    expect(timedOut(aging(120), old, NOW)).toBe(false);
  });
  it("is never with timeout 0, for a station without a position, or for our own station", () => {
    const old = station("A", { last_position_at: ago(10 * 86400) });
    expect(timedOut(aging(0), old, NOW)).toBe(false);
    expect(timedOut(aging(60), station("A", { lat: null, lon: null, last_position_at: null, last_heard: ago(86400) }), NOW)).toBe(false);
    expect(timedOut(aging(60), station("ME", { is_me: true, last_position_at: ago(86400) }), NOW)).toBe(false);
    expect(timedOut(aging(60), station("MINE", { kind: "object", own: true, last_position_at: ago(86400) }), NOW)).toBe(false);
  });
  it("takes the last packet for a position that has no time", () => {
    expect(timedOut(aging(60), station("A", { last_position_at: null, last_heard: ago(3 * 3600) }), NOW)).toBe(true);
  });
});

describe("fadeFraction", () => {
  it("is the age as a part of the timeout, between 0 and 1", () => {
    expect(fadeFraction(0, 60)).toBe(0);
    expect(fadeFraction(1800, 60)).toBe(0.5);
    expect(fadeFraction(7200, 60)).toBe(1);
  });
  it("measures a station that never times out against a day", () => {
    expect(fadeFraction(FADE_SPAN_NEVER_SEC / 2, 0)).toBe(0.5);
    expect(fadeFraction(10 * FADE_SPAN_NEVER_SEC, 0)).toBe(1);
  });
});

describe("trailOpacity", () => {
  it("is full for the newest, TRAIL_OLDEST at the timeout and beyond", () => {
    expect(trailOpacity(0, 60)).toBe(1);
    expect(trailOpacity(3599, 60)).toBe(TRAIL_OLDEST);
    expect(trailOpacity(3600, 60)).toBe(TRAIL_OLDEST);
    expect(trailOpacity(1e9, 60)).toBe(TRAIL_OLDEST);
  });
  it("goes down in TRAIL_STEPS even steps and never up with the age", () => {
    const seen = new Set<number>();
    let before = 1;
    for (let age = 0; age <= 3600; age += 10) {
      const opacity = trailOpacity(age, 60);
      expect(opacity).toBeLessThanOrEqual(before);
      before = opacity;
      seen.add(opacity);
    }
    expect(seen.size).toBe(TRAIL_STEPS);
  });
  it("counts from the timeout of the station: the same age is fainter for a shorter timeout", () => {
    expect(trailOpacity(1200, 30)).toBeLessThan(trailOpacity(1200, 600));
  });
});

describe("markerStep", () => {
  const rules = aging(100);
  it("goes from 0 fresh to the last step just before the timeout, by the last position", () => {
    expect(markerStep(rules, station("A", { last_position_at: ago(60) }), NOW)).toBe(0);
    expect(markerStep(rules, station("A", { last_position_at: ago(60 * 30) }), NOW)).toBe(1);
    expect(markerStep(rules, station("A", { last_position_at: ago(60 * 60) }), NOW)).toBe(2);
    expect(markerStep(rules, station("A", { last_position_at: ago(60 * 99) }), NOW)).toBe(MARKER_STEPS - 1);
    expect(markerStep(rules, station("A", { last_position_at: ago(86400) }), NOW)).toBe(MARKER_STEPS - 1);
  });
  it("never fades our own station", () => {
    expect(markerStep(rules, station("ME", { is_me: true, last_position_at: ago(86400) }), NOW)).toBe(0);
    expect(markerStep(rules, station("MINE", { kind: "object", own: true, last_position_at: ago(86400) }), NOW)).toBe(0);
  });
});
