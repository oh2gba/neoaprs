// How the page writes what the daemon tells: ages, bearings, positions, times (measured values are
// lib/units.ts). Times arrive as UTC ISO 8601 and are shown in the viewer's time. Words and the
// decimal point follow the page language (src/i18n); compass letters do not.
import { formatNumber, t } from "@/i18n";

const SECOND = 1000;
const MINUTE = 60 * SECOND;
export const HOUR_MS = 60 * MINUTE;
const DAY = 24 * HOUR_MS;

export const NONE = "-";

type Unit = "s" | "min" | "h" | "d";
const span = (unit: Unit, n: number): string => t(`time.span.${unit}`, { n });

/** The instant of a wire time in ms since 1970; NaN if it does not parse. */
function parseTime(iso: string | null): number {
  return iso === null ? NaN : Date.parse(iso);
}

/** A length of time in its largest whole unit: "12 s", "3 min", "5 h", "2 d". */
function spanText(ms: number): string {
  if (ms < MINUTE) return span("s", Math.floor(ms / SECOND));
  if (ms < HOUR_MS) return span("min", Math.floor(ms / MINUTE));
  if (ms < DAY) return span("h", Math.floor(ms / HOUR_MS));
  return span("d", Math.floor(ms / DAY));
}

/** How long ago ("12 s", "3 min"); a time in the future counts as "0 s". */
export function ageText(iso: string | null, nowMs: number): string {
  const then = parseTime(iso);
  return Number.isNaN(then) ? NONE : spanText(Math.max(0, nowMs - then));
}

/**
 * What the daemon costs the machine, as a tooltip sentence; the memory part is left out if unknown.
 */
export function processText(cpuPercent: number, rssMb: number | null, uptimeSec: number): string {
  const values = { cpu: formatNumber(cpuPercent, 1), span: spanText(Math.max(0, uptimeSec) * SECOND) };
  return rssMb === null
    ? t("footer.cost_no_memory", values)
    : t("footer.cost", { ...values, mb: formatNumber(Math.round(rssMb), 0) });
}

/** How long until ("in 12 s"); "now" once the time has come. */
export function untilText(iso: string | null, nowMs: number): string {
  const then = parseTime(iso);
  if (Number.isNaN(then)) return NONE;
  const left = then - nowMs;
  if (left <= 0) return t("time.now");
  if (left < MINUTE) return t("time.in", { span: span("s", Math.ceil(left / SECOND)) });
  if (left < HOUR_MS) return t("time.in", { span: span("min", Math.ceil(left / MINUTE)) });
  if (left < DAY) return t("time.in", { span: span("h", Math.ceil(left / HOUR_MS)) });
  return t("time.in", { span: span("d", Math.ceil(left / DAY)) });
}

/** The age in seconds of a wire time; Infinity for none. */
export function ageSeconds(iso: string | null, nowMs: number): number {
  const then = parseTime(iso);
  return Number.isNaN(then) ? Infinity : Math.max(0, (nowMs - then) / SECOND);
}

/** A number of at least two digits, with a leading zero: 7 is "07". */
export const pad2 = (n: number): string => String(n).padStart(2, "0");

/** HH:MM:SS in the viewer's time. */
export function clockText(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? NONE : `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

/** HH:MM in the viewer's time. */
export function hourMinuteText(iso: string): string {
  return clockText(iso).slice(0, 5);
}

/** "nothing heard since 02:43 (5 h)": the time of the latest byte and how long ago. */
export function silentText(since: string | null, nowMs: number): string {
  return since === null
    ? t("time.nothing_heard")
    : t("time.nothing_heard_since", { time: hourMinuteText(since), span: ageText(since, nowMs) });
}

/** YYYY-MM-DD HH:MM:SS in the viewer's time. */
export function dateTimeText(iso: string | null): string {
  if (iso === null) return NONE;
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? NONE
    : `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${clockText(iso)}`;
}

/** "2 min ago"; a dash for none. The full time belongs in a hover title (`dateTimeText`). */
export function agoWords(iso: string | null, nowMs: number): string {
  return iso === null ? NONE : t("time.ago", { span: ageText(iso, nowMs) });
}

const POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

/** The compass point of a bearing in degrees: 0 is N, 90 E. */
export function compassPoint(deg: number): string {
  return POINTS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16] ?? "N";
}

/** "123° ESE", or a dash for none. */
export function bearingText(deg: number | null): string {
  if (deg === null) return NONE;
  const whole = ((Math.round(deg) % 360) + 360) % 360;
  return `${whole}° ${compassPoint(whole)}`;
}

/** The bearing for a hover title: "NE, 47°"; a dash for none. */
export function bearingTitle(deg: number | null): string {
  if (deg === null) return NONE;
  const whole = ((Math.round(deg) % 360) + 360) % 360;
  return `${compassPoint(whole)}, ${whole}°`;
}

/**
 * "60.17000 N 24.94000 E": degrees with N or S, E or W, to `decimals` decimals (5, about a metre,
 * unless said).
 */
export function positionText(lat: number | null, lon: number | null, decimals = 5): string {
  if (lat === null || lon === null) return NONE;
  const negative = (x: number): boolean => x < 0 && Math.round(Math.abs(x) * 10 ** decimals) > 0;
  return `${formatNumber(Math.abs(lat), decimals)} ${negative(lat) ? "S" : "N"} ${formatNumber(Math.abs(lon), decimals)} ${negative(lon) ? "W" : "E"}`;
}

/** The digipeaters of a path, as the packet would carry them. */
export function pathText(path: readonly string[]): string {
  return path.length === 0 ? NONE : path.join(",");
}

const BYTE_UNITS = ["B", "kB", "MB", "GB", "TB"];

/**
 * Bytes in powers of 1000 (`15 kB`, `1.5 MB`); the unit is chosen after rounding, never `1000 kB`.
 */
export function bytesText(bytes: number): string {
  let value = Math.max(0, bytes);
  let unit = 0;
  const digitsOf = (v: number): number => (unit === 0 || Math.round(v * 10) / 10 >= 10 ? 0 : 1);
  const shown = (v: number): number => Number(v.toFixed(digitsOf(v)));
  while (unit < BYTE_UNITS.length - 1 && shown(value) >= 1000) {
    value /= 1000;
    unit += 1;
  }
  return `${formatNumber(value, digitsOf(value))} ${BYTE_UNITS[unit]}`;
}
