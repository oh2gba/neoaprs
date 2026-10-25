// What the page checks of a value before it sends it, for the settings form (once the person has finished the field: Enter, or leaving it) and for the first-run guide (as it is typed): enough to keep a half-typed call, position or
// number from going to the daemon. Every figure is LIMITS (the daemon's own constants); the rules that are code are held to the daemon's by ui/src/protocol/vectors.json. The daemon checks every value again against the settings
// in force (and the rules between settings: the comment against the power, the status against the rigctld, the port against the radio type); its refusal is shown under the field.
import { t } from "@/i18n";
import { baseCall, mayTransmitAs, normalizeCall, parsePathSetting, placeholderCall } from "@/lib/calls";
import { LIMITS, SYMBOL_TABLES } from "@/protocol/lists";

/** The whole numbers the daemon limits, by setting: whether an empty field is a value (none, or the profile's own). */
const WHOLE: Record<string, boolean> = {
  "serial/baud": true,
  "tcp/port": false,
  "beacon/power_w": true,
  "beacon/antenna_height_m": false,
  "beacon/antenna_gain_db": false,
  "map/radius_km": false,
  "gps/baud": true,
  "smart/fast_kmh": true,
  "smart/fast_sec": true,
  "smart/slow_kmh": true,
  "smart/slow_sec": true,
  "smart/turn_min_deg": true,
  "smart/turn_min_sec": true,
  "smart/turn_slope": true,
};

/** A number as typed: a comma is a decimal point; null for text that is no number. */
export function parseNumber(text: string): number | null {
  const clean = text.trim().replace(",", ".");
  return /^[-+]?(\d+\.?\d*|\.\d+)$/.test(clean) ? Number(clean) : null;
}

function wholeProblem(key: string, text: string, quiet: boolean): string {
  const { min, max } = LIMITS.range[key as keyof typeof LIMITS.range];
  const value = text.trim();
  if (value === "") return WHOLE[key] || quiet ? "" : t("settings.check.range", { min, max });
  const n = /^\d+$/.test(value) ? Number(value) : NaN;
  return n >= min && n <= max ? "" : t("settings.check.range", { min, max });
}

/** Whether a latitude and a longitude are a place on the earth (the settings' limits). */
export function onEarth(lat: number, lon: number): boolean {
  const { "station/lat": latitude, "station/lon": longitude } = LIMITS.range;
  return Math.abs(lat) <= latitude.max && Math.abs(lon) <= longitude.max;
}

/** What is wrong with a call as it stands, or "" when it is fine (or still empty: Next waits for it, but nothing is said yet). A placeholder such as N0CALL is the call the programs ship with, never a call. */
export function callProblem(text: string): string {
  if (text.trim() === "") return "";
  if (placeholderCall(text)) return t("settings.check.placeholder_call", { call: baseCall(text) });
  return mayTransmitAs(text) ? "" : t("settings.check.not_call");
}

export function callOk(text: string): boolean {
  return text.trim() !== "" && callProblem(text) === "";
}

/** What is wrong with a latitude or a longitude (`limit` 90 or 180), "" when it is fine or empty. */
export function degreesProblem(text: string, limit: number): string {
  if (text.trim() === "") return "";
  const value = parseNumber(text);
  if (value === null) return t("settings.check.not_number");
  return Math.abs(value) <= limit ? "" : t("settings.check.between", { limit });
}

export function symbolProblem(text: string): string {
  if (text === "") return "";
  const table = text[0] ?? "";
  const code = text[1] ?? "";
  if (text.length !== 2) return t("settings.check.symbol_length");
  if (!SYMBOL_TABLES.includes(table)) return t("settings.check.symbol_table");
  return code >= "!" && code <= "~" ? "" : t("settings.check.symbol_code");
}

/** What is wrong with the text of a setting as it stands, or "" when the page has nothing against it (the daemon may still refuse it). `quiet`: an empty field says nothing, whether or not the setting needs a value (the guide:
 * its Next waits for the answer). */
export function problemOf(key: string, text: string, quiet = false): string {
  if (key in WHOLE) return wholeProblem(key, text, quiet);
  switch (key) {
    case "station/call":
      return callProblem(text);
    case "station/lat":
      return degreesProblem(text, LIMITS.range["station/lat"].max);
    case "station/lon":
      return degreesProblem(text, LIMITS.range["station/lon"].max);
    case "tcp/host":
      return (text.trim() === "" && !quiet) || /\s/.test(text.trim()) ? t("settings.check.not_address") : "";
    case "beacon/path":
      return parsePathSetting(text) === null ? t("settings.check.path", { max: LIMITS.path.maxCalls }) : "";
    default:
      return "";
  }
}

/** Whether the text typed is the value the daemon has already, however it is written (`60.170` and `60.17`, `oh2gba` and `OH2GBA`): nothing then needs sending. */
export function sameValue(key: string, typed: string, current: string): boolean {
  if (typed === current) return true;
  if (key === "station/call") return normalizeCall(typed) === current;
  if (key === "station/lat" || key === "station/lon" || key in WHOLE) {
    const a = parseNumber(typed);
    return a !== null && a === parseNumber(current);
  }
  return false;
}

/** What is wrong with the keys of a pair taken together: a position needs both its latitude and its longitude (both empty is no position, which is fine), so one empty while the other is not is refused, under the empty one. */
export function pairProblems(keys: readonly string[], texts: Readonly<Record<string, string>>): Record<string, string> {
  if (!keys.includes("station/lat") || !keys.includes("station/lon")) return {};
  const lat = (texts["station/lat"] ?? "").trim();
  const lon = (texts["station/lon"] ?? "").trim();
  if (lat !== "" && lon === "") return { "station/lon": t("settings.check.needs_latitude") };
  if (lon !== "" && lat === "") return { "station/lat": t("settings.check.needs_longitude") };
  return {};
}
