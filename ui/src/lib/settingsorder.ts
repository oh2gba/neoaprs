// The order of fields inside the Settings and My station groups that have their own (the daemon
// lists keys in its order; these groups use the order the eye wants): Radio, Status, Beacon and
// Station. `rank` is a key's place in an order, after every listed one when it is not there.
import { ANTENNA } from "@/lib/beaconoff";

/**
 * The Radio group's own rows: the RX only tickbox (the radios' boxes follow:
 * components/SettingsRadio.vue), then the port radio 1's search found (no field).
 */
const TNC_ORDER = ["station/transmit", "serial/last_port"];

/**
 * The Status group: the choice, then Every (as the Beacon group has the interval with its choice),
 * then what the chosen source needs.
 */
const STATUS_ORDER = ["status/source", "status/interval_min", "station/status", "status/rigctld", "status/template"];
/**
 * The Beacon group: the Beacon choice (a fixed station's interval, Off or On for a moving one),
 * what it travels as, what it says, then the folds (antenna, path).
 */
const BEACON_ORDER = ["beacon/interval_min", "beacon/travel", "station/comment", ...ANTENNA, "beacon/path"];
/**
 * The Station group: the call, where the position comes from and what that needs (gpsd address, or
 * serial port and speed), the place (only for a fixed station) and the symbol.
 */
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
export const GROUP_ORDER: Record<string, readonly string[]> = {
  station: STATION_ORDER,
  serial: TNC_ORDER,
  status: STATUS_ORDER,
  beacon: BEACON_ORDER,
};

export function rank(order: readonly string[], key: string): number {
  const at = order.indexOf(key);
  return at < 0 ? order.length : at;
}
