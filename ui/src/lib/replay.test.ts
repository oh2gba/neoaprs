import { describe, expect, it } from "vitest";
import { placesAt, replayClock, replayData, trailAt, trailLines, trailMinutes } from "@/lib/replay";
import type { PositionHistoryMessage } from "@/protocol/protocol";

const START = "2026-10-21T09:00:00Z";
const T0 = Date.parse(START);
const MIN = 60_000;
const at = (minutes: number): string => new Date(T0 + minutes * MIN).toISOString().replace(".000", "");

/** A span of three hours: a car that drives (positions 2 min apart, then a gap of an hour), a digipeater heard once, and a station with nothing (not drawn). */
function message(): PositionHistoryMessage {
  return {
    type: "position_history",
    hours: 3,
    start: START,
    stations: {
      "OH2RDG-9": [
        [at(10), 60.0, 25.0],
        [at(12), 60.02, 25.0],
        [at(14), 60.04, 25.02],
        [at(74), 60.1, 25.1],
        [at(76), 60.12, 25.1],
      ],
      "OH2RCH-2": [[at(30), 60.3, 24.7]],
      EMPTY: [],
    },
  };
}

describe("the replay's data", () => {
  it("has the span's start and end and the tracks with their times as numbers, the empty ones left out", () => {
    const data = replayData(message());
    expect([data.start, data.end, data.hours]).toEqual([T0, T0 + 3 * 60 * MIN, 3]);
    expect(data.tracks.map((track) => track.call)).toEqual(["OH2RDG-9", "OH2RCH-2"]);
    expect(data.tracks[0]?.points[1]).toEqual([T0 + 12 * MIN, 60.02, 25.0]);
  });
});

describe("where the stations are", () => {
  const data = replayData(message());
  const place = (minutes: number) => Object.fromEntries(placesAt(data, T0 + minutes * MIN).map(([call, lat, lon]) => [call, [lat, lon]]));

  it("shows a station from its first position on, and none before", () => {
    expect(place(5)).toEqual({});
    expect(place(10)).toEqual({ "OH2RDG-9": [60.0, 25.0] });
    expect(Object.keys(place(30))).toEqual(["OH2RDG-9", "OH2RCH-2"]);
  });

  it("moves a station along the line between two positions near in time", () => {
    const [lat, lon] = place(13)["OH2RDG-9"] ?? [];
    expect(lat).toBeCloseTo(60.03, 6);
    expect(lon).toBeCloseTo(25.01, 6);
  });

  it("keeps a station where it was across a long gap, then at its last position to the end", () => {
    expect(place(40)["OH2RDG-9"]).toEqual([60.04, 25.02]);
    expect(place(74)["OH2RDG-9"]).toEqual([60.1, 25.1]);
    expect(place(179)["OH2RDG-9"]).toEqual([60.12, 25.1]);
    expect(place(179)["OH2RCH-2"]).toEqual([60.3, 24.7]);
  });

  it("has the trail up to the time, ending where the station is", () => {
    const car = data.tracks[0];
    if (!car) throw new Error("no track");
    expect(trailAt(car, T0 + 5 * MIN)).toEqual([]);
    const trail = trailAt(car, T0 + 13 * MIN);
    expect(trail.map(([t]) => (t - T0) / MIN)).toEqual([10, 12, 13]);
    expect(trailAt(car, T0 + 40 * MIN).map(([t]) => (t - T0) / MIN)).toEqual([10, 12, 14]); // (waiting where it was)
    expect(trailAt(car, T0 + 100 * MIN).map(([t]) => (t - T0) / MIN)).toEqual([10, 12, 14, 74, 76]);
  });
});

describe("the trails' lines", () => {
  it("fade behind the station over a quarter of the span, the newest stretch whole", () => {
    expect(trailMinutes(3)).toBe(45);
    const lines = trailLines(replayData(message()), T0 + 75 * MIN);
    const car = lines.features.filter((f) => f.properties.call === "OH2RDG-9");
    expect(car.map((f) => f.properties.opacity)).toEqual([0.15, 1]); // (the drive of an hour ago faint, joined as one line; the last minute whole)
    expect(car[0]?.geometry.coordinates).toHaveLength(4);
    expect(car.flatMap((f) => f.geometry.coordinates).at(-1)).toEqual([25.1, 60.11]);
    expect(lines.features.some((f) => f.properties.call === "OH2RCH-2")).toBe(false); // (one position: no line)
  });

  it("are none before anyone is heard", () => {
    expect(trailLines(replayData(message()), T0).features).toEqual([]);
  });
});

describe("the clock of the bar", () => {
  it("is the time of day, with the date when the span crosses midnight", () => {
    const t = new Date(2026, 9, 21, 9, 5, 7).getTime();
    const sameDay = [new Date(2026, 9, 21, 6).getTime(), new Date(2026, 9, 21, 12).getTime()] as const;
    const twoDays = [new Date(2026, 9, 20, 22).getTime(), new Date(2026, 9, 21, 22).getTime()] as const;
    expect(replayClock(t, ...sameDay)).toBe("09:05:07");
    expect(replayClock(t, ...twoDays)).toBe("10-21 09:05:07");
  });
});
