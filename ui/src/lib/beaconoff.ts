// When the beacon is Off (`beacon/interval_min` is 0, for a station that moves too): which fields of the Beacon tab are then greyed out. Off sends no beacon and no status report, so what belongs to them is shown with its value and not asked;
// the Station group and the Beacon choice itself are never greyed. The daemon's rule is Config.beacon_on (neoaprs/config.py).

/** The antenna's keys belong to the station, though they are the beacon's to send. */
export const ANTENNA = ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"];

/** Whether the beacon is Off in these settings (key to text): `beacon/interval_min` is 0. False while the settings do not have it. */
export function beaconOff(values: Readonly<Record<string, string>>): boolean {
  const interval = values["beacon/interval_min"];
  return interval !== undefined && ["", "0"].includes(interval.trim());
}

/** Whether a field is greyed out (shown, with its value, and not changeable) for these settings: while the beacon is Off, what the beacon says (Travelling, the comment, the antenna, the path) and the whole Status group. */
export function disabledByValues(key: string, values: Readonly<Record<string, string>>): boolean {
  if (!beaconOff(values)) return false;
  return (
    key.startsWith("status/") ||
    key === "station/status" ||
    key === "beacon/travel" ||
    key === "station/comment" ||
    key === "beacon/path" ||
    ANTENNA.includes(key)
  );
}
