// What the page checks of a setting before it sends it, once the person has finished the field (Enter, or leaving it): enough to keep a half-typed call, position or number from going to the daemon. The daemon checks every
// value again against the settings in force (and the rules between settings: the comment against the power, the status against the rigctld, the port against the radio type); its refusal is shown under the field.
import { normalizeCall, parsePath } from "@/lib/calls";
import { callProblem, degreesProblem, parseNumber } from "@/lib/setup";

interface Whole {
  min: number;
  max: number;
  /** an empty field is a value (none, or the profile's own) */
  empty?: boolean;
}

/** The limits of the daemon's whole numbers (neoaprs/config.py). */
const WHOLE: Record<string, Whole> = {
  "serial/baud": { min: 300, max: 921600, empty: true },
  "tcp/port": { min: 1, max: 65535 },
  "beacon/power_w": { min: 0, max: 9999, empty: true },
  "beacon/antenna_height_m": { min: 0, max: 9999 },
  "beacon/antenna_gain_db": { min: 0, max: 9 },
  "map/radius_km": { min: 10, max: 1000 },
};

function wholeProblem(text: string, limits: Whole): string {
  const value = text.trim();
  if (value === "") return limits.empty ? "" : `${limits.min} to ${limits.max}`;
  const n = /^\d+$/.test(value) ? Number(value) : NaN;
  return n >= limits.min && n <= limits.max ? "" : `${limits.min} to ${limits.max}`;
}

/** What is wrong with the text of a setting as it stands, or "" when the page has nothing against it (the daemon may still refuse it). */
export function problemOf(key: string, text: string): string {
  const limits = WHOLE[key];
  if (limits) return wholeProblem(text, limits);
  switch (key) {
    case "station/call":
      return callProblem(text);
    case "station/lat":
      return degreesProblem(text, 90);
    case "station/lon":
      return degreesProblem(text, 180);
    case "tcp/host":
      return text.trim() === "" || /\s/.test(text.trim()) ? "Not an address" : "";
    case "beacon/path":
      return parsePath(text) === null ? "Calls separated by commas, 8 at the most" : "";
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
  if (lat !== "" && lon === "") return { "station/lon": "Needed with the latitude" };
  if (lon !== "" && lat === "") return { "station/lat": "Needed with the longitude" };
  return {};
}
