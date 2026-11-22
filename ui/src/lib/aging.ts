// How stations age on the map: the timeout of a station (setting `map/station_hours`; our own
// station and objects never time out), whether it has passed it, and how faded its marker and trail
// are on the way there.
import { ageSeconds } from "@/lib/format";
import { LIMITS } from "@/protocol/lists";
import type { StationRow } from "@/protocol/protocol";

/** The timeout in minutes (0 is never); the page's follows the setting (`agingOf`). */
export interface Aging {
  defaultMin: number;
}

/** A station that never times out still fades over this long. */
export const FADE_SPAN_NEVER_SEC = 24 * 60 * 60;
/**
 * A trail has TRAIL_STEPS opacities, from 1 (newest) to TRAIL_OLDEST; a marker has MARKER_STEPS
 * looks, 0 fresh up to the last one nearest the timeout.
 */
export const TRAIL_STEPS = 8;
export const TRAIL_OLDEST = 0.15;
export const MARKER_STEPS = 4;

/**
 * The setting for how many hours a station stays on the map, and the allowed hours (STATION_HOURS
 * in config.py).
 */
export const STATION_HOURS_KEY = "map/station_hours";
export const STATION_HOURS: readonly number[] = LIMITS.station.hours;

/** The timeout in minutes while the setting is unknown: the default, three hours. */
export const DEFAULT_TIMEOUT_MIN = LIMITS.station.defaultHours * 60;

/** The hours the setting says; the default for a missing or unknown value. */
export function stationHours(values: Readonly<Record<string, string>> | undefined): number {
  const hours = Number(values?.[STATION_HOURS_KEY]);
  return STATION_HOURS.includes(hours) ? hours : LIMITS.station.defaultHours;
}

/** How stations age for the daemon's settings. */
export function agingOf(values: Readonly<Record<string, string>> | undefined): Aging {
  return { defaultMin: stationHours(values) * 60 };
}

/** The timeout of a station in minutes, 0 for never (our own station and objects). */
export function timeoutMin(aging: Aging, row: StationRow): number {
  return row.is_me || row.own ? 0 : aging.defaultMin;
}

/** The age in seconds of the last position (the last packet if it has no position time). */
function positionAge(row: StationRow, nowMs: number): number {
  return ageSeconds(row.last_position_at ?? row.last_heard, nowMs);
}

/** Whether the station has a position older than its timeout, so it is not drawn. */
export function timedOut(aging: Aging, row: StationRow, nowMs: number): boolean {
  const minutes = timeoutMin(aging, row);
  return minutes > 0 && row.lat !== null && row.lon !== null && positionAge(row, nowMs) > minutes * 60;
}

/**
 * How far an age is towards the timeout, 0 (now) to 1; a station that never times out uses a day.
 */
export function fadeFraction(ageSec: number, minutes: number): number {
  const span = minutes > 0 ? minutes * 60 : FADE_SPAN_NEVER_SEC;
  return Math.min(1, Math.max(0, ageSec / span));
}

function stepOf(fraction: number, steps: number): number {
  return Math.min(steps - 1, Math.floor(fraction * steps));
}

/**
 * The opacity of a trail stretch whose older end is `ageSec` old: 1 for the newest, TRAIL_OLDEST at
 * the timeout.
 */
export function trailOpacity(ageSec: number, minutes: number): number {
  const step = stepOf(fadeFraction(ageSec, minutes), TRAIL_STEPS);
  return Math.round((1 - (step / (TRAIL_STEPS - 1)) * (1 - TRAIL_OLDEST)) * 100) / 100;
}

/** How dim a marker is: 0 fresh up to MARKER_STEPS - 1 before the timeout; 0 for our own. */
export function markerStep(aging: Aging, row: StationRow, nowMs: number): number {
  return row.is_me || row.own ? 0 : stepOf(fadeFraction(positionAge(row, nowMs), timeoutMin(aging, row)), MARKER_STEPS);
}
