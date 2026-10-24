import { describe, expect, it } from "vitest";
import { bandPath, bars, extent, lastIndex, linePath, linearScale, nearestIndex, niceTicks, tickDecimals, timeTicks, usualGap, type Point } from "@/lib/chart";

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

describe("the usual spacing", () => {
  it("is the median time between two observations, 0 for fewer than two", () => {
    expect(usualGap([at(0, 1), at(10, 1), at(20, 1), at(30, 1)])).toBe(10 * MIN);
    expect(usualGap([at(0, 1)])).toBe(0);
  });
});

/** The segments of a path made of `M` and `C` as the numbers of the start and the three points of each. */
function segments(path: string): number[][] {
  const [start, ...rest] = path.split("C");
  const first = (start ?? "").slice(1).split(",").map(Number);
  let from = first;
  return rest.map((c) => {
    const seg = [...from.slice(-2), ...c.split(",").map(Number)];
    from = seg.slice(-2);
    return seg;
  });
}

describe("linePath", () => {
  it("is one cubic curve through the readings, from the first to the last", () => {
    const path = linePath([at(0, 1), at(1, 3), at(2, 2)], (t) => t / MIN, identity);
    expect(path).toMatch(/^M0,1C[\d.,-]+C[\d.,-]+$/);
    expect(path.match(/C/g)).toHaveLength(2);
    expect(path.endsWith(",2,2")).toBe(true);
  });

  it("carries on across a missing value and a long silence, with no break", () => {
    const path = linePath([at(0, 1), at(1, 2), at(2, null), at(3, 3), at(4, 4), at(600, 5), at(601, 6)], (t) => t / MIN, identity);
    expect(path.match(/M/g)).toHaveLength(1);
    const segs = segments(path);
    expect(segs).toHaveLength(5); // 6 readings with a value
    expect(segs[1]?.slice(-2)).toEqual([3, 3]); // the reading at 3 follows the one at 1 directly
    expect(segs[3]?.slice(-2)).toEqual([600, 5]);
    expect(segs[4]?.slice(-2)).toEqual([601, 6]);
  });

  it("stays between the neighbouring readings: no control point above or below them, so no invented peak", () => {
    const series = [at(0, 1010), at(5, 1012), at(9, 1012), at(30, 1008), at(31, 1008.5), at(70, 1020), at(75, 1019), at(200, 1015), at(260, 1015.2)];
    const y = (v: number): number => v;
    const readings = series.map((p) => p.v as number);
    const segs = segments(linePath(series, (t) => t / MIN, y));
    expect(segs).toHaveLength(series.length - 1);
    segs.forEach((seg, i) => {
      const [lo, hi] = [Math.min(readings[i], readings[i + 1]), Math.max(readings[i], readings[i + 1])];
      for (const cy of [seg[3], seg[5]] as number[]) {
        expect(cy).toBeGreaterThanOrEqual(lo - 0.011);
        expect(cy).toBeLessThanOrEqual(hi + 0.011);
      }
      // and in time the control points lie between the readings
      expect(seg[2]).toBeGreaterThanOrEqual(seg[0]);
      expect(seg[4]).toBeLessThanOrEqual(seg[6]);
      expect(seg[2]).toBeLessThanOrEqual(seg[4]);
    });
  });

  it("is level at a turning point and between equal readings", () => {
    const segs = segments(linePath([at(0, 1), at(10, 5), at(20, 2), at(30, 2), at(40, 2)], (t) => t / MIN, identity));
    expect(segs[0]?.[5]).toBe(5); // the peak: the control points beside it are at its height
    expect(segs[1]?.[3]).toBe(5);
    expect(segs[2]).toEqual([20, 2, 20 + 10 / 3, 2, 30 - 10 / 3, 2, 30, 2].map((n) => Math.round(n * 100) / 100));
  });

  it("is a straight stretch for two readings", () => {
    expect(segments(linePath([at(0, 0), at(3, 6)], (t) => t / MIN, identity))).toEqual([[0, 0, 1, 2, 2, 4, 3, 6]]);
  });

  it("draws a lone reading as a dot of no length, and nothing for no value", () => {
    expect(linePath([at(5, 2)], (t) => t / MIN, identity)).toBe("M5,2h0");
    expect(linePath([at(1, null), at(5, 2), at(6, null)], (t) => t / MIN, identity)).toBe("M5,2h0");
    expect(linePath([at(5, null)], (t) => t / MIN, identity)).toBe("");
    expect(linePath([], identity, identity)).toBe("");
  });

  it("does not reach before the first reading or after the last", () => {
    const xs = [...linePath([at(2, 1), at(3, 4), at(8, 2)], (t) => t / MIN, identity).matchAll(/[M,C](-?[\d.]+),(-?[\d.]+)/g)].map((m) => Number(m[1]));
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(2);
    expect(Math.max(...xs)).toBeLessThanOrEqual(8);
  });

  it("rounds the numbers to two decimals", () => {
    expect(linePath([at(0, 1.23456), at(1, 2)], (t) => t / 3 / MIN, identity)).toBe("M0,1.23C0.11,1.49,0.22,1.74,0.33,2");
  });
});

describe("bandPath", () => {
  /** the points of a closed path of M, L and Z */
  const outline = (path: string): [number, number][] =>
    path
      .replace("Z", "")
      .split(/[ML]/)
      .filter(Boolean)
      .map((p) => p.split(",").map(Number) as [number, number]);

  it("closes one path between the curves of the two series, from the first time both have to the last", () => {
    const wind = [at(0, 2), at(10, 3), at(20, 4)];
    const gust = [at(0, 5), at(10, 7), at(20, 6)];
    const path = bandPath(wind, gust, (t) => t / MIN, identity);
    expect(path).toMatch(/^M0,2L.*Z$/);
    expect(path.match(/M/g)).toHaveLength(1);
    const points = outline(path);
    expect(points[0]).toEqual([0, 2]);
    expect(points).toContainEqual([10, 3]);
    expect(points).toContainEqual([10, 7]);
    expect(points).toContainEqual([20, 4]);
    expect(points[points.length - 1]).toEqual([0, 5]);
  });

  it("follows the curves across the gaps and stays between them", () => {
    const wind = [at(0, 2), at(10, null), at(20, 4), at(100, 5)];
    const gust = [at(0, 5), at(10, 7), at(20, null), at(100, 9)];
    const path = bandPath(wind, gust, (t) => t / MIN, identity);
    expect(path.match(/M/g)).toHaveLength(1);
    const points = outline(path);
    const half = points.length / 2;
    const low = points.slice(0, half);
    const high = points.slice(half).reverse();
    expect(low[0]?.[0]).toBe(0);
    expect(low[low.length - 1]?.[0]).toBe(100);
    low.forEach((p, i) => {
      expect(p[0]).toBe(high[i]?.[0]);
      expect(p[1]).toBeLessThanOrEqual(high[i]?.[1]);
      expect(p[1]).toBeGreaterThanOrEqual(2 - 0.01);
      expect(high[i]?.[1]).toBeLessThanOrEqual(9 + 0.01);
    });
    expect(low).toContainEqual([20, 4]);
    expect(high).toContainEqual([10, 7]);
  });

  it("covers only the time both series span", () => {
    const points = outline(bandPath([at(5, 1), at(15, 2)], [at(0, 4), at(10, 5)], (t) => t / MIN, identity));
    expect(Math.min(...points.map((p) => p[0]))).toBe(5);
    expect(Math.max(...points.map((p) => p[0]))).toBe(10);
  });

  it("is empty without a gust, with a single reading or with no time in common", () => {
    expect(bandPath([at(0, 2), at(1, 3)], [], identity, identity)).toBe("");
    expect(bandPath([at(0, 2)], [at(0, 4)], identity, identity)).toBe("");
    expect(bandPath([at(0, 2), at(1, 3)], [at(5, 4), at(6, 5)], identity, identity)).toBe("");
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
