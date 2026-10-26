// The first-run guide's rules (components/SetupGuide.vue): the steps, the symbols it offers, what is wrong with each field as it is typed, and which settings its answers change. The daemon checks
// everything again when the guide saves; this keeps the user from sending what it would refuse, and the page from sending a key whose value is the one the daemon has.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { normalizeCall } from "@/lib/calls";
import { callOk, parseNumber, problemOf, symbolProblem } from "@/lib/fieldcheck";
import { lazyText } from "@/lib/lazytext";
import type { Choice } from "@/lib/settingchoices";
import { portForProfile, speedFallback } from "@/lib/tncprofile";
import { TNC_PROFILES } from "@/protocol/lists";
import type { PortsMessage } from "@/protocol/protocol";

const STEP_IDS: readonly MessageId[] = ["setup.step.call", "setup.step.position", "setup.step.symbol", "setup.step.radio", "setup.step.map"];
export const STEP_COUNT = STEP_IDS.length;
export const LAST_STEP = STEP_COUNT - 1;

/** The name of a step, in the language of the page. */
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

/** What the guide asks, as text the way it is typed. */
export interface SetupFields {
  call: string;
  lat: string;
  lon: string;
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

const isTcp = (f: SetupFields): boolean => profileOf(f.profile)?.transport === "tcp";
/** The Dummy radio: no radio, so no port, no speed and no host to ask for. */
export const isDummy = (f: SetupFields): boolean => profileOf(f.profile)?.transport === "dummy";
/** The step with the radio. */
export const RADIO_STEP = STEP_OF.profile;

/** The problems of the fields of each step, by field (lib/fieldcheck.ts: an empty field says nothing here). A field that is empty and needed has none: `stepOk` says Next waits for it. */
const CHECKS: ((f: SetupFields) => Problems)[] = [
  (f) => ({ call: problemOf("station/call", f.call, true) }),
  (f) => ({ lat: problemOf("station/lat", f.lat, true), lon: problemOf("station/lon", f.lon, true) }),
  (f) => ({ symbol: symbolProblem(f.symbol) }),
  (f) => {
    if (isDummy(f)) return {};
    return isTcp(f)
      ? { host: problemOf("tcp/host", f.host, true), tcpPort: problemOf("tcp/port", f.tcpPort, true) }
      : { baud: problemOf("serial/baud", f.baud, true) };
  },
  (f) => ({ radius: problemOf("map/radius_km", f.radius, true) }),
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
      return (
        profileOf(f.profile) !== undefined && (isDummy(f) || (isTcp(f) ? f.host.trim() !== "" && f.tcpPort.trim() !== "" : f.port !== "" || search !== false))
      );
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

/** The settings to save: the keys whose answer is not what the daemon has, with the text to write. Only the keys of the chosen kind of TNC (a serial TNC's port and speed, a TCP one's host and port, the Dummy radio's none), and a serial device
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
  if (isTcp(f)) {
    wanted["tcp/host"] = f.host.trim();
    wanted["tcp/port"] = f.tcpPort.trim();
    wanted["serial/port"] = portForProfile(f.profile, values["serial/port"] ?? "");
  } else if (!isDummy(f)) {
    // (the Dummy radio has no port, no speed and no address: what the settings hold stays, for the day a real radio is chosen)
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

/** The settings of the radio among the changes: what the Terminal of the Radio step saves, so that the radio it shows is the one the answers name. */
export function radioChanges(f: SetupFields, values: Readonly<Record<string, string>>): Record<string, string> {
  const keys = ["tnc/profile", "serial/port", "serial/baud", "tcp/host", "tcp/port"];
  return Object.fromEntries(Object.entries(setupChanges(f, values)).filter(([key]) => keys.includes(key)));
}

/** The ports to pick from, as a choice: "Automatic" first where the daemon looks for the radio itself, else a blank to say none is picked; each port with what the system calls it. */
export function portChoices(ports: PortsMessage | null): Choice[] {
  const first: Choice = ports?.search === false ? { value: "", label: "-" } : { value: "", label: t("setup.port_automatic") };
  const rows = (ports?.ports ?? []).map((p) => ({
    value: p.device,
    label: p.description && p.description !== "n/a" && p.description !== p.device ? `${p.device} - ${p.description}` : p.device,
  }));
  return [first, ...rows];
}
