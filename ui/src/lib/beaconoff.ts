// When the beacon is Off (`beacon/interval_min` is 0, also for a moving station) or transmitting is
// off (RX only): which My station fields are greyed. Off means no automatic beacon or status
// (Beacon now still sends), so only the timing is greyed. RX only sends nothing, so everything the
// beacon says is greyed (shown, not asked); the Station group and the Beacon choice are never
// greyed. The daemon's rule is Config.beacon_on (neoaprs/config.py).

/** The antenna keys belong to the station, though the beacon sends them. */
export const ANTENNA = [
  "beacon/power_w",
  "beacon/antenna_height_m",
  "beacon/antenna_gain_db",
  "beacon/antenna_direction",
];

/**
 * Whether the beacon is Off in these settings (key to text): `beacon/interval_min` is 0. False if
 * the settings lack it.
 */
export function beaconOff(values: Readonly<Record<string, string>>): boolean {
  const interval = values["beacon/interval_min"];
  return interval !== undefined && ["", "0"].includes(interval.trim());
}

/**
 * Whether transmitting is off (`station/transmit` is false: RX only): nothing is sent, so beacon
 * fields are greyed as when Off.
 */
const rxOnly = (values: Readonly<Record<string, string>>): boolean => values["station/transmit"] === "false";

/**
 * Whether a field is greyed out (shown with its value, not changeable) for these settings. While
 * the beacon is Off only its timing (Travelling and the status's Every); the fields for what is
 * sent (place, symbol, comment, path, antenna, status text) stay, as Beacon now still sends them.
 * While transmitting is off (RX only), all the beacon says. `receiveOnly`: no radio that is on can
 * send (the page's `receiveOnly`); it greys as RX only does.
 */
export function disabledByValues(key: string, values: Readonly<Record<string, string>>, receiveOnly = false): boolean {
  if (receiveOnly || rxOnly(values))
    return SENT.includes(key) || TIMING.includes(key) || key.startsWith("status/") || key === "station/status";
  return beaconOff(values) && TIMING.includes(key);
}

/** What the timer decides: the preset of a moving station and how often the status goes. */
const TIMING = ["beacon/travel", "status/interval_min"];
/** What the beacon says. */
const SENT = ["station/comment", "beacon/path", ...ANTENNA];
