// The replay of the map (the map's menu, Replay: components/ReplayBar.vue, composables/useReplay.ts, composables/useMapReplay.ts) as plain functions: the daemon's answer to `position_history` made into tracks of numbers,
// where each station was at a time of the span, its trail up to then (fading behind it as a live track does, lib/tracks.ts), and the clock of the bar. A station is shown from its first position in the span and stays
// at its last; between two positions that are near in time it is moved along the line between them, as far as the time has gone, so that a moving station drives and does not hop; across a longer gap (it was not
// heard for a while) it waits where it was and jumps. The spans are the hours of the Stations tab's On map for and then days, up to the week the daemon keeps.
import { t } from "@/i18n";
import { pad2 } from "@/lib/format";
import { fadingLines, type TrackCollection } from "@/lib/tracks";
import { STATION_HOURS, trailOpacity } from "@/lib/aging";
import { LIMITS } from "@/protocol/lists";
import type { PositionHistoryMessage } from "@/protocol/protocol";

/** How many seconds of the span go by in a second of the replay: the choices of the bar. At 3600× a week plays in under three minutes, a day in 24 seconds: nothing faster is needed, and a faster one would
 * move the stations hours at each tenth of a second the map is drawn. */
export const REPLAY_SPEEDS: readonly number[] = [60, 300, 900, 3600];
export const DEFAULT_SPEED = 300;
/** The span the bar asks for when it opens, the default of the Stations tab's On map for. */
export const DEFAULT_HOURS: number = LIMITS.station.defaultHours;
/** The spans of the bar in hours: those of On map for, then the days of the daemon (SPAN_DAYS of neoaprs/web/replaywire.py: 2, 3 and the 7 its packet log keeps). */
export const REPLAY_SPANS: readonly number[] = [...STATION_HOURS, ...LIMITS.replay.days.map((days) => days * 24)];

/** A span as the bar says it: hours up to a day ("24 h"), days beyond ("3 days"). */
export function spanLabel(hours: number): string {
  return hours > 24 && hours % 24 === 0 ? t("weather.span.days", { n: hours / 24 }) : t("station.table.hours", { n: hours });
}

/** Two positions further apart in time than this are not joined by a drive: the station waits at the first, then jumps. The daemon thins a longer span to a point every few minutes at most, well inside it
 * (GLIDE_MAX_MIN of neoaprs/web/replaywire.py, held to its thinning by a test there), so that a trip of a week glides as a day's does. */
const GLIDE_MAX_MS = LIMITS.replay.glideMaxMin * 60_000;

/** A position of a station: when (ms since 1970), lat, lon. */
type ReplayPoint = readonly [number, number, number];

interface ReplayTrack {
  call: string;
  /** the oldest first */
  points: readonly ReplayPoint[];
}

export interface ReplayData {
  hours: number;
  /** where the replay begins and ends, ms since 1970: the span asked for, begun later when the daemon's log does not reach back that far */
  start: number;
  end: number;
  tracks: readonly ReplayTrack[];
}

/** The answer of the daemon as the replay plays it: the times as numbers. */
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

/** Where the station is at `t` (the time `t` itself, lat, lon): null before its first position. */
function headAt(points: readonly ReplayPoint[], t: number): { index: number; head: ReplayPoint } | null {
  const index = lastAt(points, t);
  const from = points[index];
  if (from === undefined) return null;
  const to = points[index + 1];
  if (to === undefined || to[0] - from[0] > GLIDE_MAX_MS) return { index, head: [t, from[1], from[2]] };
  const part = (t - from[0]) / (to[0] - from[0]);
  return { index, head: [t, from[1] + (to[1] - from[1]) * part, from[2] + (to[2] - from[2]) * part] };
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

/** The trail of a station up to `t`: its positions at or before `t`, then where it is at `t` when it is on its way to the next; empty before its first position. */
export function trailAt(track: ReplayTrack, t: number): ReplayPoint[] {
  const found = headAt(track.points, t);
  if (!found) return [];
  const passed = track.points.slice(0, found.index + 1);
  const last = passed.at(-1);
  return last && last[1] === found.head[1] && last[2] === found.head[2] ? passed : [...passed, found.head];
}

/** How long a trail takes to fade, in minutes: a quarter of the span (15 minutes of an hour's replay, 6 hours of a day's); older than that it stays, faint. */
export function trailMinutes(hours: number): number {
  return hours * 15;
}

/** The lines of the trails at `t`: each station's up to where it is, a stretch the fainter the longer before `t` it was driven. */
export function trailLines(data: ReplayData, t: number): TrackCollection {
  const minutes = trailMinutes(data.hours);
  const features = data.tracks.flatMap((track) =>
    fadingLines(track.call, trailAt(track, t), false, ([at, lat, lon]) => ({ at: [lon, lat], opacity: trailOpacity(Math.max(0, (t - at) / 1000), minutes) })),
  );
  return { type: "FeatureCollection", features };
}

/** The clock while there is no span to play (the answer has not come). */
export const CLOCK_NONE = "--:--:--";

/** The clock of the bar, in the viewer's time: HH:MM:SS, with the date (MM-DD) before it when the span crosses midnight, so that the hours of two days are told apart. */
export function replayClock(t: number, start: number, end: number): string {
  const d = new Date(t);
  const time = `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  return new Date(start).toDateString() === new Date(end).toDateString() ? time : `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${time}`;
}
