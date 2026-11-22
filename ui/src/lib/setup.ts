// The first-run guide's rules (components/SetupGuide.vue): the steps, the offered symbols,
// per-field problems as typed, and which settings the answers change. The daemon checks everything
// again on save; this stops the guide sending what would be refused. The Radio step is live like
// the Settings Radio group; Finish needs `radioReady`.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { normalizeCall } from "@/lib/calls";
import { callOk, parseNumber, problemOf, symbolProblem } from "@/lib/fieldcheck";
import { lazyText } from "@/lib/lazytext";
import type { PageRadio } from "@/lib/radios";
import { boxKeys, fieldOfKey } from "@/lib/settingsradio";

const STEP_IDS: readonly MessageId[] = [
  "setup.step.call",
  "setup.step.position",
  "setup.step.symbol",
  "setup.step.radio",
];
export const STEP_COUNT = STEP_IDS.length;
export const LAST_STEP = STEP_COUNT - 1;

export const stepTitle = (step: number): string => {
  const id = STEP_IDS[step];
  return id === undefined ? "" : t(id);
};

/** The 12 symbols most stations use, in the primary table. */
export const SYMBOL_CHOICES: readonly { readonly table: "/"; readonly code: string; readonly name: string }[] = (
  [
    ["-", "setup.symbol.house"],
    [">", "setup.symbol.car"],
    ["k", "setup.symbol.truck"],
    ["v", "setup.symbol.van"],
    ["<", "setup.symbol.motorcycle"],
    ["b", "setup.symbol.bike"],
    ["[", "setup.symbol.walker"],
    ["s", "setup.symbol.boat"],
    ["#", "setup.symbol.digipeater"],
    ["_", "setup.symbol.weather_station"],
    [";", "setup.symbol.portable"],
    ["r", "setup.symbol.antenna"],
  ] as const satisfies readonly (readonly [string, MessageId])[]
).map(([code, id]) => lazyText({ table: "/" as const, code }, { name: () => t(id) }));

/** What the guide asks, as typed text. */
export interface SetupFields {
  call: string;
  lat: string;
  lon: string;
  /** The table character and the code character: `/-`. */
  symbol: string;
}

export type FieldName = keyof SetupFields;
export type Problems = Partial<Record<FieldName, string>>;

export const STEP_OF: Record<FieldName, number> = {
  call: 0,
  lat: 1,
  lon: 1,
  symbol: 2,
};

/**
 * The setting each field answers (locator and symbol characters are exceptions: they make other
 * keys).
 */
export const KEY_OF: Record<string, FieldName> = {
  "station/call": "call",
  "station/lat": "lat",
  "station/lon": "lon",
  "station/symbol_table": "symbol",
  "station/symbol_code": "symbol",
};

export const RADIO_STEP = STEP_IDS.indexOf("setup.step.radio");

/**
 * Problems of each step's fields, by field (lib/fieldcheck.ts). An empty needed field has none:
 * `stepOk` holds Next.
 */
const CHECKS: ((f: SetupFields) => Problems)[] = [
  (f) => ({ call: problemOf("station/call", f.call, true) }),
  (f) => ({ lat: problemOf("station/lat", f.lat, true), lon: problemOf("station/lon", f.lon, true) }),
  (f) => ({ symbol: symbolProblem(f.symbol) }),
];

export function stepProblems(step: number, f: SetupFields): Problems {
  return Object.fromEntries(Object.entries(CHECKS[step]?.(f) ?? {}).filter(([, text]) => text !== ""));
}

/**
 * Whether the step has all its answers, filled and without a problem. The Radio step has none (see
 * `radioReady`).
 */
export function stepOk(step: number, f: SetupFields): boolean {
  if (Object.keys(stepProblems(step, f)).length > 0) return false;
  switch (step) {
    case 0:
      return callOk(f.call);
    case 1:
      return parseNumber(f.lat) !== null && parseNumber(f.lon) !== null;
    case 2:
      return f.symbol.length === 2;
    default:
      return true;
  }
}

/** A position as the settings keep it: no trailing zeros, at most six decimals. */
export function degreesText(value: number): string {
  return String(Math.round(value * 1e6) / 1e6);
}

/**
 * A coordinate to five decimals (a metre), as a place picked on the map or found by the browser is
 * kept.
 */
export function roundPlace(degrees: number): number {
  return Math.round(degrees * 1e5) / 1e5;
}

/** A longitude brought into -180 to 180, to the metre. */
export function wrapLongitude(lon: number): number {
  return roundPlace(((((lon + 180) % 360) + 360) % 360) - 180);
}

/**
 * Whether a setting's text is the same position or number as the daemon's, however written
 * (`60.170` and `60.17`).
 */
function sameNumber(a: string, b: string): boolean {
  const x = parseNumber(a);
  const y = parseNumber(b);
  return x !== null && y !== null ? x === y : a.trim() === b.trim();
}

/** The guide's fields as they are for the daemon's current settings: the guide's first state. */
export function fieldsFrom(values: Readonly<Record<string, string>>): SetupFields {
  return {
    call: values["station/call"] ?? "",
    lat: values["station/lat"] ?? "",
    lon: values["station/lon"] ?? "",
    symbol: `${values["station/symbol_table"] ?? "/"}${values["station/symbol_code"] ?? "-"}`,
  };
}

/**
 * How often a new station beacons, in minutes. The first save sets it so that the daemon's default
 * can stay Off.
 */
export const NEW_STATION_BEACON_MIN = "30";

/** The daemon has no call and no beacon: the first run. */
function isNewStation(values: Readonly<Record<string, string>>): boolean {
  return (values["station/call"] ?? "") === "" && ["", "0"].includes((values["beacon/interval_min"] ?? "").trim());
}

/**
 * The settings to save at Finish: keys whose answer differs from the daemon's, with the text to
 * write. A station with no call and no beacon interval gets a beacon every NEW_STATION_BEACON_MIN
 * minutes in the same save.
 */
export function setupChanges(f: SetupFields, values: Readonly<Record<string, string>>): Record<string, string> {
  const wanted: Record<string, string> = {
    "station/call": normalizeCall(f.call),
    "station/lat": parseNumber(f.lat) === null ? f.lat.trim() : degreesText(parseNumber(f.lat) ?? 0),
    "station/lon": parseNumber(f.lon) === null ? f.lon.trim() : degreesText(parseNumber(f.lon) ?? 0),
    "station/symbol_table": f.symbol.slice(0, 1),
    "station/symbol_code": f.symbol.slice(1),
  };
  if (isNewStation(values)) wanted["beacon/interval_min"] = NEW_STATION_BEACON_MIN;
  return Object.fromEntries(Object.entries(wanted).filter(([key, text]) => !sameNumber(text, values[key] ?? "")));
}

/**
 * What the Radio step's radios are read from: the form's settings (values, pending changes, errors)
 * and whether the daemon searches the ports for a serial radio itself (`search`, null before it has
 * said).
 */
export interface RadioStep {
  values: Readonly<Record<string, string>>;
  draft: Readonly<Record<string, string>>;
  errors: Readonly<Record<string, string>>;
  search: boolean | null;
}

/**
 * Whether the Radio step has what Finish needs (plan section 6): a radio that is on with no
 * complaint on any field, the page's or the daemon's. An empty serial port is a problem where the
 * daemon does not search for the radio.
 */
export function radioReady(radios: readonly PageRadio[], step: RadioStep): boolean {
  const right = (radio: PageRadio): boolean =>
    boxKeys(radio).every(
      (key) =>
        (step.errors[key] ?? "") === "" &&
        !(step.search === false && fieldOfKey(key) === "port" && (step.draft[key] ?? "") === ""),
    );
  return radios.some((radio) => !radio.removed && radio.enabled && right(radio));
}
