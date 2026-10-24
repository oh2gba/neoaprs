// The settings form's logic: which key goes in which group, what each field says of itself, and which field an error of the daemon is about.
// The keys and their order come from the daemon (CONFIG_KEYS of the generated lists); a key this file does not know is shown under its own name.
// What a field says of itself is words of the catalogue (i18n/en/settings.ts), made when they are read: `FIELDS[key].label` is in the language the page has at that moment, so a template that reads it follows a change of language.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { errorReason, type Failure } from "@/i18n/errortext";
import type { Params } from "@/i18n/message";
import { STATION_HOURS, STATION_HOURS_KEY } from "@/lib/aging";
import { lazyText } from "@/lib/lazytext";
import { STATUS_CHOICES, statusShown, statusSource } from "@/lib/status";
import { CONFIG_KEYS, LIMITS, TNC_PROFILES } from "@/protocol/lists";

type FieldKind = "text" | "bool" | "readonly" | "choice";

export interface FieldInfo {
  label: string;
  /** What the toast calls the setting after a change ("Beacon interval changed"), when the label alone does not say it. */
  name?: string;
  /** After the input: "min", "W", "km/h". */
  unit?: string;
  /** The placeholder of a field whose empty value means something ("none", "auto", "direct"); else the placeholder is the default. */
  empty?: string;
  /** On hover: the one thing a word cannot say. */
  title?: string;
  /** The text of the (i) beside the field, one paragraph for each entry: what the setting is for, what to pick, an example. Only for a field a non-developer may not understand. */
  tip?: readonly string[];
  /** What the (i) is called for a screen reader and on hover; else "About" and the label. */
  tipLabel?: string;
  kind?: FieldKind;
  /** The values a `choice` offers: the text of the setting, or the text with the words it is shown as. */
  choices?: readonly (string | Choice)[];
  /** The words for a value that is none of the choices (a setting stored from the shell): "Every 20 min"; else the value itself. */
  other?: (value: string) => string;
}

export interface Choice {
  value: string;
  label: string;
}

/** A text of the page: the id of a message, the id with its values, or a function that makes the words (for what is no message: a port, an address). */
type Say = MessageId | readonly [MessageId, Params] | (() => string);
const said = (say: Say): string => (typeof say === "function" ? say() : typeof say === "string" ? t(say) : t(say[0], say[1]));
/** Words that are the same in every language and are no message. */
const plain =
  (text: string): Say =>
  () =>
    text;

/** What a field is, in ids: the words are looked up when they are read. */
interface FieldSpec {
  label: Say;
  name?: Say;
  unit?: string;
  empty?: Say;
  title?: Say;
  tip?: readonly Say[];
  tipLabel?: Say;
  kind?: FieldKind;
  choices?: () => readonly (string | Choice)[];
  other?: (value: string) => string;
}

/** The field of a spec, with its words as getters. */
function field(spec: FieldSpec): FieldInfo {
  const info = {} as FieldInfo;
  const words = (key: "label" | "name" | "empty" | "title" | "tipLabel", say: Say | undefined): void => {
    if (say !== undefined) Object.defineProperty(info, key, { enumerable: true, get: () => said(say) });
  };
  words("label", spec.label);
  words("name", spec.name);
  words("empty", spec.empty);
  words("title", spec.title);
  words("tipLabel", spec.tipLabel);
  const tip = spec.tip;
  if (tip !== undefined) Object.defineProperty(info, "tip", { enumerable: true, get: () => tip.map(said) });
  if (spec.choices !== undefined) Object.defineProperty(info, "choices", { enumerable: true, get: spec.choices });
  if (spec.unit !== undefined) info.unit = spec.unit;
  if (spec.kind !== undefined) info.kind = spec.kind;
  if (spec.other !== undefined) info.other = spec.other;
  return info;
}

const every = (minutes: number | string): string => t("settings.every_min", { minutes });

/** The status's choices: every 30 or 60 minutes or every 2 hours (15 is the least the daemon takes). */
const statusIntervalChoices = (): readonly Choice[] => [
  { value: "30", label: every(30) },
  { value: "60", label: every(60) },
  { value: "120", label: t("settings.every_hours", { n: 2 }) },
];

/** The beacon's choices: off, or every 30 or 60 minutes or every 3 hours (20 is the least the daemon takes; a stored 20 shows as one more choice). */
const beaconChoices = (): readonly Choice[] => [
  { value: "0", label: t("settings.beacon_interval.off") },
  { value: "30", label: every(30) },
  { value: "60", label: every(60) },
  { value: "180", label: t("settings.every_hours", { n: 3 }) },
];

/** How long a station stays on the map: 1 h, 3 h, 6 h, 12 h or 24 h (the Stations tab offers them). */
const stationHoursChoices = (): readonly Choice[] => STATION_HOURS.map((hours) => ({ value: String(hours), label: t("station.table.hours", { n: hours }) }));

/** Whether the station transmits at all: on, or receive only (station/transmit). */
const transmitChoices = (): readonly Choice[] => [
  { value: "true", label: t("settings.transmit.on") },
  { value: "false", label: t("settings.transmit.off") },
];

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const directionChoices = (): readonly Choice[] => [
  { value: "omni", label: t("settings.antenna_direction.omni") },
  ...COMPASS.map((point) => ({ value: point, label: point })),
];

const GAIN = LIMITS.range["beacon/antenna_gain_db"];

const SPECS: Record<string, FieldSpec> = {
  "station/call": { label: "settings.call.label" },
  "station/transmit": { label: "settings.transmit.label", kind: "choice", choices: transmitChoices },
  "station/lat": { label: "settings.lat.label", unit: "°" },
  "station/lon": { label: "settings.lon.label", unit: "°" },
  "station/symbol_table": { name: "settings.symbol.label", label: "settings.symbol.label" },
  "station/symbol_code": { name: "settings.symbol.label", label: "settings.symbol_code.label" },
  "station/comment": {
    label: "settings.comment.label",
    tip: [["settings.comment.tip1", { max: LIMITS.comment.max, with_phg: LIMITS.comment.maxWithPhg }], "settings.comment.tip2"],
  },
  "station/status": {
    name: "settings.station_status.name",
    label: "settings.station_status.label",
    empty: "settings.none",
    tip: [["settings.station_status.tip1", { max: LIMITS.status.max }], "settings.station_status.tip2"],
  },
  "beacon/power_w": {
    label: "settings.power.label",
    unit: "W",
    empty: "settings.none",
    tip: ["settings.power.tip1", "settings.power.tip2"],
  },
  "beacon/antenna_height_m": {
    label: "settings.antenna_height.label",
    unit: "m",
    tip: ["settings.antenna_height.tip1", "settings.antenna_height.tip2"],
  },
  "beacon/antenna_gain_db": {
    label: "settings.antenna_gain.label",
    unit: "dB",
    tip: [["settings.antenna_gain.tip1", { min: GAIN.min, max: GAIN.max }], "settings.antenna_gain.tip2"],
  },
  "beacon/antenna_direction": {
    label: "settings.antenna_direction.label",
    kind: "choice",
    choices: directionChoices,
    tip: ["settings.antenna_direction.tip1"],
  },
  "tnc/profile": {
    label: "settings.profile.label",
    kind: "choice",
    choices: () => TNC_PROFILES.map((p) => ({ value: p.key, label: p.name })),
    tipLabel: "settings.profile.tip_label",
    tip: ["settings.profile.tip1", "settings.profile.tip2", "settings.profile.tip3", "settings.profile.tip4", "settings.profile.tip5"],
  },
  "serial/port": {
    name: "settings.port.name",
    label: "settings.port.label",
    empty: plain("/dev/ttyUSB0"),
    tipLabel: "settings.port.tip_label",
    tip: ["settings.port.tip1", "settings.port.tip2", "settings.port.tip3"],
  },
  "serial/baud": {
    name: "settings.baud.name",
    label: "settings.baud.label",
    unit: "baud",
    tipLabel: "settings.baud.tip_label",
    tip: ["settings.baud.tip1", "settings.baud.tip2"],
  },
  "tcp/host": { label: "settings.tcp_host.label" },
  "tcp/port": { label: "settings.tcp_port.label", title: "settings.tcp_port.title" },
  "serial/last_port": { label: "settings.last_port.label", kind: "readonly", empty: plain("-") },
  "web/network": {
    name: "settings.network.name",
    label: "settings.network.label",
    kind: "bool",
    tipLabel: "settings.network.tip_label",
    tip: ["settings.network.tip1", "settings.network.tip2", "settings.network.tip3"],
  },
  "web/key": {
    label: "settings.access_key.label",
    kind: "readonly",
    tipLabel: "settings.access_key.tip_label",
    tip: ["settings.access_key.tip1", "settings.access_key.tip2"],
  },
  "web/https": {
    name: "settings.https.name",
    label: "settings.https.label",
    kind: "bool",
    tipLabel: "settings.https.tip_label",
    tip: ["settings.https.tip1"],
  },
  "map/radius_km": {
    name: "settings.radius.name",
    label: "settings.radius.label",
    unit: "km",
    tipLabel: "settings.radius.tip_label",
    tip: ["settings.radius.tip1", "settings.radius.tip2"],
  },
  [STATION_HOURS_KEY]: { name: "settings.station_hours.name", label: "station.table.on_map", kind: "choice", choices: stationHoursChoices },
  "digi/enabled": {
    label: "settings.digipeater.label",
    kind: "bool",
    tipLabel: "settings.digipeater.tip_label",
    tip: ["settings.digipeater.tip1", "settings.digipeater.tip2"],
  },
  "messages/alert": { name: "settings.alert.label", label: "settings.alert.label", kind: "bool" },
  "messages/alert_command": { name: "settings.alert_command.name", label: "settings.alert_command.label" },
  "status/source": {
    label: "settings.status_source.label",
    kind: "choice",
    choices: () => STATUS_CHOICES,
    tip: ["settings.status_source.tip1"],
  },
  "status/rigctld": {
    label: "settings.status_rigctld.label",
    empty: plain("127.0.0.1:4532"),
    tip: ["settings.status_rigctld.tip1", "settings.status_rigctld.tip2"],
  },
  "status/interval_min": {
    name: "settings.status_interval.name",
    label: "settings.status_interval.label",
    kind: "choice",
    choices: statusIntervalChoices,
    other: every,
    tip: ["settings.status_interval.tip1"],
  },
  "status/template": {
    name: "settings.status_template.name",
    label: "settings.status_template.label",
    tip: [["settings.status_template.tip1", { max: LIMITS.status.max }], "settings.status_template.tip2"],
  },
  "beacon/interval_min": {
    name: "settings.beacon_interval.name",
    label: "settings.beacon_interval.label",
    kind: "choice",
    choices: beaconChoices,
    other: every,
    tip: [["settings.beacon_interval.tip1", { min: LIMITS.interval.beaconMinMin }]],
  },
  "beacon/path": {
    name: "settings.path.name",
    label: "settings.path.label",
    tip: ["settings.path.tip1", "settings.path.tip2"],
  },
};

/** What each setting says of itself (words in the language of the page, made when they are read); a key this page does not know has none. */
export const FIELDS: Record<string, FieldInfo> = Object.fromEntries(Object.entries(SPECS).map(([key, spec]) => [key, field(spec)]));

/** The settings of the daemon's own alert, which the Notifications group shows (beside the alert of the browser, which is the page's). */
const ALERT = ["messages/alert", "messages/alert_command"];

/** The heading that goes above a key inside its group: the daemon's own alert, which runs on the computer NeoAPRS runs on, whichever device shows the page. */
export const SUBGROUPS: Record<string, { readonly text: string; readonly title: string; readonly tipLabel: string; readonly tip: readonly string[] }> = {
  "messages/alert": {
    get text() {
      return t("settings.alerts.text");
    },
    get title() {
      return t("settings.alerts.title");
    },
    get tipLabel() {
      return t("settings.alerts.tip_label");
    },
    get tip() {
      return [t("settings.alerts.tip1"), t("settings.alerts.tip2"), t("settings.alerts.tip3")];
    },
  },
};

/** The antenna's keys belong to the station, though they are the beacon's to send. */
const ANTENNA = ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"];

/** What the Beacon group keeps behind a closed heading: the antenna (the PHG part of the beacon) and the path. */
export const BEACON_FOLDS: readonly { readonly title: string; readonly keys: readonly string[] }[] = [
  lazyText({ keys: ANTENNA }, { title: () => t("settings.fold.antenna") }),
  lazyText({ keys: ["beacon/path"] }, { title: () => t("settings.fold.advanced") }),
];

interface Group {
  id: string;
  title: string;
  keys: string[];
}

const GROUPS: { id: string; title: MessageId; prefixes: string[]; also?: string[]; except?: string[] }[] = [
  { id: "station", title: "settings.group.station", prefixes: ["station/"], except: ["station/status", "station/comment"] },
  { id: "serial", title: "settings.group.tnc", prefixes: ["tnc/", "serial/", "tcp/"] },
  { id: "web", title: "settings.group.web", prefixes: ["web/"] },
  { id: "notifications", title: "settings.group.notifications", prefixes: [], also: ALERT },
  { id: "map", title: "settings.group.map", prefixes: ["map/"] },
  { id: "digi", title: "settings.group.digi", prefixes: ["digi/"] },
  { id: "beacon", title: "settings.group.beacon", prefixes: ["beacon/"], also: ["station/comment"] },
  { id: "status", title: "settings.group.status", prefixes: ["status/"], also: ["station/status"] },
];

/** Which settings a form shows: the Beacon tab has what the beacon says and sends, the Settings tab the rest (and any key this file does not know), so that no key is in two places. */
export type Scope = "settings" | "beacon";
const SCOPE_GROUPS: Record<Scope, readonly string[]> = {
  beacon: ["station", "beacon", "status"],
  settings: ["serial", "digi", "web", "notifications", "map"],
};

/** The order of the TNC group on the page: the type of TNC, the port and its speed, or the host and port of a TCP one. */
const TNC_ORDER = ["tnc/profile", "serial/port", "serial/baud", "tcp/host", "tcp/port", "serial/last_port"];

/** The Status group: the choice first, then what that choice needs. */
const STATUS_ORDER = ["status/source", "station/status", "status/rigctld", "status/template", "status/interval_min"];
/** The Beacon group: how often, what it says, then the folds (the antenna, the path). */
const BEACON_ORDER = ["beacon/interval_min", "station/comment", ...ANTENNA, "beacon/path"];
const GROUP_ORDER: Record<string, readonly string[]> = { station: ["station/transmit"], serial: TNC_ORDER, status: STATUS_ORDER, beacon: BEACON_ORDER };

function rank(order: readonly string[], key: string): number {
  const at = order.indexOf(key);
  return at < 0 ? order.length : at;
}

/** Settings that stay in the daemon (`neoaprs db set`) and are not on the page: the address the update check asks, which ports the search for the radio looks at and leaves alone, and the port and the host names of the page itself
 * (the defaults suit nearly everyone, and the daemon moves to a free port and says which in the log), and the map's detail (12, streets), source (the latest daily build). The map download uses the stored values, so a custom source or detail still works. */
const NOT_ON_THE_PAGE: readonly string[] = ["update/url", "serial/pattern", "serial/skip", "web/port", "web/allowed_hosts", "map/maxzoom", "map/source"];

/** Settings that are on the page, but in another tab than the Settings tab: the time stations stay on the map (map/station_hours) is chosen in the Stations tab. */
const IN_ANOTHER_TAB: readonly string[] = [STATION_HOURS_KEY];

/** The keys in the order of the daemon's list (a key it did not list last; the TNC and Status groups in their own order), in the groups of the form `scope` shows. */
export function groupKeys(keys: readonly string[], scope: Scope = "settings"): Group[] {
  const order = (key: string): number => {
    const at = (CONFIG_KEYS as readonly string[]).indexOf(key);
    return at < 0 ? CONFIG_KEYS.length : at;
  };
  const sorted = keys.filter((k) => !NOT_ON_THE_PAGE.includes(k) && !IN_ANOTHER_TAB.includes(k)).sort((a, b) => order(a) - order(b));
  const groups: Group[] = GROUPS.map((g) => ({
    id: g.id,
    title: t(g.title),
    keys: sorted.filter((k) => (g.also?.includes(k) ?? false) || (g.prefixes.some((p) => k.startsWith(p)) && !g.except?.includes(k))),
  }));
  for (const group of groups) {
    const order = GROUP_ORDER[group.id];
    if (order) group.keys.sort((a, b) => rank(order, a) - rank(order, b));
  }
  const known = new Set(groups.flatMap((g) => g.keys));
  groups.push({ id: "other", title: t("settings.group.other"), keys: sorted.filter((k) => !known.has(k)) });
  const shown = scope === "beacon" ? SCOPE_GROUPS.beacon : [...SCOPE_GROUPS.settings, "other"];
  return shown.flatMap((id) => groups.filter((g) => g.id === id && g.keys.length > 0));
}

/** What is wrong, without the command and the setting in front: the page's sentence for the refusal's code, else the daemon's English one, whose sentence is "<cmd>: [<key>: ]<reason>" (neoaprs/web/handlers.py; tests/test_error_codes.py holds it to that). */
export const reasonOf: (error: Failure) => string = errorReason;

const SERIAL_ONLY = ["serial/port", "serial/baud"];

/** The profile a form shows (its draft or the daemon's value), or undefined for a key this page does not know. */
function profileOf(key: string | undefined) {
  return TNC_PROFILES.find((p) => p.key === key);
}

/** Whether a setting is shown for the chosen TNC profile: the host and port for one that is reached over TCP, the port and speed for a serial one; the access key while the daemon lets the network in (`network`) and has made one.
 * The port the search found last is no field: the port's own control says it. */
export function shownFor(key: string, profileKey: string | undefined, network = true): boolean {
  if (key === "web/key" || key === "web/https") return network;
  if (key === "serial/last_port") return false;
  const profile = profileOf(profileKey);
  if (!profile) return true;
  if (key.startsWith("tcp/")) return profile.transport === "tcp";
  if (SERIAL_ONLY.includes(key)) return profile.transport === "serial";
  return true;
}

/** What an empty speed means for the chosen profile, as the placeholder: its own speed, else the default of the daemon. */
export function speedFallback(profileKey: string | undefined, fallback: string): string {
  const baud = profileOf(profileKey)?.baud;
  return baud ? String(baud) : fallback;
}

/** The port to keep when the profile is changed: a serial device does not go with a TCP profile (the daemon refuses it), so it is cleared; an address stays. */
export function portForProfile(profileKey: string, port: string): string {
  return profileOf(profileKey)?.transport === "tcp" && port !== "" && !/^(socket|tcp):\/\//i.test(port.trim()) ? "" : port;
}

/** Whether a field of the Beacon tab is shown for the values the form holds: the Status group shows what its source needs, and the antenna's height, gain and direction come once there is a power (they only make the PHG code with it). */
export function shownByValues(key: string, values: Readonly<Record<string, string>>): boolean {
  if (key.startsWith("status/") || key === "station/status") return statusShown(key, statusSource(values));
  if (ANTENNA.includes(key) && key !== "beacon/power_w") return (values["beacon/power_w"] ?? "").trim() !== "";
  return true;
}
