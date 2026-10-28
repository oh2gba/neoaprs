// The speed graph of a moving station's card (components/StationSpeed.vue): which stations move, and the line of the speeds the daemon read from the station's positions (`speed_series`). Plain functions of the
// station's row and the answer.
import type { Point } from "@/lib/chart";
import type { SpeedSeriesMessage, StationRow } from "@/protocol/protocol";

/** How far back the speed graph goes. */
export const SPEED_HOURS = 24;
const HOUR_MS = 3_600_000;
/** A track whose points in the span are farther apart than this is a station that moved: a fixed station's track gets a point every 5 minutes too (neoaprs/station.py), a few metres apart at most by its GPS. */
const MOVED_M = 100;
const EARTH_RADIUS_M = 6_371_008.8; // the daemon's sphere (neoaprs/geo.py)

/** The distance between two points, flat over the short distances that are compared here. */
function metresApart(a: readonly [string, number, number], b: readonly [string, number, number]): number {
  const toRad = Math.PI / 180;
  const x = (b[2] - a[2]) * toRad * Math.cos(((a[1] + b[1]) / 2) * toRad);
  const y = (b[1] - a[1]) * toRad;
  return Math.hypot(x, y) * EARTH_RADIUS_M;
}

/** Whether the station moves, by its row alone (so that the card keeps the graph's room before the answer comes, and a fixed station's card has none): it is moving now, or its track of the last
 * SPEED_HOURS has a point more than MOVED_M from the latest. */
export function isMoving(row: StationRow, now: number): boolean {
  if (row.speed_kmh !== null && row.speed_kmh > 0) return true;
  const since = now - SPEED_HOURS * HOUR_MS;
  const recent = row.track.filter(([at]) => Date.parse(at) >= since);
  const latest = recent.at(-1);
  return latest !== undefined && recent.some((point) => metresApart(point, latest) > MOVED_M);
}

/** The line of the graph: one point for each speed, over the last SPEED_HOURS to now; no points until the answer came (the frame keeps its place). */
export function speedPoints(series: SpeedSeriesMessage | null, now: number): { from: number; to: number; points: Point[] } {
  const points = series === null ? [] : series.points.map(([at, kmh]) => ({ t: Date.parse(at), v: kmh }));
  return { from: now - SPEED_HOURS * HOUR_MS, to: now, points };
}
