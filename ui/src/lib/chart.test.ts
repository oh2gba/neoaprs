import { describe, expect, it } from "vitest";
import {
  bandPath,
  bars,
  extent,
  gapLimit,
  lastIndex,
  linePath,
  linearScale,
  nearestIndex,
  niceTicks,
  tickDecimals,
  timeTicks,
  usualGap,
  type Point,
} from "@/lib/chart";

const MIN = 60_000;
const at = (minutes: number, v: number | null): Point => ({ t: minutes * MIN, v });
const identity = (n: number): number => n;

describe("linearScale", () => {
  it("maps the ends of the domain to the ends of the range, also backwards", () => {
    const up = linearScale([0, 10], [100, 200]);
    expect([up(0), up(5), up(10)]).toEqual([100, 150, 200]);
    const flipped = linearScale([-5, 5], [90, 10]);
    expect([flipped(-5), flipped(0), flipped(5)]).toEqual([90, 50, 10]);
  });

  it("puts a domain of no width in the middle", () => {
    expect(linearScale([3, 3], [0, 100])(3)).toBe(50);
  });
});

describe("extent", () => {
  it("is the lowest and the highest, and includes 0 when asked", () => {
    expect(extent([4, 9, 6], false)).toEqual([4, 9]);
    expect(extent([4, 9, 6], true)).toEqual([0, 9]);
    expect(extent([-3, -1], true)).toEqual([-3, 0]);
  });

  it("gives a span to a series with one value, with none and with all zeros", () => {
    expect(extent([5], false)).toEqual([4, 6]);
    expect(extent([], false)).toEqual([0, 1]);
    expect(extent([0, 0], true)).toEqual([-1, 1]);
  });
});

describe("niceTicks", () => {
  it("steps by 1, 2 or 5 times a power of ten and widens the ends to ticks", () => {
    expect(niceTicks(0, 10, 4)).toMatchObject({ min: 0, max: 10, step: 5, ticks: [0, 5, 10] });
    expect(niceTicks(8.9, 11.2, 3).ticks).toEqual([8, 9, 10, 11, 12]);
    expect(niceTicks(1010.2, 1014.8, 3).ticks).toEqual([1010, 1012, 1014, 1016]);
    expect(niceTicks(-20.6, 3, 4)).toMatchObject({ min: -30, max: 10 });
  });

  it("has no float noise in its ticks", () => {
    expect(niceTicks(0, 0.6, 3).ticks).toEqual([0, 0.2, 0.4, 0.6]);
  });

  it("covers a span of no width", () => {
    const t = niceTicks(5, 5, 3);
    expect(t.min).toBeLessThanOrEqual(5);
    expect(t.max).toBeGreaterThanOrEqual(5);
  });

  it("says how many decimals a step needs", () => {
    expect([5, 1, 0.5, 0.2, 0.05].map(tickDecimals)).toEqual([0, 0, 1, 1, 2]);
  });
});

describe("timeTicks", () => {
  const local = (d: number, h: number): number => new Date(2026, 9, d, h, 0, 0).getTime();

  it("puts a tick on every 6th hour of the viewer's clock for a day", () => {
    const ticks = timeTicks(local(20, 14), local(21, 14));
    expect(ticks.map((t) => t.label)).toEqual(["18:00", "00:00", "06:00", "12:00"]);
    expect(ticks.every((t, i) => i === 0 || t.at - (ticks[i - 1]?.at ?? 0) === 6 * 3_600_000)).toBe(true);
  });

  it("puts a tick on each midnight for a week and names the day", () => {
    const ticks = timeTicks(local(14, 12), local(21, 12));
    expect(ticks).toHaveLength(7);
    expect(ticks[0]?.label).toBe("Thu 15");
    expect(ticks[6]?.label).toBe("Wed 21");
  });

  it("uses finer steps for a short span", () => {
    expect(timeTicks(local(21, 10), local(21, 13)).map((t) => t.label)).toEqual(["10:00", "11:00", "12:00", "13:00"]);
  });
});

describe("the gaps in a line", () => {
  it("finds the usual spacing and allows three times it, 20 minutes at least", () => {
    const ten = [at(0, 1), at(10, 1), at(20, 1), at(30, 1)];
    expect(usualGap(ten)).toBe(10 * MIN);
    expect(gapLimit(ten)).toBe(30 * MIN);
    expect(gapLimit([at(0, 1), at(1, 1)])).toBe(20 * MIN);
    expect(usualGap([at(0, 1)])).toBe(0);
  });
});

describe("linePath", () => {
  it("joins the points with a line", () => {
    expect(linePath([at(0, 1), at(1, 3), at(2, 2)], (t) => t / MIN, identity, 5 * MIN)).toBe("M0,1L1,3L2,2");
  });

  it("breaks the line at a missing value and at a silence longer than the limit", () => {
    const path = linePath([at(0, 1), at(1, 2), at(2, null), at(3, 3), at(4, 4), at(60, 5), at(61, 6)], (t) => t / MIN, identity, 5 * MIN);
    expect(path).toBe("M0,1L1,2M3,3L4,4M60,5L61,6");
  });

  it("draws a lone point as a dot of no length, and nothing for no value", () => {
    expect(linePath([at(5, 2)], (t) => t / MIN, identity, 5 * MIN)).toBe("M5,2h0");
    expect(linePath([at(5, null)], (t) => t / MIN, identity, 5 * MIN)).toBe("");
    expect(linePath([], identity, identity, 1)).toBe("");
  });

  it("rounds the numbers to two decimals", () => {
    expect(linePath([at(0, 1.23456), at(1, 2)], () => 0.123456, identity, 5 * MIN)).toBe("M0.12,1.23L0.12,2");
  });
});

describe("bandPath", () => {
  it("closes a polygon between the two series where both have a value at the same time", () => {
    const wind = [at(0, 2), at(1, 3), at(2, 4)];
    const gust = [at(0, 5), at(1, 7), at(2, 6)];
    expect(bandPath(wind, gust, (t) => t / MIN, identity, 5 * MIN)).toBe("M0,5L1,7L2,6L2,4L1,3L0,2Z");
  });

  it("leaves out what is missing in either and what is a single point", () => {
    const wind = [at(0, 2), at(1, null), at(2, 4), at(3, 5), at(4, 5)];
    const gust = [at(0, 5), at(1, 7), at(2, null), at(3, 8), at(4, 9)];
    expect(bandPath(wind, gust, (t) => t / MIN, identity, 5 * MIN)).toBe("M3,8L4,9L4,5L3,5Z");
  });

  it("is empty without a gust", () => {
    expect(bandPath([at(0, 2), at(1, 3)], [], identity, identity, 5 * MIN)).toBe("");
  });
});

describe("bars", () => {
  it("stands each value on the baseline, centred on its time, and leaves out zeros and gaps", () => {
    const y = linearScale([0, 10], [100, 0]);
    expect(bars([at(10, 5), at(20, 0), at(30, null), at(40, 10)], (t) => t / MIN, y, 0, 4)).toEqual([
      { x: 8, y: 50, width: 4, height: 50 },
      { x: 38, y: 0, width: 4, height: 100 },
    ]);
  });

  it("stands a negative value below the baseline", () => {
    const y = linearScale([-5, 5], [100, 0]);
    expect(bars([at(0, -5)], identity, y, 0, 2)).toEqual([{ x: -1, y: 50, width: 2, height: 50 }]);
  });
});

describe("the point under the pointer", () => {
  const points = [at(0, 1), at(10, null), at(20, 3), at(30, 4)];

  it("is the nearest in time that has a value", () => {
    expect(nearestIndex(points, 11 * MIN)).toBe(2);
    expect(nearestIndex(points, 100 * MIN)).toBe(3);
    expect(nearestIndex(points, -5 * MIN)).toBe(0);
    expect(nearestIndex([at(0, null)], 0)).toBe(-1);
  });

  it("has the newest value for the heading", () => {
    expect(lastIndex(points)).toBe(3);
    expect(lastIndex([at(0, 1), at(1, null)])).toBe(0);
    expect(lastIndex([])).toBe(-1);
  });
});
