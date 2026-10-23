// How the page writes what the daemon tells: ages, distances, bearings, positions, times. Times arrive as UTC ISO 8601 with a Z and are shown in the viewer's own time.

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export const NONE = "-";

/** The instant of a time of the wire, in ms since 1970; NaN for text that is none. */
function parseTime(iso: string | null): number {
  return iso === null ? NaN : Date.parse(iso);
}

/** A length of time in ms in its largest whole unit: "12 s", "3 min", "5 h", "2 d". */
function spanText(ms: number): string {
  if (ms < MINUTE) return `${Math.floor(ms / SECOND)} s`;
  if (ms < HOUR) return `${Math.floor(ms / MINUTE)} min`;
  if (ms < DAY) return `${Math.floor(ms / HOUR)} h`;
  return `${Math.floor(ms / DAY)} d`;
}

/** How long ago: "12 s", "3 min", "5 h", "2 d". A time in the future (the clocks differ a little) is "0 s". */
export function ageText(iso: string | null, nowMs: number): string {
  const then = parseTime(iso);
  return Number.isNaN(then) ? NONE : spanText(Math.max(0, nowMs - then));
}

/** What the daemon costs the machine, short: "0.3 % · 42 MB" (the share of one core, the resident memory). */
export function processTextShort(cpuPercent: number, rssMb: number | null): string {
  return `${cpuPercent.toFixed(1)} % · ${rssMb === null ? NONE : Math.round(rssMb)} MB`;
}

/** The same with the time since it started, for a tooltip: "0.3 % · 42 MB · up 3 h". */
export function processText(cpuPercent: number, rssMb: number | null, uptimeSec: number): string {
  return `${processTextShort(cpuPercent, rssMb)} · up ${spanText(Math.max(0, uptimeSec) * SECOND)}`;
}

/** How long until: "in 12 s", "in 3 min", "in 5 h", "in 2 d"; "now" for a time that has come. */
export function untilText(iso: string | null, nowMs: number): string {
  const then = parseTime(iso);
  if (Number.isNaN(then)) return NONE;
  const left = then - nowMs;
  if (left <= 0) return "now";
  if (left < MINUTE) return `in ${Math.ceil(left / SECOND)} s`;
  if (left < HOUR) return `in ${Math.ceil(left / MINUTE)} min`;
  if (left < DAY) return `in ${Math.ceil(left / HOUR)} h`;
  return `in ${Math.ceil(left / DAY)} d`;
}

/** The age in seconds of a time of the wire, Infinity for none. */
export function ageSeconds(iso: string | null, nowMs: number): number {
  const then = parseTime(iso);
  return Number.isNaN(then) ? Infinity : Math.max(0, (nowMs - then) / SECOND);
}

const pad = (n: number): string => String(n).padStart(2, "0");

/** HH:MM:SS in the viewer's time. */
export function clockText(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? NONE : `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** "nothing heard since 02:43 (5 h)": the radio is silent; the time of the latest byte in the viewer's time and how long ago. */
export function silentText(since: string | null, nowMs: number): string {
  return since === null ? "nothing heard" : `nothing heard since ${clockText(since).slice(0, 5)} (${ageText(since, nowMs)})`;
}

/** YYYY-MM-DD HH:MM:SS in the viewer's time. */
export function dateTimeText(iso: string | null): string {
  if (iso === null) return NONE;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? NONE : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${clockText(iso)}`;
}

/** How long ago, and when: "2 min ago (2026-10-21 14:03:12)"; a dash for none. */
export function agoText(iso: string | null, nowMs: number): string {
  return iso === null ? NONE : `${ageText(iso, nowMs)} ago (${dateTimeText(iso)})`;
}

/** How long ago, in words: "2 min ago"; a dash for none. The full time goes in a hover title (`dateTimeText`). */
export function agoWords(iso: string | null, nowMs: number): string {
  return iso === null ? NONE : `${ageText(iso, nowMs)} ago`;
}

/** Kilometres, one decimal under 10 and whole above. */
export function distanceText(km: number | null): string {
  if (km === null) return NONE;
  return km < 10 ? km.toFixed(1) : String(Math.round(km));
}

const POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

/** The compass point of a bearing in degrees: 0 is N, 90 E. */
export function compassPoint(deg: number): string {
  return POINTS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16] ?? "N";
}

/** "123° ESE", or a dash for none. */
export function bearingText(deg: number | null): string {
  if (deg === null) return NONE;
  const whole = Math.round(deg);
  return `${whole}° ${compassPoint(whole)}`;
}

/** The bearing for a hover title: "NE, 47°"; a dash for none. */
export function bearingTitle(deg: number | null): string {
  if (deg === null) return NONE;
  const whole = Math.round(deg);
  return `${compassPoint(whole)}, ${whole}°`;
}

/** "60.17000 N 24.94000 E". */
export function positionText(lat: number | null, lon: number | null): string {
  if (lat === null || lon === null) return NONE;
  return `${Math.abs(lat).toFixed(5)} ${lat < 0 ? "S" : "N"} ${Math.abs(lon).toFixed(5)} ${lon < 0 ? "W" : "E"}`;
}

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
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} kB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** What is left of a limit, for the counter of a box: "12 left", or "3 over" when the text is too long. */
export function leftText(left: number): string {
  return left < 0 ? `${-left} over` : `${left} left`;
}
