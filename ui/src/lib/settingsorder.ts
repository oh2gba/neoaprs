// The order of the fields inside the groups of the Settings and My station tabs that have one of their own (the daemon lists the keys in its order; these groups put theirs the way the eye wants them): the Radio group, the
// Status group, the Beacon group and the Station group. `rank` is where a key stands in an order, after every listed one when it is not there.
import { ANTENNA } from "@/lib/beaconoff";

/** The order of the Radio group's own rows: the RX only tickbox (the radios' boxes follow it: components/SettingsRadio.vue), and the port radio 1's search found last (no field). */
const TNC_ORDER = ["station/transmit", "serial/last_port"];

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
