// When the beacon is Off (`beacon/interval_min` is 0, for a station that moves too) or transmitting is switched off (RX only): which fields of the Beacon tab are then greyed out. Off is no automatic beacon and no automatic status (Beacon now still sends), so only the timing is greyed;
// RX only sends nothing, so all that the beacon says is greyed, shown with its value and not asked; the Station group and the Beacon choice itself are never greyed. The daemon's rule is Config.beacon_on (neoaprs/config.py).

/** The antenna's keys belong to the station, though they are the beacon's to send. */
export const ANTENNA = ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"];

/** Whether the beacon is Off in these settings (key to text): `beacon/interval_min` is 0. False while the settings do not have it. */
export function beaconOff(values: Readonly<Record<string, string>>): boolean {
  const interval = values["beacon/interval_min"];
  return interval !== undefined && ["", "0"].includes(interval.trim());
}

/** Whether transmitting is switched off (`station/transmit` is false: RX only): nothing is sent, so the beacon's fields are greyed as when the beacon is Off. */
export const rxOnly = (values: Readonly<Record<string, string>>): boolean => values["station/transmit"] === "false";

/** Whether a field is greyed out (shown, with its value, and not changeable) for these settings: while the beacon is Off only its timing (Travelling and the status's Every: there is no automatic beacon), for what is sent (the place, the symbol, the comment, the path, the antenna, the status text) is still what Beacon now sends; while transmitting is switched off (RX only) all of what the beacon says. */
export function disabledByValues(key: string, values: Readonly<Record<string, string>>): boolean {
  if (rxOnly(values)) return SENT.includes(key) || TIMING.includes(key) || key.startsWith("status/") || key === "station/status";
  return beaconOff(values) && TIMING.includes(key);
}

/** What the timer decides: the preset of a moving station and how often the status goes. */
const TIMING = ["beacon/travel", "status/interval_min"];
/** What the beacon says. */
const SENT = ["station/comment", "beacon/path", ...ANTENNA];
