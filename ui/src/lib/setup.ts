// The first-run guide's rules (components/SetupGuide.vue): the steps, the symbols it offers, what is wrong with each field as it is typed, and which settings its answers change. The daemon checks
// everything again when the guide saves; this keeps the user from sending what it would refuse, and the page from sending a key whose value is the one the daemon has.
import { normalizeCall, validCall } from "@/lib/calls";
import { locatorToPosition, positionToLocator } from "@/lib/locator";
import { portForProfile, speedFallback, type Choice } from "@/lib/settings";
import { SYMBOL_TABLES, TNC_PROFILES } from "@/protocol/lists";
import type { PortsMessage } from "@/protocol/protocol";

export const STEP_TITLES = ["Call", "Position", "Symbol", "Radio", "Map"] as const;
export const LAST_STEP = STEP_TITLES.length - 1;

/** The 12 symbols most stations use, in the primary table. */
export const SYMBOL_CHOICES = [
  { table: "/", code: "-", name: "House" },
  { table: "/", code: ">", name: "Car" },
  { table: "/", code: "k", name: "Truck" },
  { table: "/", code: "v", name: "Van" },
  { table: "/", code: "<", name: "Motorcycle" },
  { table: "/", code: "b", name: "Bike" },
  { table: "/", code: "[", name: "Walker" },
  { table: "/", code: "s", name: "Boat" },
  { table: "/", code: "#", name: "Digipeater" },
  { table: "/", code: "_", name: "Weather station" },
  { table: "/", code: ";", name: "Portable" },
  { table: "/", code: "r", name: "Antenna" },
] as const;

/** The limits of the daemon's settings (MAP_RADIUS_KM, MAP_MAXZOOM and the speeds of neoaprs/config.py). */
const RADIUS = { min: 10, max: 1000 };
const BAUD = { min: 300, max: 921600 };

/** What the guide asks, as text the way it is typed. */
export interface SetupFields {
  call: string;
  lat: string;
  lon: string;
  locator: string;
  /** the table character and the code character: `/-` */
  symbol: string;
  profile: string;
  port: string;
  baud: string;
  host: string;
  tcpPort: string;
  radius: string;
}

export type FieldName = keyof SetupFields;
export type Problems = Partial<Record<FieldName, string>>;

/** The step a field is on. */
export const STEP_OF: Record<FieldName, number> = {
  call: 0,
  lat: 1,
  lon: 1,
  locator: 1,
  symbol: 2,
  profile: 3,
  port: 3,
  baud: 3,
  host: 3,
  tcpPort: 3,
  radius: 4,
};

/** The setting each field is the answer to (the locator and the symbol's two characters are the exceptions: they make other keys). */
export const KEY_OF: Record<string, FieldName> = {
  "station/call": "call",
  "station/lat": "lat",
  "station/lon": "lon",
  "station/symbol_table": "symbol",
  "station/symbol_code": "symbol",
  "tnc/profile": "profile",
  "serial/port": "port",
  "serial/baud": "baud",
  "tcp/host": "host",
  "tcp/port": "tcpPort",
  "map/radius_km": "radius",
};

export const profileOf = (key: string) => TNC_PROFILES.find((p) => p.key === key);

/** A number as typed: a comma is a decimal point; null for text that is no number. */
export function parseNumber(text: string): number | null {
  const clean = text.trim().replace(",", ".");
  return /^[-+]?(\d+\.?\d*|\.\d+)$/.test(clean) ? Number(clean) : null;
}

function wholeIn(text: string, min: number, max: number): boolean {
  const value = text.trim();
  return /^\d+$/.test(value) && Number(value) >= min && Number(value) <= max;
}

/** What is wrong with a call as it stands, or "" when it is fine (or still empty: Next waits for it, but nothing is said yet). N0CALL is the placeholder the programs ship with, never a call. */
export function callProblem(text: string): string {
  if (text.trim() === "") return "";
  if (normalizeCall(text).split("-")[0] === "N0CALL") return "N0CALL is not a call";
  return validCall(text) ? "" : "Not a call";
}

export function callOk(text: string): boolean {
  return text.trim() !== "" && callProblem(text) === "";
}

/** What is wrong with a latitude or a longitude (`limit` 90 or 180), "" when it is fine or empty. */
export function degreesProblem(text: string, limit: number): string {
  if (text.trim() === "") return "";
  const value = parseNumber(text);
  if (value === null) return "Not a number";
  return Math.abs(value) <= limit ? "" : `Between -${limit} and ${limit}`;
}

export function symbolProblem(text: string): string {
  if (text === "") return "";
  const table = text[0] ?? "";
  const code = text[1] ?? "";
  if (text.length !== 2) return "Table and code";
  if (!SYMBOL_TABLES.includes(table)) return "Table: / \\ 0-9 A-Z";
  return code >= "!" && code <= "~" ? "" : "Code: one printable character";
}

const whole = (text: string, min: number, max: number): string => (text.trim() === "" || wholeIn(text, min, max) ? "" : `${min} to ${max}`);

const isTcp = (f: SetupFields): boolean => profileOf(f.profile)?.transport === "tcp";

/** The problems of the fields of each step, by field. A field that is empty and needed has none here: `stepOk` says Next waits for it. */
const CHECKS: ((f: SetupFields) => Problems)[] = [
  (f) => ({ call: callProblem(f.call) }),
  (f) => ({ lat: degreesProblem(f.lat, 90), lon: degreesProblem(f.lon, 180) }),
  (f) => ({ symbol: symbolProblem(f.symbol) }),
  (f) =>
    isTcp(f) ? { host: /\s/.test(f.host.trim()) ? "Not an address" : "", tcpPort: whole(f.tcpPort, 1, 65535) } : { baud: whole(f.baud, BAUD.min, BAUD.max) },
  (f) => ({ radius: whole(f.radius, RADIUS.min, RADIUS.max) }),
];

export function stepProblems(step: number, f: SetupFields): Problems {
  return Object.fromEntries(Object.entries(CHECKS[step]?.(f) ?? {}).filter(([, text]) => text !== ""));
}

/** Whether the step has all it needs: its fields filled and without a problem. `search` is whether the daemon looks for the radio itself (null before it has said): where it does not, a serial TNC needs the port picked. */
export function stepOk(step: number, f: SetupFields, search: boolean | null): boolean {
  if (Object.keys(stepProblems(step, f)).length > 0) return false;
  switch (step) {
    case 0:
      return callOk(f.call);
    case 1:
      return parseNumber(f.lat) !== null && parseNumber(f.lon) !== null;
    case 2:
      return f.symbol.length === 2;
    case 3:
      return profileOf(f.profile) !== undefined && (isTcp(f) ? f.host.trim() !== "" && f.tcpPort.trim() !== "" : f.port !== "" || search !== false);
    default:
      return f.radius.trim() !== "";
  }
}

/** A position as the settings keep it: no trailing zeros, six decimals at the most. */
export function degreesText(value: number): string {
  return String(Math.round(value * 1e6) / 1e6);
}

/** Whether the text of a setting is the same position or number as the daemon's, however it is written (`60.170` and `60.17`). */
function sameNumber(a: string, b: string): boolean {
  const x = parseNumber(a);
  const y = parseNumber(b);
  return x !== null && y !== null ? x === y : a.trim() === b.trim();
}

/** The speed of the line as the form shows it: empty when it is the profile's own (that is what the field's placeholder says). */
export function baudShown(profileKey: string, baud: string): string {
  return baud.trim() === speedFallback(profileKey, "") ? "" : baud.trim();
}

/** The guide's fields as they are while the daemon's settings are what they are: the first state of the guide. */
export function fieldsFrom(values: Readonly<Record<string, string>>): SetupFields {
  const profile = values["tnc/profile"] ?? "";
  return {
    call: values["station/call"] ?? "",
    lat: values["station/lat"] ?? "",
    lon: values["station/lon"] ?? "",
    locator: "",
    symbol: `${values["station/symbol_table"] ?? "/"}${values["station/symbol_code"] ?? "-"}`,
    profile,
    port: values["serial/port"] ?? "",
    baud: baudShown(profile, values["serial/baud"] ?? ""),
    host: values["tcp/host"] ?? "",
    tcpPort: values["tcp/port"] ?? "",
    radius: values["map/radius_km"] ?? "",
  };
}

/** How often a new station beacons, in minutes: the guide sets it with the first call, so that the daemon's default can stay Off (an upgrade never starts to transmit). */
export const NEW_STATION_BEACON_MIN = "30";

/** The daemon has no call and no beacon: the first run. */
function isNewStation(values: Readonly<Record<string, string>>): boolean {
  return (values["station/call"] ?? "") === "" && ["", "0"].includes((values["beacon/interval_min"] ?? "").trim());
}

/** The settings to save: the keys whose answer is not what the daemon has, with the text to write. Only the keys of the chosen kind of TNC (a serial TNC's port and speed, a TCP one's host and port), and a serial device
 * the daemon holds is cleared when the TNC is a TCP one, which it would refuse otherwise. A station that has no call yet (the first run) and no beacon interval gets the beacon every NEW_STATION_BEACON_MIN minutes in the same save;
 * the guide run again on a station that has a call leaves the beacon as it is. */
export function setupChanges(f: SetupFields, values: Readonly<Record<string, string>>): Record<string, string> {
  const wanted: Record<string, string> = {
    "station/call": normalizeCall(f.call),
    "station/lat": parseNumber(f.lat) === null ? f.lat.trim() : degreesText(parseNumber(f.lat) ?? 0),
    "station/lon": parseNumber(f.lon) === null ? f.lon.trim() : degreesText(parseNumber(f.lon) ?? 0),
    "station/symbol_table": f.symbol.slice(0, 1),
    "station/symbol_code": f.symbol.slice(1),
    "tnc/profile": f.profile,
    "map/radius_km": f.radius.trim(),
  };
  if (isNewStation(values)) wanted["beacon/interval_min"] = NEW_STATION_BEACON_MIN;
  if (profileOf(f.profile)?.transport === "tcp") {
    wanted["tcp/host"] = f.host.trim();
    wanted["tcp/port"] = f.tcpPort.trim();
    wanted["serial/port"] = portForProfile(f.profile, values["serial/port"] ?? "");
  } else {
    wanted["serial/port"] = f.port;
    wanted["serial/baud"] = f.baud.trim();
  }
  const changes: Record<string, string> = {};
  for (const [key, text] of Object.entries(wanted)) {
    const had = values[key] ?? "";
    const same = key === "serial/baud" ? baudShown(f.profile, text) === baudShown(f.profile, had) : sameNumber(text, had);
    if (!same) changes[key] = text;
  }
  return changes;
}

/** The ports to pick from, as a choice: "Automatic" first where the daemon looks for the radio itself, else a blank to say none is picked; each port with what the system calls it. */
export function portChoices(ports: PortsMessage | null): Choice[] {
  const first: Choice = ports?.search === false ? { value: "", label: "-" } : { value: "", label: "Automatic" };
  const rows = (ports?.ports ?? []).map((p) => ({
    value: p.device,
    label: p.description && p.description !== "n/a" && p.description !== p.device ? `${p.device} - ${p.description}` : p.device,
  }));
  return [first, ...rows];
}

/** The locator of the position the fields hold, "" while they hold none. */
export function locatorOf(f: Pick<SetupFields, "lat" | "lon">): string {
  const lat = parseNumber(f.lat);
  const lon = parseNumber(f.lon);
  return lat === null || lon === null ? "" : positionToLocator(lat, lon);
}

const LOCATOR_FROM = 6; // a locator of fewer characters is still being typed

/** The locator field's own problem: it is said once there are 6 characters and they are not one (7 is a locator of 8 on the way). */
export function locatorProblem(text: string): string {
  const typed = text.trim();
  return typed.length >= LOCATOR_FROM && typed.length !== 7 && locatorToPosition(typed) === null ? "Not a locator" : "";
}
