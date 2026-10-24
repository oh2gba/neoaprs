// How stations age on the map: the timeout of a station (the fixed 180 minutes; our own station and our own objects never time out), whether a station has passed it, and how faded the marker and
// the trail of a station are on the way there. Plain functions of rows and the time.
import { ageSeconds } from "@/lib/format";
import { LIMITS } from "@/protocol/lists";
import type { StationRow } from "@/protocol/protocol";

/** What the page knows of the timeout: the minutes after which a station has passed it (0 is never; the page's is DEFAULT_TIMEOUT_MIN, the tests pass others). */
export interface Aging {
  defaultMin: number;
}

/** When a station never times out its marker and trail still fade, over this long. */
export const FADE_SPAN_NEVER_SEC = 24 * 60 * 60;
/** A trail has this many opacities, from 1 for the newest to TRAIL_OLDEST for the oldest; a marker has MARKER_STEPS looks, 0 fresh to the last one nearest the timeout. */
export const TRAIL_STEPS = 8;
export const TRAIL_OLDEST = 0.15;
export const MARKER_STEPS = 4;

/** The timeout of every station, in minutes: three hours (fixed, HIDE_AFTER_MIN of the daemon's policy.py; it is no setting). */
export const DEFAULT_TIMEOUT_MIN = LIMITS.station.hideAfterMin;

/** The timeout of a station in minutes, 0 for never: the same for every station; our own station and our own objects never time out. */
export function timeoutMin(aging: Aging, row: StationRow): number {
  return row.is_me || row.own ? 0 : aging.defaultMin;
}

/** The age in seconds of the last position (the last packet for a row that has a position and no time for it). */
function positionAge(row: StationRow, nowMs: number): number {
  return ageSeconds(row.last_position_at ?? row.last_heard, nowMs);
}

/** Whether the station has a position that is older than its timeout: it is not drawn on the map then. */
export function timedOut(aging: Aging, row: StationRow, nowMs: number): boolean {
  const minutes = timeoutMin(aging, row);
  return minutes > 0 && row.lat !== null && row.lon !== null && positionAge(row, nowMs) > minutes * 60;
}

/** How far an age is on the way to the timeout, 0 (just now) to 1 (there or past it). A station that never times out is measured against a day. */
export function fadeFraction(ageSec: number, minutes: number): number {
  const span = minutes > 0 ? minutes * 60 : FADE_SPAN_NEVER_SEC;
  return Math.min(1, Math.max(0, ageSec / span));
}

function stepOf(fraction: number, steps: number): number {
  return Math.min(steps - 1, Math.floor(fraction * steps));
}

/** The opacity of a stretch of a trail whose older end is `ageSec` old, for a station with this timeout: one of TRAIL_STEPS values, 1 for the newest, TRAIL_OLDEST at the timeout. */
export function trailOpacity(ageSec: number, minutes: number): number {
  const step = stepOf(fadeFraction(ageSec, minutes), TRAIL_STEPS);
  return Math.round((1 - (step / (TRAIL_STEPS - 1)) * (1 - TRAIL_OLDEST)) * 100) / 100;
}

/** How dim the marker of a station is: 0 fresh up to MARKER_STEPS - 1 just before the timeout. Our own station and our own objects are always 0. */
export function markerStep(aging: Aging, row: StationRow, nowMs: number): number {
  return row.is_me || row.own ? 0 : stepOf(fadeFraction(positionAge(row, nowMs), timeoutMin(aging, row)), MARKER_STEPS);
}
