// The map replay (components/ReplayBar.vue, composables/useReplay.ts, useMapReplay.ts) as plain
// functions: the daemon's `position_history` answer made into tracks, where each station was at
// a time, its trail up to then (fading as a live track does, lib/tracks.ts), and the bar's
// clock. A station is shown from its first position in the span and stays at its last. Between
// two positions near in time it moves along the line between them; across a longer gap it waits
// where it was and then jumps. Spans are the hours of the Stations tab's "On map for", then
// days up to the week the daemon keeps.
import { t } from "@/i18n";
import { eastOf, wrapLon } from "@/lib/dateline";
import { pad2 } from "@/lib/format";
import { fadingLines, type TrackCollection } from "@/lib/tracks";
import { STATION_HOURS, trailOpacity } from "@/lib/aging";
import { LIMITS } from "@/protocol/lists";
import type { PositionHistoryMessage } from "@/protocol/protocol";

/**
 * Seconds of the span per second of replay, the bar's choices. 3600x plays a week in under
 * three minutes; faster would move stations hours per map redraw.
 */
export const REPLAY_SPEEDS: readonly number[] = [60, 300, 900, 3600];
export const DEFAULT_SPEED = 300;
/** The span the bar asks for when it opens: the default of the Stations tab's On map for. */
export const DEFAULT_HOURS: number = LIMITS.station.defaultHours;
/**
 * Spans of the bar in hours: those of On map for, then the daemon's days (SPAN_DAYS of
 * neoaprs/web/replaywire.py).
 */
export const REPLAY_SPANS: readonly number[] = [...STATION_HOURS, ...LIMITS.replay.days.map((days) => days * 24)];

/** A span as the bar says it: hours up to a day ("24 h"), days beyond ("3 days"). */
export function spanLabel(hours: number): string {
  return hours > 24 && hours % 24 === 0 ? t("weather.span.days", { n: hours / 24 }) : t("station.table.hours", { n: hours });
}

/**
 * Positions further apart in time than this are not joined by a drive: the station waits at the
 * first, then jumps. The daemon thins a longer span well inside it (GLIDE_MAX_MIN of
 * neoaprs/web/replaywire.py), so a week glides as a day does.
 */
const GLIDE_MAX_MS = LIMITS.replay.glideMaxMin * 60_000;

/** A position: time (ms since 1970), lat, lon. */
type ReplayPoint = readonly [number, number, number];

interface ReplayTrack {
  call: string;
  points: readonly ReplayPoint[];
}

export interface ReplayData {
  hours: number;
  /**
   * Where the replay begins and ends, ms since 1970: the span asked for, or later if the
   * daemon's log is shorter.
   */
  start: number;
  end: number;
  tracks: readonly ReplayTrack[];
}

/** The daemon's answer as the replay plays it: times as numbers. */
export function replayData(message: PositionHistoryMessage): ReplayData {
  const tracks = Object.entries(message.stations)
    .map(([call, points]) => ({ call, points: points.map(([at, lat, lon]): ReplayPoint => [Date.parse(at), lat, lon]) }))
    .filter((track) => track.points.length > 0);
  return { hours: message.hours, start: Date.parse(message.start), end: Date.parse(message.end), tracks };
}

/** The index of the last point at or before `t`; -1 when the first is after it. */
function lastAt(points: readonly ReplayPoint[], t: number): number {
  let low = 0;
  let high = points.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if ((points[middle]?.[0] ?? Infinity) <= t) {
      found = middle;
      low = middle + 1;
    } else high = middle - 1;
  }
  return found;
}

/** Where the station is at `t` (`t`, lat, lon); null before its first position. */
function headAt(points: readonly ReplayPoint[], t: number): { index: number; head: ReplayPoint } | null {
  const index = lastAt(points, t);
  const from = points[index];
  if (from === undefined) return null;
  const to = points[index + 1];
  if (to === undefined || to[0] - from[0] > GLIDE_MAX_MS) return { index, head: [t, from[1], from[2]] };
  const part = (t - from[0]) / (to[0] - from[0]);
  return { index, head: [t, from[1] + (to[1] - from[1]) * part, wrapLon(from[2] + eastOf(from[2], to[2]) * part)] };
}

/** Where each station that has been heard by `t` is at `t`: [call, lat, lon]. */
export function placesAt(data: ReplayData, t: number): [string, number, number][] {
  const places: [string, number, number][] = [];
  for (const track of data.tracks) {
    const found = headAt(track.points, t);
    if (found) places.push([track.call, found.head[1], found.head[2]]);
  }
  return places;
}

/**
 * A station's trail up to `t`: positions at or before `t`, then where it is at `t` if on its
 * way to the next; empty before the first.
 */
export function trailAt(track: ReplayTrack, t: number): ReplayPoint[] {
  const found = headAt(track.points, t);
  if (!found) return [];
  const passed = track.points.slice(0, found.index + 1);
  const last = passed.at(-1);
  return last && last[1] === found.head[1] && last[2] === found.head[2] ? passed : [...passed, found.head];
}

/**
 * How long a trail takes to fade, in minutes: a quarter of the span; older than that it stays,
 * faint.
 */
export function trailMinutes(hours: number): number {
  return hours * 15;
}

/**
 * The trail lines at `t`: each station's up to where it is, fainter the longer before `t` it
 * was driven.
 */
export function trailLines(data: ReplayData, t: number): TrackCollection {
  const minutes = trailMinutes(data.hours);
  const features = data.tracks.flatMap((track) =>
    fadingLines(track.call, trailAt(track, t), false, ([at, lat, lon]) => ({ at: [lon, lat], opacity: trailOpacity(Math.max(0, (t - at) / 1000), minutes) })),
  );
  return { type: "FeatureCollection", features };
}

/** The clock while there is no span to play. */
export const CLOCK_NONE = "--:--:--";

/**
 * The bar's clock in the viewer's time: HH:MM:SS, with MM-DD before it when the span crosses
 * midnight.
 */
export function replayClock(t: number, start: number, end: number): string {
  const d = new Date(t);
  const time = `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  return new Date(start).toDateString() === new Date(end).toDateString() ? time : `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${time}`;
}
