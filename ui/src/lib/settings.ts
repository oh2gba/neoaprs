// The settings form's logic: which key goes in which group, what each field says of itself, which keys the user changed, and which field an error of the daemon is about.
// The keys and their order come from the daemon (CONFIG_KEYS of the generated lists); a key this file does not know is shown under its own name.
import { DETAIL_CHOICES } from "@/lib/mapfetch";
import { CONFIG_KEYS, TNC_PROFILES } from "@/protocol/lists";

type FieldKind = "text" | "bool" | "readonly" | "choice";

export interface FieldInfo {
  label: string;
  /** After the input: "min", "W", "km/h". */
  unit?: string;
  /** The word that stands in the unit's place while the value is 0: "never", "off". */
  zero?: string;
  /** The placeholder of a field whose empty value means something ("none", "auto", "direct"); else the placeholder is the default. */
  empty?: string;
  /** On hover: the one thing a word cannot say. */
  title?: string;
  kind?: FieldKind;
  /** The values a `choice` offers: the text of the setting, or the text with the words it is shown as. */
  choices?: readonly (string | Choice)[];
}

export interface Choice {
  value: string;
  label: string;
}

const AT_START = "Read at the daemon's start";

export const FIELDS: Record<string, FieldInfo> = {
  "station/call": { label: "Call" },
  "station/lat": { label: "Latitude", unit: "°" },
  "station/lon": { label: "Longitude", unit: "°" },
  "station/symbol_table": { label: "Symbol table", title: "/ primary, \\ alternate, 0-9 and A-Z overlay" },
  "station/symbol_code": { label: "Symbol code" },
  "station/comment": { label: "Comment", title: "43 characters; 36 with PHG, 40 compressed" },
  "station/status": { label: "Static text", empty: "none", title: "55 characters, ASCII" },
  "beacon/power_w": { label: "Power", unit: "W", empty: "none", title: "PHG; not sent when compressed" },
  "beacon/antenna_height_m": { label: "Antenna height", unit: "m" },
  "beacon/antenna_gain_db": { label: "Antenna gain", unit: "dB" },
  "beacon/antenna_direction": { label: "Antenna direction", kind: "choice", choices: ["omni", "N", "NE", "E", "SE", "S", "SW", "W", "NW"] },
  "tnc/profile": { label: "TNC", kind: "choice", choices: TNC_PROFILES.map((p) => ({ value: p.key, label: p.name })) },
  "serial/port": { label: "Port", empty: "/dev/ttyUSB0", title: "Automatic listens to the ports under Search" },
  "serial/baud": { label: "Speed", unit: "baud" },
  "tcp/host": { label: "Host" },
  "tcp/port": { label: "Port", title: "Direwolf 8001, soundmodem 8100" },
  "serial/last_port": { label: "Last port found", kind: "readonly", empty: "-" },
  "serial/pattern": { label: "Ports to search", title: "Device globs, separated by spaces" },
  "serial/skip": { label: "Ports to skip", empty: "none", title: "Device paths, separated by commas" },
  "tnc/check_sec": { label: "Keep-alive", unit: "s", zero: "off", title: "Silence before the radio is asked if it is there" },
  "web/network": { label: "Allow access from the network", kind: "bool" },
  "web/key": { label: "Access key", kind: "readonly" },
  "web/port": { label: "Port", zero: "any", title: AT_START },
  "web/allowed_hosts": { label: "Allowed hosts", empty: "none", title: AT_START },
  "log/keep_days": { label: "Keep", unit: "days" },
  "map/hide_after_min": { label: "Off map after", unit: "min", zero: "never" },
  "map/radius_km": { label: "Radius", unit: "km" },
  "map/maxzoom": { label: "Detail", kind: "choice", choices: DETAIL_CHOICES },
  "map/source": { label: "Source", empty: "latest build" },
  "update/check": { label: "Check once a day", kind: "bool", title: "Sends this version and the platform" },
  "messages/attempts": { label: "Attempts" },
  "messages/alert": { label: "Alert", kind: "bool" },
  "messages/alert_command": { label: "Command" },
  "status/rigctld": { label: "Rigctld", empty: "off", title: "host:port" },
  "status/interval_min": { label: "Interval", unit: "min", title: "10 at least" },
  "status/template": { label: "Template", title: "{freq} {mode}" },
  "beacon/interval_min": { label: "Interval", unit: "min", zero: "off", title: "10 at least" },
  "beacon/path": { label: "Path", empty: "direct" },
  "beacon/destination": { label: "Destination" },
  "beacon/compressed": { label: "Compressed", kind: "bool" },
  "beacon/dao": { label: "DAO", kind: "bool", title: "One more digit of the position, !Wxy!" },
};

/** The settings of the daemon's own alert, which the Notifications group shows (beside the alert of the browser, which is the page's). */
const ALERT = ["messages/alert", "messages/alert_command"];

/** The heading that goes above a key inside its group: the daemon's own alert, which runs on the computer NeoAPRS runs on, whichever device shows the page. */
export const SUBGROUPS: Record<string, { text: string; title: string }> = {
  "messages/alert": { text: "On the NeoAPRS computer", title: "NeoAPRS's own alert: the command the daemon runs on the computer it runs on" },
  "serial/pattern": { text: "Search", title: "Used when no port is chosen, and when the chosen port cannot be opened" },
};

/** The antenna's keys belong to the station, though they are the beacon's to send. */
const ANTENNA = ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"];

interface Group {
  id: string;
  title: string;
  keys: string[];
}

const GROUPS: { id: string; title: string; prefixes: string[]; also?: string[]; except?: string[] }[] = [
  { id: "station", title: "Station", prefixes: ["station/"], also: ANTENNA },
  { id: "serial", title: "TNC", prefixes: ["tnc/", "serial/", "tcp/"] },
  { id: "web", title: "Web page", prefixes: ["web/"] },
  { id: "log", title: "Log", prefixes: ["log/"] },
  { id: "messages", title: "Messaging", prefixes: ["messages/"], except: ALERT },
  { id: "notifications", title: "Notifications", prefixes: [], also: ALERT },
  { id: "map", title: "Map", prefixes: ["map/"] },
  { id: "update", title: "Update check", prefixes: ["update/"] },
  { id: "beacon", title: "Beacon", prefixes: ["beacon/"], except: ANTENNA },
  { id: "status", title: "Status", prefixes: ["status/"] },
];

/** Which settings a form shows: the Beacon tab has what the beacon says and sends, the Settings tab the rest (and any key this file does not know), so that no key is in two places. */
export type Scope = "settings" | "beacon";
const SCOPE_GROUPS: Record<Scope, readonly string[]> = {
  beacon: ["station", "beacon", "status"],
  settings: ["serial", "web", "log", "messages", "notifications", "map", "update"],
};

/** The order of the TNC group on the page: the port and its speed, the keep-alive, then the search (which the port falls back to). */
const TNC_ORDER = ["tnc/profile", "serial/port", "serial/baud", "tcp/host", "tcp/port", "tnc/check_sec", "serial/pattern", "serial/skip", "serial/last_port"];

function rank(key: string): number {
  const at = TNC_ORDER.indexOf(key);
  return at < 0 ? TNC_ORDER.length : at;
}

/** Settings that stay in the daemon (`neoaprs db set`) and are not on the page: the address the update check asks. */
const NOT_ON_THE_PAGE: readonly string[] = ["update/url"];

/** The keys in the order of the daemon's list (a key it did not list last; the TNC group in its own order), in the groups of the form `scope` shows. */
export function groupKeys(keys: readonly string[], scope: Scope = "settings"): Group[] {
  const order = (key: string): number => {
    const at = (CONFIG_KEYS as readonly string[]).indexOf(key);
    return at < 0 ? CONFIG_KEYS.length : at;
  };
  const sorted = keys.filter((k) => !NOT_ON_THE_PAGE.includes(k)).sort((a, b) => order(a) - order(b));
  const groups: Group[] = GROUPS.map((g) => ({
    id: g.id,
    title: g.title,
    keys: sorted.filter((k) => (g.also?.includes(k) ?? false) || (g.prefixes.some((p) => k.startsWith(p)) && !g.except?.includes(k))),
  }));
  const tnc = groups.find((g) => g.id === "serial");
  if (tnc) tnc.keys.sort((a, b) => rank(a) - rank(b));
  const known = new Set(groups.flatMap((g) => g.keys));
  groups.push({ id: "other", title: "Other", keys: sorted.filter((k) => !known.has(k)) });
  const shown = scope === "beacon" ? SCOPE_GROUPS.beacon : [...SCOPE_GROUPS.settings, "other"];
  return shown.flatMap((id) => groups.filter((g) => g.id === id && g.keys.length > 0));
}

/** The keys whose draft is not what the daemon has: what Save sends. */
export function changedValues(draft: Readonly<Record<string, string>>, values: Readonly<Record<string, string>>): Record<string, string> {
  const changed: Record<string, string> = {};
  for (const [key, text] of Object.entries(draft)) if (key in values && text !== values[key]) changed[key] = text;
  return changed;
}

/** The setting an error of the daemon is about: its text names the key ("set_config: station/lat: 95 is not between -90 and 90"). The longest key that is named wins. */
export function errorKey(text: string, keys: readonly string[]): string | null {
  const named = keys.filter((k) => text.startsWith(`${k}:`) || text.includes(` ${k}:`) || text.startsWith(k));
  return named.sort((a, b) => b.length - a.length)[0] ?? null;
}

/** What is wrong with the setting, without the command and the key in front. */
export function errorReason(text: string, key: string): string {
  const at = text.indexOf(key);
  return at < 0 ? text : text.slice(at + key.length).replace(/^:\s*/, "");
}

const SERIAL_ONLY = ["serial/port", "serial/baud"];
/** The search for the radio, which a serial TNC falls back to where the daemon can search at all. */
const SEARCH = ["serial/pattern", "serial/skip"];

/** The profile a form shows (its draft or the daemon's value), or undefined for a key this page does not know. */
function profileOf(key: string | undefined) {
  return TNC_PROFILES.find((p) => p.key === key);
}

/** Whether a setting is shown for the chosen TNC profile: the host and port for one that is reached over TCP, the port and speed for a serial one, with the search for the radio where the daemon can search (`search`, false
 * where it cannot: Windows, macOS), the keep-alive for one that can be asked if it is there; the access key while the daemon lets the network in (`network`) and has made one. The port the search found last is no field:
 * the port's own control says it. */
export function shownFor(key: string, profileKey: string | undefined, network = true, search = true): boolean {
  if (key === "web/key") return network;
  if (key === "serial/last_port") return false;
  const profile = profileOf(profileKey);
  if (!profile) return true;
  if (key.startsWith("tcp/")) return profile.transport === "tcp";
  if (SERIAL_ONLY.includes(key)) return profile.transport === "serial";
  if (SEARCH.includes(key)) return profile.transport === "serial" && search;
  if (key === "tnc/check_sec") return profile.probe;
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
