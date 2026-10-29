// The arithmetic of the trend graphs (components/TrendChart.vue): the scales, the ticks with round numbers, the paths of a line, a band and bars, and the point under the pointer. Plain functions of numbers, so that
// the page draws inline SVG in its own colours with no chart library. A point is a time in ms and a value, null where the station did not send one.

import { weekdayShort } from "@/i18n";
import { HOUR_MS, pad2 } from "@/lib/format";

export interface Point {
  t: number;
  v: number | null;
}

interface Ticks {
  min: number;
  max: number;
  step: number;
  ticks: number[];
}

interface TimeTick {
  at: number;
  label: string;
}

/** The function that maps a value of `domain` to a place in `range` (the range may run backwards: the y axis of a screen); a domain of no width maps everything to the middle. */
export function linearScale(domain: readonly [number, number], range: readonly [number, number]): (v: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  return (v) => (d1 === d0 ? (r0 + r1) / 2 : r0 + ((v - d0) / (d1 - d0)) * (r1 - r0));
}

/** The lowest and highest value present; with `zero` the span includes 0 (wind, rain); a series with one value, or none, still has a span. */
export function extent(values: readonly number[], zero: boolean): [number, number] {
  let lo = values.length > 0 ? Math.min(...values) : 0;
  let hi = values.length > 0 ? Math.max(...values) : 1;
  if (zero) {
    lo = Math.min(lo, 0);
    hi = Math.max(hi, 0);
  }
  return hi > lo ? [lo, hi] : [lo - 1, hi + 1];
}

/** Round tick values (1, 2 or 5 times a power of ten) around [min, max], about `target` of them; the first and last are the new ends of the axis. */
export function niceTicks(min: number, max: number, target = 4): Ticks {
  const raw = (max > min ? max - min : 1) / Math.max(1, target);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? 10 * magnitude;
  const lo = Math.floor(min / step + 1e-9) * step;
  const hi = Math.ceil(max / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let i = 0; lo + i * step <= hi + step / 1e6; i++) ticks.push(Number((lo + i * step).toPrecision(12)));
  return { min: ticks[0] ?? lo, max: ticks[ticks.length - 1] ?? hi, step, ticks };
}

/** How many decimals a tick of this step needs: 0 for 5, 1 for 0.5, 2 for 0.05. */
export function tickDecimals(step: number): number {
  return step >= 1 ? 0 : Math.min(4, Math.ceil(-Math.log10(step) - 1e-9));
}

/** Ticks on whole hours of the viewer's clock between two times, a step of 1, 2, 3, 6, 12 or 24 hours that gives at most seven; a day step is labelled with the day ("Mon 19"), the others with the hour ("06:00"). */
export function timeTicks(from: number, to: number): TimeTick[] {
  const stepHours = [1, 2, 3, 6, 12, 24].find((s) => (to - from) / (s * HOUR_MS) <= 7.5) ?? 24;
  const d = new Date(from);
  d.setMinutes(0, 0, 0);
  d.setHours(stepHours >= 24 ? 0 : Math.floor(d.getHours() / stepHours) * stepHours);
  const ticks: TimeTick[] = [];
  for (let guard = 0; d.getTime() <= to && guard < 400; guard++) {
    if (d.getTime() >= from) ticks.push({ at: d.getTime(), label: stepHours >= 24 ? `${weekdayShort(d)} ${d.getDate()}` : `${pad2(d.getHours())}:00` });
    d.setHours(d.getHours() + stepHours);
  }
  return ticks;
}

/** The usual time between two observations (the median), 0 for fewer than two. */
export function usualGap(points: readonly Point[]): number {
  const gaps = points
    .slice(1)
    .map((p, i) => p.t - (points[i]?.t ?? p.t))
    .filter((g) => g > 0)
    .sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)] ?? 0;
}

const num = (n: number): string => String(Math.round(n * 100) / 100);

/** A curve through the readings that have a value, in places of the screen: x strictly increasing, and the slope of the curve at each reading. */
interface Curve {
  xs: number[];
  ys: number[];
  slopes: number[];
}

/** The slope at an end of the readings from the secant `d0` of the segment there (width `h0`) and the one next to it (`d1`, `h1`; none when there are only two readings): a parabola's slope, held to the direction of `d0` and to three times it. */
function endSlope(d0: number, h0: number, d1?: number, h1?: number): number {
  if (d1 === undefined || h1 === undefined) return d0;
  const raw = (d0 * (2 * h0 + h1) - d1 * h0) / (h0 + h1);
  if (raw * d0 <= 0) return 0;
  return Math.abs(raw) > 3 * Math.abs(d0) ? 3 * d0 : raw;
}

/** The monotone cubic through the readings (Fritsch-Carlson, the "monotoneX" of d3): the slope is 0 where the data turns or stays level, else the weighted harmonic mean of the two secants, so that between two readings the curve never goes above or below either of them. Readings at the same time: the later one counts. */
function curveOf(points: readonly Point[], x: (t: number) => number, y: (v: number) => number): Curve {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const p of points) {
    if (p.v === null) continue;
    const px = x(p.t);
    if (xs.length > 0 && px <= (xs[xs.length - 1] ?? px)) {
      ys[ys.length - 1] = y(p.v);
      continue;
    }
    xs.push(px);
    ys.push(y(p.v));
  }
  const n = xs.length;
  const h = xs.slice(1).map((v, i) => v - (xs[i] ?? v));
  const d = ys.slice(1).map((v, i) => (v - (ys[i] ?? v)) / (h[i] ?? 1));
  const slopes = ys.map((_, i): number => {
    if (i === 0 || i === n - 1) return 0;
    const [d0, d1, h0, h1] = [d[i - 1] ?? 0, d[i] ?? 0, h[i - 1] ?? 1, h[i] ?? 1];
    return d0 * d1 <= 0 ? 0 : (3 * (h0 + h1)) / ((2 * h1 + h0) / d0 + (h1 + 2 * h0) / d1);
  });
  if (n >= 2) {
    slopes[0] = endSlope(d[0] ?? 0, h[0] ?? 1, d[1], h[1]);
    slopes[n - 1] = endSlope(d[n - 2] ?? 0, h[n - 2] ?? 1, d[n - 3], h[n - 3]);
  }
  return { xs, ys, slopes };
}

/** The curve's height at a place between its first and last reading. */
function heightAt(c: Curve, at: number): number {
  let i = 0;
  while (i < c.xs.length - 2 && at > (c.xs[i + 1] ?? at)) i++;
  const [x0, x1, y0, y1] = [c.xs[i] ?? 0, c.xs[i + 1] ?? 1, c.ys[i] ?? 0, c.ys[i + 1] ?? 0];
  const h = x1 - x0;
  const s = (at - x0) / h;
  const [m0, m1] = [(c.slopes[i] ?? 0) * h, (c.slopes[i + 1] ?? 0) * h];
  return (2 * s ** 3 - 3 * s ** 2 + 1) * y0 + (s ** 3 - 2 * s ** 2 + s) * m0 + (-2 * s ** 3 + 3 * s ** 2) * y1 + (s ** 3 - s ** 2) * m1;
}

/** The path of one smooth curve through the readings that have a value, across the times where there are none and from the first reading to the last, no further: a cubic Bezier for each stretch between two readings, whose control points lie at a third of its width, on the slopes of the monotone cubic. A single reading is a dot of no length (a line cap draws it). */
export function linePath(points: readonly Point[], x: (t: number) => number, y: (v: number) => number): string {
  const { xs, ys, slopes } = curveOf(points, x, y);
  const first = xs[0];
  if (first === undefined) return "";
  if (xs.length === 1) return `M${num(first)},${num(ys[0] ?? 0)}h0`;
  let path = `M${num(first)},${num(ys[0] ?? 0)}`;
  for (let i = 1; i < xs.length; i++) {
    const [x0, x1, y0, y1] = [xs[i - 1] ?? 0, xs[i] ?? 0, ys[i - 1] ?? 0, ys[i] ?? 0];
    const third = (x1 - x0) / 3;
    path += `C${num(x0 + third)},${num(y0 + (slopes[i - 1] ?? 0) * third)},${num(x1 - third)},${num(y1 - (slopes[i] ?? 0) * third)},${num(x1)},${num(y1)}`;
  }
  return path;
}

/** The area between two series (the sustained wind and its gusts) that follows their two curves, one closed path from the later of their first readings to the earlier of their last; the edge is taken in small steps of the curves, so that where they cross it stays between them. Nothing for a series with fewer than two readings or no time in common. */
export function bandPath(lower: readonly Point[], upper: readonly Point[], x: (t: number) => number, y: (v: number) => number): string {
  const [low, high] = [curveOf(lower, x, y), curveOf(upper, x, y)];
  const [from, to] = [
    Math.max(low.xs[0] ?? Infinity, high.xs[0] ?? Infinity),
    Math.min(low.xs[low.xs.length - 1] ?? -Infinity, high.xs[high.xs.length - 1] ?? -Infinity),
  ];
  if (!(to > from)) return "";
  const places = [...new Set([from, to, ...[...low.xs, ...high.xs].filter((v) => v > from && v < to)])].sort((a, b) => a - b);
  const steps = places.flatMap((v, i) => {
    const next = places[i + 1];
    if (next === undefined) return [v];
    const pieces = Math.max(1, Math.ceil((next - v) / 2));
    return Array.from({ length: pieces }, (_, k) => v + ((next - v) * k) / pieces);
  });
  const edges = steps.map((v) => {
    const a = heightAt(low, v);
    const b = heightAt(high, v);
    return { v, a: Math.min(a, b), b: Math.max(a, b) };
  });
  const top = edges.map((e, i) => `${i === 0 ? "M" : "L"}${num(e.v)},${num(e.a)}`).join("");
  const bottom = [...edges]
    .reverse()
    .map((e) => `L${num(e.v)},${num(e.b)}`)
    .join("");
  return `${top}${bottom}Z`;
}

interface Bar {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** The bars of a series standing on `baseline` (a value), each `width` wide and centred on its time; a value of 0 is a bar of no height, left out. */
export function bars(points: readonly Point[], x: (t: number) => number, y: (v: number) => number, baseline: number, width: number): Bar[] {
  const floor = y(baseline);
  return points.flatMap((p) => {
    if (p.v === null || p.v === baseline) return [];
    const top = y(p.v);
    return [{ x: x(p.t) - width / 2, y: Math.min(top, floor), width, height: Math.abs(floor - top) }];
  });
}

/** The index of the point nearest in time to `t` among those that have a value; -1 when none has. */
export function nearestIndex(points: readonly Point[], t: number): number {
  let best = -1;
  let distance = Infinity;
  points.forEach((p, i) => {
    if (p.v === null) return;
    const d = Math.abs(p.t - t);
    if (d < distance) {
      best = i;
      distance = d;
    }
  });
  return best;
}

/** The index of the newest point that has a value; -1 when none has. */
export function lastIndex(points: readonly Point[]): number {
  for (let i = points.length - 1; i >= 0; i--) if (points[i]?.v !== null) return i;
  return -1;
}
