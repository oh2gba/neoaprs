// The settings form's logic: which key goes in which group, what each field says of itself, which keys the user changed, and which field an error of the daemon is about.
// The keys and their order come from the daemon (CONFIG_KEYS of the generated lists); a key this file does not know is shown under its own name.
import { DETAIL_CHOICES } from "@/lib/mapfetch";
import { STATUS_CHOICES, statusShown, statusSource } from "@/lib/status";
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
  /** The text of the (i) beside the field, one paragraph for each entry: what the setting is for, what to pick, an example. Only for a field a non-developer may not understand. */
  tip?: readonly string[];
  /** What the (i) is called for a screen reader and on hover; else "About" and the label. */
  tipLabel?: string;
  kind?: FieldKind;
  /** The values a `choice` offers: the text of the setting, or the text with the words it is shown as. */
  choices?: readonly (string | Choice)[];
}

export interface Choice {
  value: string;
  label: string;
}

export const FIELDS: Record<string, FieldInfo> = {
  "station/call": { label: "Call" },
  "station/lat": { label: "Latitude", unit: "°" },
  "station/lon": { label: "Longitude", unit: "°" },
  "station/symbol_table": { label: "Symbol" },
  "station/symbol_code": { label: "Symbol code" },
  "station/comment": {
    label: "Comment",
    tip: [
      "A short text sent with your position in every beacon. Other stations see it beside your name on their map. Letters, digits and ordinary punctuation, no | or ~. It can be 43 characters long, 36 when Power is set.",
      "Example: Home station, 2 m FM",
    ],
  },
  "station/status": {
    label: "Text",
    empty: "none",
    tip: [
      "A line about what you are doing, sent on its own, not with every beacon. Other stations see it as your status. It goes out when it is new and the Every time has passed since the last status. Up to 55 characters, no | or ~.",
      "Example: At the summer cottage, QRV 145.500 FM",
    ],
  },
  "beacon/power_w": {
    label: "Power",
    unit: "W",
    empty: "none",
    tip: [
      "The transmitter's output power. Together with the antenna height, gain and direction it adds a short code (PHG) to the beacon that tells others how far you can be heard. Leave it empty to send none of the four.",
      "Example: 5",
    ],
  },
  "beacon/antenna_height_m": {
    label: "Antenna height",
    unit: "m",
    tip: [
      "How high the antenna is above the average ground around it, not above the sea. Used only for the PHG code.",
      "Example: 10 for a mast on a house on level ground",
    ],
  },
  "beacon/antenna_gain_db": {
    label: "Antenna gain",
    unit: "dB",
    tip: ["How much the antenna concentrates the signal, 0 to 9 dB. Use 0 if you do not know. Used only for the PHG code.", "Example: 3"],
  },
  "beacon/antenna_direction": {
    label: "Antenna direction",
    kind: "choice",
    choices: ["omni", "N", "NE", "E", "SE", "S", "SW", "W", "NW"],
    tip: [
      "The way the antenna favours: omni when it works the same in every direction, as most whips and verticals do, or the point of the compass a beam antenna points to. Used only for the PHG code.",
    ],
  },
  "tnc/profile": {
    label: "Radio type",
    kind: "choice",
    choices: TNC_PROFILES.map((p) => ({ value: p.key, label: p.name })),
    tipLabel: "Which radio type to pick",
    tip: [
      "This tells NeoAPRS how to talk to your radio or modem (its TNC, the part that turns sound into packets). Pick the line that matches yours.",
      "KISS TNC: Mobilinkd, NinoTNC, TNC-Pi, and the Kenwood TH-D74 and TH-D75 with KISS switched on at the radio. The usual choice.",
      "KISS over TCP: Direwolf or a sound-card modem running on this or another computer. A Digirig or SignaLink goes this way too.",
      "Kenwood TH-D7, TM-D700, TS-2000: NeoAPRS puts the radio into KISS itself. So it does for the TM-D710 and TH-D72, and for the Kantronics KPC-3+.",
      "Not sure? See the radio guide, docs/RADIOS.md.",
    ],
  },
  "serial/port": {
    label: "Port",
    empty: "/dev/ttyUSB0",
    tipLabel: "About the port",
    tip: [
      "The connection to the radio. On Linux, automatic means NeoAPRS listens to the USB ports until it finds the radio, and remembers it. Choose a port yourself if you have several devices, or if the search picks the wrong one.",
      "A USB radio is /dev/ttyUSB0 on Linux and COM3 on Windows. A Bluetooth radio appears in this list after you have paired it with the computer.",
      "Refresh reads the list again, for example after you plug the cable in.",
    ],
  },
  "serial/baud": {
    label: "Speed",
    unit: "baud",
    tipLabel: "About the speed",
    tip: [
      "The speed of the cable between the computer and the TNC. Leave it empty: NeoAPRS then uses the speed of the TNC you chose, 9600 for most.",
      "Set it only if the manual of your TNC says so, for example 57600 for a NinoTNC. Bluetooth and TCP connections have no speed.",
    ],
  },
  "tcp/host": { label: "TCP host" },
  "tcp/port": { label: "TCP port", title: "Direwolf 8001, soundmodem 8100" },
  "serial/last_port": { label: "Last port found", kind: "readonly", empty: "-" },
  "serial/pattern": { label: "Ports to search", title: "Device globs, separated by spaces" },
  "serial/skip": { label: "Ports to skip", empty: "none", title: "Device paths, separated by commas" },
  "tnc/check_sec": {
    label: "Keep-alive",
    unit: "s",
    zero: "off",
    tipLabel: "About the keep-alive",
    tip: [
      "When nothing at all has come from the radio for this many seconds, NeoAPRS asks it whether it is still there. That way a radio that was switched off and on again is noticed and put back into KISS.",
      "60 suits most. 0 turns it off. It applies to the Kenwood and Kantronics TNCs, which can be asked; a KISS TNC is not asked.",
    ],
  },
  "web/network": {
    label: "Allow access from the network",
    kind: "bool",
    tipLabel: "About network access",
    tip: [
      "For NeoAPRS on a Raspberry Pi in the shack with the page opened on a laptop or a phone at home. Without this, only the computer NeoAPRS runs on can open the page.",
      "Set it to yes and Save: an access key appears with the addresses to open. Type the key once on each device.",
      "The connection is plain http on your home network: fine at home, not for the internet. Do not open a port to NeoAPRS in your router.",
    ],
  },
  "web/key": {
    label: "Access key",
    kind: "readonly",
    tipLabel: "About the access key",
    tip: [
      "The password for the other devices. Open one of the addresses below on the laptop or phone and type this key once; the device stays logged in.",
      "New key makes another one and logs every other device out. Type the new key again on each.",
    ],
  },
  "map/hide_after_min": {
    label: "Hide stations after",
    unit: "min",
    zero: "never",
    tipLabel: "About leaving the map",
    tip: [
      "A station that has not sent its position for this long is taken off the map. It stays in the Stations table. 180 minutes is three hours; 0 keeps stations on the map for ever.",
      "A single station can have its own time in its details.",
    ],
  },
  "map/radius_km": {
    label: "Radius",
    unit: "km",
    tipLabel: "About the radius",
    tip: [
      "How far from your station, in every direction, the detailed map reaches. The world map is always there; this is the area with streets and names.",
      "A bigger radius means a bigger download: 150 km is a region, 500 km a large part of a country. The size is shown before you start.",
    ],
  },
  "map/maxzoom": {
    label: "Detail",
    kind: "choice",
    choices: DETAIL_CHOICES,
    tipLabel: "About the detail",
    tip: [
      "How closely you can zoom in on the detailed map: towns, streets or houses.",
      "Each step up makes the map several times bigger and the download longer. Streets are enough for most; choose houses only for a small radius.",
    ],
  },
  "map/source": {
    label: "Map data",
    empty: "daily build",
    tipLabel: "About the map data",
    tip: [
      "Where the detailed map is cut from. Empty uses the newest daily build of the free Protomaps map of the world, which is made from OpenStreetMap.",
      "Fill it in only to use a map of your own: the web address or the file path of a PMTiles file.",
    ],
  },
  "digi/enabled": {
    label: "Digipeater",
    kind: "bool",
    tipLabel: "What the digipeater does",
    tip: [
      "Helps nearby stations that cannot reach a digipeater: packets asking for WIDE1-1, or sent through your call, are repeated once by your radio.",
      "Leave it off unless you are in a spot with poor coverage.",
    ],
  },
  "messages/alert": { label: "Alert", kind: "bool" },
  "messages/alert_command": { label: "Command" },
  "status/source": {
    label: "Status",
    kind: "choice",
    choices: STATUS_CHOICES,
    tip: [
      "A status is a line other stations see with your name. Off sends none. A text of my own sends the line you type. The frequency from my radio asks your radio, through rigctld, what it is tuned to and sends that.",
    ],
  },
  "status/rigctld": {
    label: "Rigctld",
    empty: "127.0.0.1:4532",
    tip: [
      "rigctld is a small Hamlib program that lets a computer ask a radio what it is tuned to; start it for your radio first. Type where it listens, as address:port. 4532 is the usual port.",
      "Example: 127.0.0.1:4532",
    ],
  },
  "status/interval_min": {
    label: "Every",
    unit: "min",
    tip: [
      "The least time between two status reports, 10 to 1440 minutes. A status is not sent again while it says the same as the last one, however long it has been.",
      "Example: 30",
    ],
  },
  "status/template": {
    label: "Text",
    tip: [
      "The status is made from this text with what your radio is tuned to now: {freq} becomes the frequency and {mode} the mode. Up to 55 characters once they are filled in.",
      "Example: QRV {freq} {mode} gives QRV 14.074 MHz USB",
    ],
  },
  "beacon/interval_min": {
    label: "Interval",
    unit: "min",
    zero: "off",
    tip: [
      "How often your position is sent, in minutes, 10 at the least. 0 sends none by itself; Beacon now still sends one. Every beacon uses the channel for everyone around, so choose it with care.",
      "Example: 30 for a station that stays where it is",
    ],
  },
  "beacon/path": {
    label: "Path",
    empty: "direct",
    tip: [
      "The digipeaters, the stations that repeat your packet so it travels further, in the order it should use them, separated by commas. WIDE1-1,WIDE2-1 is the usual choice. Empty sends direct, with no help.",
      "Example: WIDE1-1,WIDE2-1",
    ],
  },
};

/** The settings of the daemon's own alert, which the Notifications group shows (beside the alert of the browser, which is the page's). */
const ALERT = ["messages/alert", "messages/alert_command"];

/** The heading that goes above a key inside its group: the daemon's own alert, which runs on the computer NeoAPRS runs on, whichever device shows the page. */
export const SUBGROUPS: Record<string, { text: string; title: string; tipLabel: string; tip: readonly string[] }> = {
  "messages/alert": {
    text: "On the NeoAPRS computer",
    title: "NeoAPRS's own alert: the command the daemon runs on the computer it runs on",
    tipLabel: "About the alerts",
    tip: [
      "A new message can alert you in two places. This group is the NeoAPRS computer itself: with Alert on, it runs the Command when a message arrives, by default a notification and a sound. On a Raspberry Pi in the shack that is the speaker of the Pi.",
      "The next group is this browser, on whatever device has the page open: no alert, a sound, a sound and a pop-up, or a pop-up only. Each device chooses for itself, and Test sound and Test pop-up try it.",
      "If you read NeoAPRS on the computer it runs on, one of the two is enough; use both only if you want to be told twice.",
    ],
  },
};

/** The antenna's keys belong to the station, though they are the beacon's to send. */
const ANTENNA = ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"];

interface Group {
  id: string;
  title: string;
  keys: string[];
}

const GROUPS: { id: string; title: string; prefixes: string[]; also?: string[]; except?: string[] }[] = [
  { id: "station", title: "Station", prefixes: ["station/"], also: ANTENNA, except: ["station/status"] },
  { id: "serial", title: "TNC", prefixes: ["tnc/", "serial/", "tcp/"] },
  { id: "web", title: "Web page", prefixes: ["web/"] },
  { id: "notifications", title: "Notifications", prefixes: [], also: ALERT },
  { id: "map", title: "Map", prefixes: ["map/"] },
  { id: "digi", title: "Digipeater", prefixes: ["digi/"] },
  { id: "beacon", title: "Beacon", prefixes: ["beacon/"], except: ANTENNA },
  { id: "status", title: "Status", prefixes: ["status/"], also: ["station/status"] },
];

/** Which settings a form shows: the Beacon tab has what the beacon says and sends, the Settings tab the rest (and any key this file does not know), so that no key is in two places. */
export type Scope = "settings" | "beacon";
const SCOPE_GROUPS: Record<Scope, readonly string[]> = {
  beacon: ["station", "beacon", "status"],
  settings: ["serial", "digi", "web", "notifications", "map"],
};

/** The order of the TNC group on the page: the port and its speed, the keep-alive, then the search (which the port falls back to). */
const TNC_ORDER = ["tnc/profile", "serial/port", "serial/baud", "tcp/host", "tcp/port", "tnc/check_sec", "serial/pattern", "serial/skip", "serial/last_port"];

/** The Status group: the choice first, then what that choice needs. */
const STATUS_ORDER = ["status/source", "station/status", "status/rigctld", "status/template", "status/interval_min"];
const GROUP_ORDER: Record<string, readonly string[]> = { serial: TNC_ORDER, status: STATUS_ORDER };

function rank(order: readonly string[], key: string): number {
  const at = order.indexOf(key);
  return at < 0 ? order.length : at;
}

/** Settings that stay in the daemon (`neoaprs db set`) and are not on the page: the address the update check asks, which ports the search for the radio looks at and leaves alone, and the port and the host names of the page itself
 * (the defaults suit nearly everyone, and the daemon moves to a free port and says which in the log). */
const NOT_ON_THE_PAGE: readonly string[] = ["update/url", "serial/pattern", "serial/skip", "web/port", "web/allowed_hosts"];

/** The keys in the order of the daemon's list (a key it did not list last; the TNC and Status groups in their own order), in the groups of the form `scope` shows. */
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
  for (const group of groups) {
    const order = GROUP_ORDER[group.id];
    if (order) group.keys.sort((a, b) => rank(order, a) - rank(order, b));
  }
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

/** Whether a field of the Beacon tab is shown for the values the form holds: the Status group shows what its source needs, and the antenna's height, gain and direction come once there is a power (they only make the PHG code with it). */
export function shownByValues(key: string, values: Readonly<Record<string, string>>): boolean {
  if (key.startsWith("status/") || key === "station/status") return statusShown(key, statusSource(values));
  if (ANTENNA.includes(key) && key !== "beacon/power_w") return (values["beacon/power_w"] ?? "").trim() !== "";
  return true;
}
