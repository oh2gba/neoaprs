// The settings form's logic: which key goes in which group, what each field says of itself, and
// which field a daemon error is about. Keys and their order come from the daemon (CONFIG_KEYS); an
// unknown key shows under its own name. Field words come from the catalogue (i18n/en/settings.ts)
// when read, so they follow the language.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { errorReason, type Failure, type RadioNames } from "@/i18n/errortext";
import type { Params } from "@/i18n/message";
import { STATION_HOURS_KEY } from "@/lib/aging";
import { ANTENNA, beaconOff } from "@/lib/beaconoff";
import type { PictureName } from "@/help/names";
import { isMoving } from "@/lib/gpsstatus";
import { LAYER_BOXES, LAYER_SPECS, layerShown } from "@/lib/layersettings";
import { lazyText } from "@/lib/lazytext";
import { alertLegend } from "@/lib/alertlegend";
import { GROUP_ORDER, rank } from "@/lib/settingsorder";
import type { PageRadio } from "@/lib/radios";
import { flatKeyOf, isRadioKey, radioFieldOf, typeChoices, typeText } from "@/lib/settingsradio";
import { pairField } from "@/lib/settingspair";
import { UNITS_KEY } from "@/lib/units";
import { keyingChoices } from "@/lib/mercury";
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
import { CONFIG_KEYS, HF_PROFILES, LIMITS, TNC_PROFILES } from "@/protocol/lists";

type FieldKind = "text" | "bool" | "readonly" | "choice" | "password" | "call";

export interface FieldInfo {
  label: string;
  /**
   * What the toast calls the setting after a change ("Beacon interval changed"), when the label
   * alone does not say it.
   */
  name?: string;
  /** Shown after the input: "min", "W", "km/h". */
  unit?: string;
  /**
   * Placeholder for a field whose empty value means something ("none", "auto"); else the default.
   */
  empty?: string;
  /** Hover text: the one thing a word cannot say. */
  title?: string;
  /**
   * Text of the (i) beside the field, one paragraph per entry. Only for fields a non-developer may
   * not understand.
   */
  tip?: readonly string[];
  /** The (i)'s label for screen readers and hover; else "About" and the label. */
  tipLabel?: string;
  /** The picture shown under the (i) note (help/). */
  picture?: PictureName;
  kind?: FieldKind;
  /**
   * The values a `choice` offers: the setting's text, or the text with the words it is shown as.
   */
  choices?: readonly (string | Choice)[];
  /**
   * Words for a value that is none of the choices (stored from the shell): "Every 20 min"; else the
   * value itself.
   */
  other?: (value: string) => string;
  /** The most characters a typed field takes; the input stops there. */
  maxLength?: number;
}

/**
 * A page text: a message id, an id with values, or a function making the words (for a port, an
 * address).
 */
type Say = MessageId | readonly [MessageId, Params] | (() => string);
const said = (say: Say): string =>
  typeof say === "function" ? say() : typeof say === "string" ? t(say) : t(say[0], say[1]);
/** Words that are the same in every language. */
const plain =
  (text: string): Say =>
  () =>
    text;

/** A field as ids; the words are looked up when read. */
export interface FieldSpec {
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

/**
 * The Radio type field of every box, of either kind: one (i) for the one list of types (plan
 * section 6).
 */
const RADIO_TYPE: FieldSpec = {
  label: "settings.profile.label",
  kind: "choice",
  tipLabel: "settings.profile.tip_label",
  tip: ["settings.profile.tip1", "settings.profile.tip2"],
  picture: "dummy",
};

const SPECS: Record<string, FieldSpec> = {
  "station/call": {
    label: "settings.call.label",
    kind: "call",
    tip: ["settings.call.tip1", "settings.call.tip2"],
    picture: "ssid",
  },
  "station/lat": { label: "settings.lat.label", unit: "°" },
  "station/lon": { label: "settings.lon.label", unit: "°" },
  "station/symbol_table": { name: "settings.symbol.label", label: "settings.symbol.label" },
  "station/symbol_code": { name: "settings.symbol.label", label: "settings.symbol_code.label" },
  "station/comment": {
    label: "settings.comment.label",
    tip: [["settings.comment.tip1", { max: LIMITS.comment.max }], "settings.comment.tip2"],
  },
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
  "fm/enabled": {
    name: "settings.fm_enabled.name",
    label: "settings.enable.label",
    kind: "bool",
    tipLabel: "settings.fm_enabled.tip_label",
    tip: ["settings.fm_enabled.tip1", "settings.fm_enabled.tip2"],
    picture: "tworadios",
  },
  "hf/enabled": {
    name: "settings.hf_enabled.name",
    label: "settings.enable.label",
    kind: "bool",
    tipLabel: "settings.hf_enabled.tip_label",
    tip: ["settings.hf_enabled.tip1", "settings.hf_enabled.tip2"],
    picture: "tworadios",
  },
  "lora/enabled": {
    name: "settings.group.lora_radio",
    label: "settings.enable.label",
    kind: "bool",
    tipLabel: "settings.lora_enabled.tip_label",
    tip: ["settings.lora_enabled.tip1", "settings.fm_enabled.tip2"],
  },
  "tnc/profile": {
    ...RADIO_TYPE,
    choices: () => typeChoices("fm").filter((choice) => TNC_PROFILES.some((p) => p.key === choice.value)),
  },
  "hf/profile": { ...RADIO_TYPE, choices: () => HF_PROFILES.map((p) => ({ value: p.key, label: typeText(p.key) })) },
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
  "tcp/port": { label: "settings.tcp_port.label", tip: ["settings.tcp_port.tip1"] },
  "tnc/on_hf": {
    label: "settings.on_hf.label",
    kind: "bool",
    tipLabel: "settings.on_hf.tip_label",
    tip: ["settings.on_hf.tip1"],
  },
  "lora/host": { label: "settings.board_host.label", empty: plain(""), tip: ["settings.board_host.tip1"] },
  "lora/port": { label: "settings.board_port.label", tip: ["settings.board_port.tip1"] },
  "mercury/sound_card": {
    label: "settings.sound_card.label",
    tipLabel: "settings.sound_card.tip_label",
    tip: ["settings.sound_card.tip1", "settings.sound_card.tip2"],
    picture: "mercury",
  },
  "mercury/keying": {
    label: "settings.keying.label",
    kind: "choice",
    choices: () => keyingChoices(null),
    tipLabel: "settings.keying.tip_label",
    tip: ["settings.keying.tip1", "settings.keying.tip2"],
    picture: "mercury",
  },
  "mercury/tx_gain_db": {
    label: "settings.txlevel.label",
    tipLabel: "settings.txlevel.tip_label",
    tip: ["settings.txlevel.tip1", "settings.txlevel.tip2"],
  },
  "serial/last_port": { label: "settings.last_port.label", kind: "readonly", empty: plain("-") },
  "web/network": {
    name: "settings.network.name",
    label: "settings.network.label",
    kind: "bool",
    tipLabel: "settings.network.tip_label",
    tip: ["settings.network.tip1", "phone.network.tip2"],
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
  [STATION_HOURS_KEY]: {
    name: "settings.station_hours.name",
    label: "station.table.on_map",
    kind: "choice",
    choices: stationHoursChoices,
  },
  [UNITS_KEY]: {
    name: "settings.units.name",
    label: "settings.units.label",
    kind: "bool",
    tip: ["settings.units.tip1", "settings.units.tip2"],
  },
  ...LAYER_SPECS,
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
    label: "settings.igate.show_label",
    kind: "bool",
    tipLabel: "settings.igate.tip_label",
    tip: ["settings.igate.tip1"],
    picture: "internet",
  },
  "igate/gate": {
    name: "settings.igate.gate_label",
    label: "settings.igate.gate_label",
    kind: "bool",
    tipLabel: "settings.igate.gate_tip_label",
    tip: ["settings.igate.gate_tip1", "settings.igate.gate_tip2"],
  },
  "igate/show_gated": {
    name: "settings.igate.show_gated_label",
    label: "settings.igate.show_gated_label",
    kind: "bool",
    tipLabel: "settings.igate.show_gated_tip_label",
    tip: ["settings.igate.show_gated_tip1"],
    picture: "gated",
  },
  "messages/chat_alert": {
    name: "settings.chat_alert.name",
    label: "settings.chat_alert.name",
    kind: "bool",
    tip: ["settings.chat_alert.tip1"],
  },
  "messages/alert": {
    name: "settings.browser.mode",
    label: "settings.browser.mode",
    kind: "bool",
    tip: ["settings.alert.tip1"],
  },
  "messages/alert_command": {
    name: "settings.alert_command.name",
    label: "settings.alert_command.label",
    tip: ["settings.alert_command.tip1"],
  },
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
  "beacon/path": {
    name: "settings.path.name",
    label: "settings.path.label",
    tip: ["settings.path.tip1", "settings.path.tip2"],
    picture: "path",
  },
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
  "beacon/travel": {
    label: "settings.travel.label",
    kind: "choice",
    choices: travelChoices,
    tip: ["settings.travel.tip1"],
  },
};

/**
 * The beacon of a moving station, in place of the interval: a tickbox (ticked is On,
 * SmartBeaconing, which stores interval 30 that a moving station does not use; unticked is Off).
 */
const MOVING_BEACON = field({
  name: "settings.beacon_interval.name",
  label: "settings.beacon_interval.label",
  kind: "bool",
  tip: ["settings.beacon_interval.tip_moving"],
});

/** What each setting says of itself, in the page's language when read; none for an unknown key. */
export const FIELDS: Record<string, FieldInfo> = Object.fromEntries(
  Object.entries(SPECS).map(([key, spec]) => [key, field(spec)]),
);

/**
 * The daemon's own alert settings, which the Notifications group shows beside the browser's alert: the
 * chat's tickbox first, for both, then the box of the alert command.
 */
const ALERT = ["messages/chat_alert", "messages/alert", "messages/alert_command"];
/**
 * Whether either tick of the Internet (APRS-IS) group, Show Internet stations or Send what I hear,
 * is on in these values, so that APRS-IS is logged in to; off unless they say so.
 */
export const igateOn = (values: Readonly<Record<string, string>>): boolean =>
  values["igate/enabled"] === "true" || values["igate/gate"] === "true";

/**
 * Whether a setting that depends on a switch is shown: the alert's command and Test button only
 * while the alert is on (default on).
 */
const shownBySwitch = (key: string, values: Readonly<Record<string, string>>): boolean =>
  key !== "messages/alert_command" || values["messages/alert"] !== "false";

/** The legend of the box that starts at a key inside its group (components/SettingsBox.vue). */
export const SUBGROUPS: Record<
  string,
  {
    readonly text: string;
    readonly title: string;
    readonly tipLabel: string;
    readonly tip: readonly string[];
    readonly picture?: PictureName;
  }
> = {
  "messages/alert": alertLegend,
  ...LAYER_BOXES,
};

/**
 * What the My station tab keeps behind a closed heading in the Beacon group: the antenna (PHG) and
 * the path.
 */
export const BEACON_FOLDS: readonly {
  readonly group: string;
  readonly title: string;
  readonly keys: readonly string[];
}[] = [
  lazyText({ group: "beacon", keys: ANTENNA }, { title: () => t("settings.fold.antenna") }),
  lazyText({ group: "beacon", keys: ["beacon/path"] }, { title: () => t("settings.fold.advanced") }),
];

interface Group {
  id: string;
  title: string;
  keys: string[];
}

const GROUPS: { id: string; title: MessageId; prefixes: string[]; also?: string[]; except?: string[] }[] = [
  {
    id: "station",
    title: "settings.group.station",
    prefixes: ["station/", "gps/"],
    except: ["station/status", "station/comment"],
  },
  { id: "serial", title: "settings.group.tnc", prefixes: ["serial/"] },
  { id: "igate", title: "settings.group.igate", prefixes: ["igate/"] },
  { id: "web", title: "settings.group.web", prefixes: ["web/"] },
  { id: "notifications", title: "settings.group.notifications", prefixes: [], also: ALERT },
  { id: "map", title: "settings.group.map", prefixes: ["map/"] },
  { id: "digi", title: "settings.group.digi", prefixes: ["digi/"] },
  { id: "beacon", title: "settings.group.beacon", prefixes: ["beacon/"], also: ["station/comment"] },
  { id: "status", title: "settings.group.status", prefixes: ["status/"], also: ["station/status"] },
];

/**
 * Which settings a form shows: My station has the beacon settings, Settings the rest, so no key is
 * in two places.
 */
export type Scope = "settings" | "beacon";
const SCOPE_GROUPS: Record<Scope, readonly string[]> = {
  beacon: ["station", "beacon", "status"],
  settings: ["serial", "igate", "digi", "web", "notifications", "map"],
};

/**
 * Settings that stay in the daemon (`neoaprs db set`) and are not on the page: the update-check
 * address, the APRS-IS server and passcode, the serial ports the radio search looks at, the page's
 * own port and host names, and the map's detail and source. The map download uses the stored
 * values.
 */
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

/** RX only is `station/transmit` false: the switch at the top right (lib/rxswitch.ts). */
export const RX_ONLY_KEY = "station/transmit";

/**
 * Settings on the page but in another tab: how long stations stay on the map (map/station_hours) is
 * in Stations.
 */
const IN_ANOTHER_TAB: readonly string[] = [STATION_HOURS_KEY];
/** Settings in a row of their own above the groups, beside the language. */
const ABOVE_THE_GROUPS: readonly string[] = [UNITS_KEY];
/** Settings in the header, on every tab: RX only. */
const IN_THE_HEADER: readonly string[] = [RX_ONLY_KEY];

/**
 * The keys in the daemon's order (unlisted keys last; the TNC and Status groups in their own
 * order), grouped as `scope` shows.
 */
export function groupKeys(keys: readonly string[], scope: Scope = "settings"): Group[] {
  const order = (key: string): number => {
    const at = (CONFIG_KEYS as readonly string[]).indexOf(key);
    return at < 0 ? CONFIG_KEYS.length : at;
  };
  const sorted = keys
    .filter(
      (k) =>
        !NOT_ON_THE_PAGE.includes(k) &&
        !IN_ANOTHER_TAB.includes(k) &&
        !ABOVE_THE_GROUPS.includes(k) &&
        !IN_THE_HEADER.includes(k) &&
        !isRadioKey(k),
    )
    .sort((a, b) => order(a) - order(b));
  const groups: Group[] = GROUPS.map((g) => ({
    id: g.id,
    title: t(g.title),
    keys: sorted.filter(
      (k) => (g.also?.includes(k) ?? false) || (g.prefixes.some((p) => k.startsWith(p)) && !g.except?.includes(k)),
    ),
  }));
  for (const group of groups) {
    const order = GROUP_ORDER[group.id];
    if (order) group.keys.sort((a, b) => rank(order, a) - rank(order, b));
  }
  const known = new Set(groups.flatMap((g) => g.keys));
  groups.push({ id: "other", title: t("settings.group.other"), keys: sorted.filter((k) => !known.has(k)) });
  const shown = scope === "beacon" ? SCOPE_GROUPS.beacon : [...SCOPE_GROUPS.settings, "other"];
  // The Digipeater group's fields are its radios' (radio/<id>/digipeat); SettingsForm draws them.
  return shown.flatMap((id) => groups.filter((g) => g.id === id && (g.keys.length > 0 || g.id === "digi")));
}

/**
 * What is wrong, without the command and setting in front: the page's sentence for the refusal's
 * code, else the daemon's English sentence "<cmd>: [<key>: ]<reason>" (neoaprs/web/handlers.py).
 * `radios` names a radio in the refusal.
 */
export const reasonOf = (error: Failure, radios?: RadioNames): string => errorReason(error, radios);

/**
 * What the field of a key says of itself for these settings. A moving station's beacon choice is
 * Off or On (SmartBeaconing). A radio's setting (`radio/3/port`) uses the shared radio-field words,
 * or its kind's (`kind`). A pair's setting (`pair/1/2/ssid`) uses lib/settingspair.ts. An unknown
 * key is its own label.
 */
export function fieldFor(
  key: string,
  values: Readonly<Record<string, string>> = {},
  kind?: PageRadio["kind"],
): FieldInfo {
  const flat = flatKeyOf(radioFieldOf(key)?.field ?? "", kind);
  return key === "beacon/interval_min" && isMoving(values)
    ? MOVING_BEACON
    : (FIELDS[key] ?? pairField(key, values) ?? (flat === null ? undefined : FIELDS[flat]) ?? { label: key });
}

/**
 * The value a field shows: a moving station's beacon is "0" (Off) or the one On, whatever interval
 * is stored.
 */
export function valueFor(key: string, values: Readonly<Record<string, string>>): string {
  const text = values[key] ?? "";
  return key === "beacon/interval_min" && isMoving(values) ? String(!beaconOff(values)) : text;
}

/**
 * What is stored for what the field says: a moving station's beacon tickbox stores the interval On,
 * or 0; any other field is as it says.
 */
export function storedFor(key: string, values: Readonly<Record<string, string>>, said: string): string {
  return key === "beacon/interval_min" && isMoving(values) ? (said === "true" ? MOVING_BEACON_ON : "0") : said;
}

/**
 * Whether a field of the My station tab is shown for the values the form holds. The Status group
 * shows what its source needs. The position fields follow its choice (gpsd address; port and speed
 * for a serial GPS; the place only for a fixed station, kept stored with a GPS). A moving station
 * has Travelling and no antenna (the antenna only makes the PHG code). The Beacon choice is shown
 * to both.
 */
export function shownByValues(key: string, values: Readonly<Record<string, string>>): boolean {
  if (!shownBySwitch(key, values)) return false;
  if (key.startsWith("status/") || key === "station/status") return statusShown(key, statusSource(values));
  if (ANTENNA.includes(key))
    return !isMoving(values) && (key === "beacon/power_w" || (values["beacon/power_w"] ?? "").trim() !== "");
  if (key === "station/lat" || key === "station/lon") return !isMoving(values);
  if (key === "gps/host") return values["gps/source"] === "gpsd";
  if (key === "gps/device" || key === "gps/baud") return values["gps/source"] === "serial";
  if (key === "beacon/travel") return isMoving(values);
  if (!layerShown(key, values)) return false;
  return true;
}
