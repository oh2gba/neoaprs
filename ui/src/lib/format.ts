// How the page writes what the daemon tells: ages, distances, bearings, positions, times. Times arrive as UTC ISO 8601 with a Z and are shown in the viewer's own time. The words (the units of a length of time, "ago", "in") and
// the way a number is written (the decimal point) are the page's language's (src/i18n); the units of measure (km, MB, hPa, °C) and the compass letters are the same in every language.
import { formatNumber, t } from "@/i18n";

const SECOND = 1000;
const MINUTE = 60 * SECOND;
export const HOUR_MS = 60 * MINUTE;
const DAY = 24 * HOUR_MS;

export const NONE = "-";

type Unit = "s" | "min" | "h" | "d";
const span = (unit: Unit, n: number): string => t(`time.span.${unit}`, { n });

/** The instant of a time of the wire, in ms since 1970; NaN for text that is none. */
function parseTime(iso: string | null): number {
  return iso === null ? NaN : Date.parse(iso);
}

/** A length of time in ms in its largest whole unit: "12 s", "3 min", "5 h", "2 d". */
function spanText(ms: number): string {
  if (ms < MINUTE) return span("s", Math.floor(ms / SECOND));
  if (ms < HOUR_MS) return span("min", Math.floor(ms / MINUTE));
  if (ms < DAY) return span("h", Math.floor(ms / HOUR_MS));
  return span("d", Math.floor(ms / DAY));
}

/** How long ago: "12 s", "3 min", "5 h", "2 d". A time in the future (the clocks differ a little) is "0 s". */
export function ageText(iso: string | null, nowMs: number): string {
  const then = parseTime(iso);
  return Number.isNaN(then) ? NONE : spanText(Math.max(0, nowMs - then));
}

/** What the daemon costs the machine, in a sentence of the page's language, for a tooltip: "NeoAPRS uses 0.3 % of one processor core and 42 MB of memory, running for 3 h" (without the memory when it is not known). */
export function processText(cpuPercent: number, rssMb: number | null, uptimeSec: number): string {
  const values = { cpu: formatNumber(cpuPercent, 1), span: spanText(Math.max(0, uptimeSec) * SECOND) };
  return rssMb === null ? t("footer.cost_no_memory", values) : t("footer.cost", { ...values, mb: formatNumber(Math.round(rssMb), 0) });
}

/** How long until: "in 12 s", "in 3 min", "in 5 h", "in 2 d"; "now" for a time that has come. */
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

/** The age in seconds of a time of the wire, Infinity for none. */
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

/** "nothing heard since 02:43 (5 h)": the radio is silent; the time of the latest byte in the viewer's time and how long ago. */
export function silentText(since: string | null, nowMs: number): string {
  return since === null ? t("time.nothing_heard") : t("time.nothing_heard_since", { time: hourMinuteText(since), span: ageText(since, nowMs) });
}

/** YYYY-MM-DD HH:MM:SS in the viewer's time. */
export function dateTimeText(iso: string | null): string {
  if (iso === null) return NONE;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? NONE : `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${clockText(iso)}`;
}

/** How long ago, in words: "2 min ago"; a dash for none. The full time goes in a hover title (`dateTimeText`). */
export function agoWords(iso: string | null, nowMs: number): string {
  return iso === null ? NONE : t("time.ago", { span: ageText(iso, nowMs) });
}

/** Kilometres, one decimal under 10 and whole above; the figure is rounded first, so that 9.96 is "10" and not "10.0". */
export function distanceText(km: number | null): string {
  if (km === null) return NONE;
  const tenths = Math.round(km * 10) / 10;
  return tenths < 10 ? formatNumber(tenths, 1) : String(Math.round(km));
}

const POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

/** The compass point of a bearing in degrees: 0 is N, 90 E. */
export function compassPoint(deg: number): string {
  return POINTS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16] ?? "N";
}

/** "123° ESE", or a dash for none. */
export function bearingText(deg: number | null): string {
  if (deg === null) return NONE;
  const whole = Math.round(deg) % 360;
  return `${whole}° ${compassPoint(whole)}`;
}

/** The bearing for a hover title: "NE, 47°"; a dash for none. */
export function bearingTitle(deg: number | null): string {
  if (deg === null) return NONE;
  const whole = Math.round(deg) % 360;
  return `${compassPoint(whole)}, ${whole}°`;
}

/** "60.17000 N 24.94000 E": degrees with N or S, E or W, to `decimals` decimals (5, about a metre, unless said). */
export function positionText(lat: number | null, lon: number | null, decimals = 5): string {
  if (lat === null || lon === null) return NONE;
  return `${formatNumber(Math.abs(lat), decimals)} ${lat < 0 ? "S" : "N"} ${formatNumber(Math.abs(lon), decimals)} ${lon < 0 ? "W" : "E"}`;
}

/** A speed in whole km/h; a dash for none. */
export function speedText(kmh: number | null): string {
  return kmh === null ? NONE : `${Math.round(kmh)} km/h`;
}

export function altitudeText(m: number | null): string {
  return m === null ? NONE : `${Math.round(m)} m`;
}

/** The digipeaters of a path, as the packet would carry them. */
export function pathText(path: readonly string[]): string {
  return path.length === 0 ? NONE : path.join(",");
}

/** Bytes as "1.5 kB". */
export function bytesText(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${formatNumber(n / 1024, 1)} kB`;
  return `${formatNumber(n / (1024 * 1024), 1)} MB`;
}
