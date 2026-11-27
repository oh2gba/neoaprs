// Where a moving thing is drawn between its reports: carried on from its last reported position
// along its course at its speed (dead reckoning on the sphere), and eased onto a new report over
// a short moment instead of jumping. A thing without course or speed stays where it was reported;
// one not reported for `stopSec` stops where the reckoning had carried it.
import { wrapLon } from "@/lib/layers/satellite";

export type LonLat = [lon: number, lat: number];

const EARTH_KM = 6371.0088;
/** How long a new report takes to be eased onto. */
export const EASE_MS = 800;
/** A new report further than this (degrees) from where the thing is drawn is jumped to. */
const JUMP_DEG = 0.5;
/** Below this speed a thing is drawn where it was reported. */
const STILL_KMH = 1;

/** A thing's report: where and when (on the motion's clock), and how it moves (null: not told). */
export interface Report {
  lon: number;
  lat: number;
  atMs: number;
  courseDeg: number | null;
  speedKmh: number | null;
}

/** A thing as it is drawn: its last report, and the offset eased away from `fromMs` on. */
export interface Glide {
  report: Report;
  fromMs: number;
  offset: LonLat;
}

/** Where a thing at `lon`, `lat` going `courseDeg` at `speedKmh` is after `sec` seconds (a great circle). */
export function reckon(lon: number, lat: number, courseDeg: number, speedKmh: number, sec: number): LonLat {
  const rad = Math.PI / 180;
  const d = (speedKmh * sec) / 3600 / EARTH_KM;
  const p1 = lat * rad;
  const b = courseDeg * rad;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 = Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [wrapLon(lon + l2 / rad), p2 / rad];
}

/** The eased share of a move, 0 at its start and 1 at its end (a cubic ease-out). */
export function easeOut(fraction: number): number {
  const f = Math.min(1, Math.max(0, fraction));
  return 1 - (1 - f) ** 3;
}

const moves = (report: Report): boolean =>
  report.courseDeg !== null && report.speedKmh !== null && report.speedKmh >= STILL_KMH;

/** Where the report puts the thing at `nowMs`: reckoned from its time, for at most `stopSec`. */
export function reckoned(report: Report, nowMs: number, stopSec: number): LonLat {
  if (!moves(report)) return [report.lon, report.lat];
  const sec = Math.min(stopSec, Math.max(0, (nowMs - report.atMs) / 1000));
  if (sec === 0) return [report.lon, report.lat];
  return reckon(report.lon, report.lat, report.courseDeg ?? 0, report.speedKmh ?? 0, sec);
}

/** Where a thing is drawn at `nowMs`. */
export function glidePosition(glide: Glide, nowMs: number, stopSec: number): LonLat {
  const [lon, lat] = reckoned(glide.report, nowMs, stopSec);
  const left = 1 - easeOut((nowMs - glide.fromMs) / EASE_MS);
  if (left <= 0) return [lon, lat];
  return [wrapLon(lon + glide.offset[0] * left), lat + glide.offset[1] * left];
}

const sameReport = (a: Report, b: Report): boolean =>
  a.lon === b.lon && a.lat === b.lat && a.atMs === b.atMs && a.courseDeg === b.courseDeg && a.speedKmh === b.speedKmh;

/** The glide after a report comes at `nowMs`: eased from where the thing is drawn onto the new report. */
export function nextGlide(was: Glide | undefined, report: Report, nowMs: number, stopSec: number): Glide {
  if (was && sameReport(was.report, report)) return was;
  if (!was) return { report, fromMs: -Infinity, offset: [0, 0] };
  const shown = glidePosition(was, nowMs, stopSec);
  const target = reckoned(report, nowMs, stopSec);
  const offset: LonLat = [wrapLon(shown[0] - target[0]), shown[1] - target[1]];
  if (Math.abs(offset[0]) > JUMP_DEG || Math.abs(offset[1]) > JUMP_DEG)
    return { report, fromMs: -Infinity, offset: [0, 0] };
  return { report, fromMs: nowMs, offset };
}
