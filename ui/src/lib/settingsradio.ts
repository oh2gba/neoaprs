// Which settings are there for the radios in use: the fields of the FM radio's TNC profile (its transport), and what a radio that is off leaves out (the HF radio has no paths, no digipeater and no moving station).
import { fmOn, hfOn } from "@/lib/radiosides";
import { profileOf } from "@/lib/tncprofile";

const SERIAL_ONLY = ["serial/port", "serial/baud"];

/** Whether a setting is shown for the FM radio's chosen TNC profile: the host and port for one that is reached over TCP, the port and speed for a serial one (the sound card and the keying are the HF radio's and always there); the access key while the daemon lets the network in (`network`) and has made one.
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

/** The keys that are there only for the FM radio, whose network has digipeaters: the path and the digipeater. */
const PATH_KEYS = ["beacon/path", "digi/enabled"];
/** What a moving station travels as: SmartBeaconing's preset, which is FM's. (The GPS itself, the Position choice and where the receiver is, stay: a station on HF alone can move, with the timed beacon.) */
const MOVING_KEYS = ["beacon/travel"];

/** Whether a setting is there for the radios that are on (`fm/enabled` and `hf/enabled` of the values): the one Beacon choice while any radio is, and the path, the digipeater and Travelling while FM is. */
export function shownByRadios(key: string, values: Readonly<Record<string, string>>): boolean {
  if (key === "beacon/interval_min") return fmOn(values) || hfOn(values);
  if (PATH_KEYS.includes(key) || MOVING_KEYS.includes(key)) return fmOn(values);
  return true;
}
