// The arithmetic of the trend graphs (components/TrendChart.vue): the scales, the ticks with round numbers, the paths of a line, a band and bars, and the point under the pointer. Plain functions of numbers, so that
// the page draws inline SVG in its own colours with no chart library. A point is a time in ms and a value, null where the station did not send one.

import { weekdayShort } from "@/i18n";

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

const HOUR = 3_600_000;
const MINUTE = 60_000;

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

const pad = (n: number): string => String(n).padStart(2, "0");

/** Ticks on whole hours of the viewer's clock between two times, a step of 1, 2, 3, 6, 12 or 24 hours that gives at most seven; a day step is labelled with the day ("Mon 19"), the others with the hour ("06:00"). */
export function timeTicks(from: number, to: number): TimeTick[] {
  const stepHours = [1, 2, 3, 6, 12, 24].find((s) => (to - from) / (s * HOUR) <= 7.5) ?? 24;
  const d = new Date(from);
  d.setMinutes(0, 0, 0);
  d.setHours(stepHours >= 24 ? 0 : Math.floor(d.getHours() / stepHours) * stepHours);
  const ticks: TimeTick[] = [];
  for (let guard = 0; d.getTime() <= to && guard < 400; guard++) {
    if (d.getTime() >= from) ticks.push({ at: d.getTime(), label: stepHours >= 24 ? `${weekdayShort(d)} ${d.getDate()}` : `${pad(d.getHours())}:00` });
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

/** The longest silence that still joins two points of a line: three times the usual spacing, at least 20 minutes. */
export function gapLimit(points: readonly Point[]): number {
  return Math.max(3 * usualGap(points), 20 * MINUTE);
}

const num = (n: number): string => String(Math.round(n * 100) / 100);

/** The runs of the points that have a value and are not further apart than `gap`: a station that went quiet leaves a break in the line, not a straight stretch. */
function runs(points: readonly Point[], gap: number): { t: number; v: number }[][] {
  const out: { t: number; v: number }[][] = [];
  let current: { t: number; v: number }[] = [];
  let last = -Infinity;
  for (const p of points) {
    if (p.v === null) {
      current = [];
      last = -Infinity;
      continue;
    }
    if (p.t - last > gap) {
      current = [];
      out.push(current);
    }
    current.push({ t: p.t, v: p.v });
    last = p.t;
  }
  return out.filter((r) => r.length > 0);
}

/** The path of a line through the points; a run of one point is a dot of no length (a line cap draws it). */
export function linePath(points: readonly Point[], x: (t: number) => number, y: (v: number) => number, gap: number): string {
  return runs(points, gap)
    .map((run) => run.map((p, i) => `${i === 0 ? "M" : "L"}${num(x(p.t))},${num(y(p.v))}`).join("") + (run.length === 1 ? "h0" : ""))
    .join("");
}

/** The area between two series (the sustained wind and its gusts), closed paths, only where both have a value at the same time. */
export function bandPath(lower: readonly Point[], upper: readonly Point[], x: (t: number) => number, y: (v: number) => number, gap: number): string {
  const high = new Map(upper.filter((p) => p.v !== null).map((p) => [p.t, p.v as number]));
  const both = lower.map((p): Point => ({ t: p.t, v: p.v !== null && high.has(p.t) ? p.v : null }));
  return runs(both, gap)
    .filter((run) => run.length > 1)
    .map((run) => {
      const top = run.map((p, i) => `${i === 0 ? "M" : "L"}${num(x(p.t))},${num(y(Math.max(p.v, high.get(p.t) ?? p.v)))}`).join("");
      const bottom = [...run]
        .reverse()
        .map((p) => `L${num(x(p.t))},${num(y(Math.min(p.v, high.get(p.t) ?? p.v)))}`)
        .join("");
      return `${top}${bottom}Z`;
    })
    .join("");
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
