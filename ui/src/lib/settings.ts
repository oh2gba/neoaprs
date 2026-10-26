// The settings form's logic: which key goes in which group, what each field says of itself, and which field an error of the daemon is about.
// The keys and their order come from the daemon (CONFIG_KEYS of the generated lists); a key this file does not know is shown under its own name.
// What a field says of itself is words of the catalogue (i18n/en/settings.ts), made when they are read: `FIELDS[key].label` is in the language the page has at that moment, so a template that reads it follows a change of language.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { errorReason, type Failure } from "@/i18n/errortext";
import type { Params } from "@/i18n/message";
import { STATION_HOURS_KEY } from "@/lib/aging";
import { ANTENNA, beaconOff } from "@/lib/beaconoff";
import type { PictureName } from "@/help/names";
import { isMoving } from "@/lib/gpsstatus";
import { lazyText } from "@/lib/lazytext";
import {
  beaconChoices,
  directionChoices,
  every,
  MOVING_BEACON_ON,
  positionChoices,
  statusIntervalChoices,
  stationHoursChoices,
  travelChoices,
  type Choice,
} from "@/lib/settingchoices";
import { STATUS_CHOICES, statusShown, statusSource } from "@/lib/status";
import { profileOf } from "@/lib/tncprofile";
import { CONFIG_KEYS, LIMITS, TNC_PROFILES } from "@/protocol/lists";

type FieldKind = "text" | "bool" | "readonly" | "choice" | "password";

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
  /** The picture the note of the (i) shows under its text (help/), when a picture says it better. */
  picture?: PictureName;
  kind?: FieldKind;
  /** The values a `choice` offers: the text of the setting, or the text with the words it is shown as. */
  choices?: readonly (string | Choice)[];
  /** The words for a value that is none of the choices (a setting stored from the shell): "Every 20 min"; else the value itself. */
  other?: (value: string) => string;
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
  picture?: PictureName;
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
  if (spec.picture !== undefined) info.picture = spec.picture;
  if (spec.other !== undefined) info.other = spec.other;
  return info;
}

const GAIN = LIMITS.range["beacon/antenna_gain_db"];

const SPECS: Record<string, FieldSpec> = {
  "station/transmit": {
    name: "settings.transmit.name",
    label: "settings.transmit.label",
    kind: "bool",
    tipLabel: "settings.transmit.tip_label",
    tip: ["settings.transmit.tip1"],
    picture: "transmit",
  },
  "station/call": { label: "settings.call.label", tip: ["settings.call.tip1", "settings.call.tip2"], picture: "ssid" },
  "station/lat": { label: "settings.lat.label", unit: "°" },
  "station/lon": { label: "settings.lon.label", unit: "°" },
  "station/symbol_table": { name: "settings.symbol.label", label: "settings.symbol.label" },
  "station/symbol_code": { name: "settings.symbol.label", label: "settings.symbol_code.label" },
  "station/comment": { label: "settings.comment.label", tip: [["settings.comment.tip1", { max: LIMITS.comment.max }], "settings.comment.tip2"] },
  "station/status": {
    name: "settings.station_status.name",
    label: "settings.station_status.label",
    empty: plain("145.500MHz QRV"),
    tip: ["settings.station_status.tip1", ["settings.station_status.tip2", { max: LIMITS.status.max }]],
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
    tip: ["settings.profile.tip1", "settings.profile.tip2"],
    picture: "dummy",
  },
  "serial/port": {
    name: "settings.port.name",
    label: "settings.port.label",
    empty: plain("/dev/ttyUSB0"),
    tipLabel: "settings.port.tip_label",
    tip: ["settings.port.tip1", "settings.port.tip2"],
  },
  "serial/baud": {
    name: "settings.baud.name",
    label: "settings.baud.label",
    unit: "baud",
    tipLabel: "settings.baud.tip_label",
    tip: ["settings.baud.tip1", "settings.baud.tip2"],
  },
  "tcp/host": { label: "settings.tcp_host.label", tip: ["settings.tcp_host.tip1"] },
  "tcp/port": { label: "settings.tcp_port.label", title: "settings.tcp_port.title", tip: ["settings.tcp_port.tip1"] },
  "serial/last_port": { label: "settings.last_port.label", kind: "readonly", empty: plain("-") },
  "web/network": {
    name: "settings.network.name",
    label: "settings.network.label",
    kind: "bool",
    tipLabel: "settings.network.tip_label",
    tip: ["settings.network.tip1", "settings.network.tip2"],
    picture: "network",
  },
  "web/key": {
    label: "settings.access_key.label",
    kind: "readonly",
    tipLabel: "settings.access_key.tip_label",
    tip: ["settings.access_key.tip1", "settings.access_key.tip2"],
    picture: "accesskey",
  },
  "web/https": {
    name: "settings.https.name",
    label: "settings.https.label",
    kind: "bool",
    tipLabel: "settings.https.tip_label",
    tip: ["settings.https.tip1", "settings.https.tip2"],
  },
  "map/radius_km": {
    name: "settings.radius.name",
    label: "settings.radius.label",
    unit: "km",
    tipLabel: "settings.radius.tip_label",
    tip: ["settings.radius.tip1", "settings.radius.tip2"],
    picture: "radius",
  },
  [STATION_HOURS_KEY]: { name: "settings.station_hours.name", label: "station.table.on_map", kind: "choice", choices: stationHoursChoices },
  "digi/enabled": {
    name: "settings.digipeater.name",
    label: "settings.enable.label",
    kind: "bool",
    tipLabel: "settings.digipeater.tip_label",
    tip: ["settings.digipeater.tip1", "settings.digipeater.tip2"],
    picture: "digipeater",
  },
  "igate/enabled": {
    name: "settings.igate.name",
    label: "settings.enable.label",
    kind: "bool",
    tipLabel: "settings.igate.tip_label",
    tip: ["settings.igate.tip1"],
    picture: "internet",
  },
  "messages/alert": { name: "settings.alert.label", label: "settings.alert.label", kind: "bool", tip: ["settings.alert.tip1"] },
  "messages/alert_command": { name: "settings.alert_command.name", label: "settings.alert_command.label", tip: ["settings.alert_command.tip1"] },
  "status/source": {
    label: "settings.status_source.label",
    kind: "choice",
    choices: () => STATUS_CHOICES,
    tip: ["settings.status_source.tip1"],
    picture: "status",
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
    tip: [["settings.beacon_interval.tip1", { min: LIMITS.interval.beaconMinMin }], "settings.beacon_interval.tip2"],
    picture: "beaconoff",
  },
  "beacon/path": { name: "settings.path.name", label: "settings.path.label", tip: ["settings.path.tip1", "settings.path.tip2"], picture: "path" },
  "gps/source": {
    name: "settings.position.name",
    label: "settings.position.label",
    kind: "choice",
    choices: positionChoices,
    tip: ["settings.position.tip1", "settings.position.tip2"],
    picture: "position",
  },
  "gps/host": { label: "settings.gps_host.label", tip: ["settings.gps_host.tip1"] },
  "gps/device": {
    label: "settings.gps_device.label",
    empty: plain("/dev/ttyUSB1"),
    tip: ["settings.gps_device.tip1", "settings.gps_device.tip2"],
  },
  "gps/baud": { label: "settings.gps_baud.label", unit: "baud", tip: ["settings.gps_baud.tip1"] },
  "beacon/travel": { label: "settings.travel.label", kind: "choice", choices: travelChoices, tip: ["settings.travel.tip1"] },
};

/** The beacon of a station that moves, in place of the interval of a fixed one: a tickbox (ticked is On, SmartBeaconing, which stores the interval 30 that a moving station does not use; unticked is Off). */
const MOVING_BEACON = field({
  name: "settings.beacon_interval.name",
  label: "settings.beacon_interval.label",
  kind: "bool",
  tip: ["settings.beacon_interval.tip_moving"],
});

/** What each setting says of itself (words in the language of the page, made when they are read); a key this page does not know has none. */
export const FIELDS: Record<string, FieldInfo> = Object.fromEntries(Object.entries(SPECS).map(([key, spec]) => [key, field(spec)]));

/** The settings of the daemon's own alert, which the Notifications group shows (beside the alert of the browser, which is the page's). */
const ALERT = ["messages/alert", "messages/alert_command"];

/** Whether the Internet switch (Enable, in the group Internet stations: the stations of APRS-IS on the map) is on in these values; it is off unless the values say so. */
export const igateOn = (values: Readonly<Record<string, string>>): boolean => values["igate/enabled"] === "true";

/** Whether a setting that depends on a switch is shown: the alert's command (and its Test button) only while the alert is on; an alert the values do not mention is the daemon's default, on. */
function shownBySwitch(key: string, values: Readonly<Record<string, string>>): boolean {
  return key !== "messages/alert_command" || values["messages/alert"] !== "false";
}

/** The legend of the box that starts at a key inside its group (components/SettingsBox.vue): the daemon's own alert, which runs on the computer NeoAPRS runs on, whichever device shows the page. */
export const SUBGROUPS: Record<
  string,
  { readonly text: string; readonly title: string; readonly tipLabel: string; readonly tip: readonly string[]; readonly picture?: PictureName }
> = {
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
      return [t("settings.alerts.tip1"), t("settings.alerts.tip2")];
    },
    picture: "notifications",
  },
};

/** What the Beacon tab keeps behind a closed heading in the Beacon group: the antenna (the PHG part of the beacon, which only a fixed station has) and the path. */
export const BEACON_FOLDS: readonly { readonly group: string; readonly title: string; readonly keys: readonly string[] }[] = [
  lazyText({ group: "beacon", keys: ANTENNA }, { title: () => t("settings.fold.antenna") }),
  lazyText({ group: "beacon", keys: ["beacon/path"] }, { title: () => t("settings.fold.advanced") }),
];

interface Group {
  id: string;
  title: string;
  keys: string[];
}

const GROUPS: { id: string; title: MessageId; prefixes: string[]; also?: string[]; except?: string[] }[] = [
  { id: "station", title: "settings.group.station", prefixes: ["station/", "gps/"], except: ["station/status", "station/comment", "station/transmit"] },
  { id: "serial", title: "settings.group.tnc", prefixes: ["tnc/", "serial/", "tcp/"], also: ["station/transmit"] },
  { id: "igate", title: "settings.group.igate", prefixes: ["igate/"] },
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
  settings: ["serial", "igate", "digi", "web", "notifications", "map"],
};

/** The order of the TNC group on the page: the RX only tickbox, the type of TNC, the port and its speed, or the host and port of a TCP one. */
const TNC_ORDER = ["station/transmit", "tnc/profile", "serial/port", "serial/baud", "tcp/host", "tcp/port", "serial/last_port"];

/** The Status group: the choice first, then Every (as the Beacon group has the interval with its choice), then what the chosen source needs. */
const STATUS_ORDER = ["status/source", "status/interval_min", "station/status", "status/rigctld", "status/template"];
/** The Beacon group: the Beacon choice (the interval of a fixed station, Off or On for a moving one), what it travels as (a moving station), what it says, then the folds (the antenna, the path). */
const BEACON_ORDER = ["beacon/interval_min", "beacon/travel", "station/comment", ...ANTENNA, "beacon/path"];
/** The Station group: the call, where the position comes from and what that needs (the gpsd address, or the port and speed of a serial GPS), then the place itself (only for a fixed station: with a GPS chosen the stored place is kept and not shown) and the symbol. */
const STATION_ORDER = [
  "station/call",
  "gps/source",
  "gps/host",
  "gps/device",
  "gps/baud",
  "station/lat",
  "station/lon",
  "station/symbol_table",
  "station/symbol_code",
];
const GROUP_ORDER: Record<string, readonly string[]> = {
  station: STATION_ORDER,
  serial: TNC_ORDER,
  status: STATUS_ORDER,
  beacon: BEACON_ORDER,
};

function rank(order: readonly string[], key: string): number {
  const at = order.indexOf(key);
  return at < 0 ? order.length : at;
}

/** Settings that stay in the daemon (`neoaprs db set`) and are not on the page: the address the update check asks, the APRS-IS server and the passcode of the Internet switch (igate/server, whose default is the round-robin name of the volunteer servers, and igate/password, which only a person who gates for the radio sets), which ports the search for the radio looks at and leaves alone, and the port and the host names of the page itself
 * (the defaults suit nearly everyone, and the daemon moves to a free port and says which in the log), and the map's detail (12, streets), source (the latest daily build). The map download uses the stored values, so a custom source or detail still works. */
const NOT_ON_THE_PAGE: readonly string[] = [
  "update/url",
  "serial/pattern",
  "serial/skip",
  "web/port",
  "web/allowed_hosts",
  "igate/server",
  "igate/password",
  "map/maxzoom",
  "map/source",
];

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

/** What the field of a key says of itself for these settings: the beacon choice of a station that moves is Off or On (SmartBeaconing), else the field's own. */
export function fieldFor(key: string, values: Readonly<Record<string, string>>): FieldInfo {
  return key === "beacon/interval_min" && isMoving(values) ? MOVING_BEACON : (FIELDS[key] ?? { label: key });
}

/** The tickbox RX only is the setting `station/transmit` the other way round: ticked is `false` (nothing is transmitted), unticked `true`. */
export const RX_ONLY_KEY = "station/transmit";

/** The value a field shows: the beacon of a station that moves is "0" (Off) or the one On, whatever interval is stored. */
export function valueFor(key: string, values: Readonly<Record<string, string>>): string {
  const text = values[key] ?? "";
  if (key === RX_ONLY_KEY) return String(text === "false");
  return key === "beacon/interval_min" && isMoving(values) ? String(!beaconOff(values)) : text;
}

/** What is stored for what the field says: the tickbox of a moving station's beacon says true or false, which is the interval On stores, or 0; the tickbox RX only says it the other way round; any other field is as it says. */
export function storedFor(key: string, values: Readonly<Record<string, string>>, said: string): string {
  if (key === RX_ONLY_KEY) return said === "true" ? "false" : "true";
  return key === "beacon/interval_min" && isMoving(values) ? (said === "true" ? MOVING_BEACON_ON : "0") : said;
}

/** Whether a field of the Beacon tab is shown for the values the form holds: the Status group shows what its source needs; the position's own fields follow its choice (the address of gpsd for gpsd, the port and speed for a serial GPS; the station's place only for a fixed station, with a GPS the place stays stored and the daemon uses it until the first fix); a station that moves
 * (a GPS is chosen) has the Travelling choice, and no antenna, which is a fixed station's (the antenna's height, gain and direction come once there is a power: they only make the PHG code with it); the Beacon choice is shown to both, with other choices (an interval, or Off and On). */
export function shownByValues(key: string, values: Readonly<Record<string, string>>): boolean {
  if (!shownBySwitch(key, values)) return false;
  if (key.startsWith("status/") || key === "station/status") return statusShown(key, statusSource(values));
  if (ANTENNA.includes(key)) return !isMoving(values) && (key === "beacon/power_w" || (values["beacon/power_w"] ?? "").trim() !== "");
  if (key === "station/lat" || key === "station/lon") return !isMoving(values);
  if (key === "gps/host") return values["gps/source"] === "gpsd";
  if (key === "gps/device" || key === "gps/baud") return values["gps/source"] === "serial";
  if (key === "beacon/travel") return isMoving(values);
  return true;
}
