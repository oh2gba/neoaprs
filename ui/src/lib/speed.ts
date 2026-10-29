// The speed graph of a moving station's card (components/StationSpeed.vue): which stations move, the span of the graph (the station's trip: its track as the map draws it, from its oldest point to now), and the line
// of the speeds the daemon read from the station's positions (`speed_series`). Plain functions of the station's row and the answer.
import type { Point } from "@/lib/chart";
import type { SpeedSeriesMessage, StationRow } from "@/protocol/protocol";

/** How far back a station's track is looked at for whether it moves. */
const MOVING_HOURS = 24;
const HOUR_MS = 3_600_000;
/** The longest trip the daemon is asked for (`speed_series`' limit, a week: all the packets it keeps). */
const MAX_TRIP_HOURS = 168;
/** The shortest span the graph is drawn over, so that a trip of two positions a minute apart is not a graph of one minute. */
const MIN_TRIP_MS = 15 * 60_000;
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
 * MOVING_HOURS has a point more than MOVED_M from the latest. */
export function isMoving(row: StationRow, now: number): boolean {
  if (row.speed_kmh !== null && row.speed_kmh > 0) return true;
  const since = now - MOVING_HOURS * HOUR_MS;
  const recent = row.track.filter(([at]) => Date.parse(at) >= since);
  const latest = recent.at(-1);
  return latest !== undefined && recent.some((point) => metresApart(point, latest) > MOVED_M);
}

/** When the station's trip began: the oldest point of its track (the trail the map draws of it), at least MIN_TRIP_MS and at most MAX_TRIP_HOURS before now; a station with no track yet has the shortest span. */
export function tripStart(row: StationRow, now: number): number {
  const first = row.track[0];
  const oldest = first === undefined ? now : Date.parse(first[0]);
  return Math.max(now - MAX_TRIP_HOURS * HOUR_MS, Math.min(now - MIN_TRIP_MS, oldest));
}

/** The whole hours the daemon is asked for to cover the trip. */
export function tripHours(row: StationRow, now: number): number {
  return Math.min(MAX_TRIP_HOURS, Math.max(1, Math.ceil((now - tripStart(row, now)) / HOUR_MS)));
}

/** The line of the graph: one point for each speed since the trip began (the answer covers whole hours, so it may go back further), over the trip to now; no points until the answer came (the frame keeps its place). */
export function speedPoints(series: SpeedSeriesMessage | null, from: number, now: number): { from: number; to: number; points: Point[] } {
  const points = series === null ? [] : series.points.map(([at, kmh]) => ({ t: Date.parse(at), v: kmh })).filter((point) => point.t >= from);
  return { from, to: now, points };
}
