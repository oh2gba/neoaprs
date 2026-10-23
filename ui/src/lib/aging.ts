// How stations age on the map: the timeout of a station (its own, else the default of 180 minutes; 0 is never), whether a station has passed it, and how faded the marker and
// the trail of a station are on the way there. Plain functions of rows and the time.
import { t } from "@/i18n";
import { ageSeconds } from "@/lib/format";
import { LIMITS } from "@/protocol/lists";
import type { StationRow } from "@/protocol/protocol";

/** What the page knows of the timeouts: the minutes of the stations that have one of their own (0 is never), and the default for the others (0 is never). */
export interface Aging {
  timeouts: ReadonlyMap<string, number>;
  defaultMin: number;
}

/** When a station never times out its marker and trail still fade, over this long. */
export const FADE_SPAN_NEVER_SEC = 24 * 60 * 60;
/** A trail has this many opacities, from 1 for the newest to TRAIL_OLDEST for the oldest; a marker has MARKER_STEPS looks, 0 fresh to the last one nearest the timeout. */
export const TRAIL_STEPS = 8;
export const TRAIL_OLDEST = 0.15;
export const MARKER_STEPS = 4;

/** The timeout of a station that has none of its own, in minutes: three hours (fixed, HIDE_AFTER_MIN of the daemon's policy.py; it is no setting). */
export const DEFAULT_TIMEOUT_MIN = LIMITS.station.hideAfterMin;

/** The timeout of a station in minutes, 0 for never: its own, else the default; our own station and our own objects never time out. */
export function timeoutMin(aging: Aging, row: StationRow): number {
  return row.is_me || row.own ? 0 : (aging.timeouts.get(row.call) ?? aging.defaultMin);
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

const TIMEOUT_MAX_MIN = 1_000_000;
/** How a timeout of 0 is written: "never" in the page's language. */
export const neverWord = (): string => t("station.timeout.never");

/** What was typed in a timeout field: `{ minutes: null }` for an empty field (the default), the whole minutes otherwise (0, "never" or the word for it in the page's language is never), null for text that is no timeout. */
export function parseTimeoutText(text: string): { minutes: number | null } | null {
  const trimmed = text.trim().toLowerCase();
  if (trimmed === "") return { minutes: null };
  if (trimmed === "never" || trimmed === neverWord().toLowerCase()) return { minutes: 0 };
  if (!/^\d+$/.test(trimmed)) return null;
  const minutes = Number(trimmed);
  return minutes <= TIMEOUT_MAX_MIN ? { minutes } : null;
}

/** A timeout for people: "never", "45 min", "3 h", "2 d". */
export function timeoutText(minutes: number): string {
  if (minutes <= 0) return neverWord();
  if (minutes % 1440 === 0) return t("time.span.d", { n: minutes / 1440 });
  if (minutes % 60 === 0) return t("time.span.h", { n: minutes / 60 });
  return t("time.span.min", { n: minutes });
}
