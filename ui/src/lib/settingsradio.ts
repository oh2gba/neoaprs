// Which settings are there for the radio in use: the fields of a TNC profile's transport, and what the rules of the radio (the `rules` of the tnc topic, the daemon's one fact about it) leave out.
import { profileOf } from "@/lib/tncprofile";
import type { RadioRulesState } from "@/protocol/protocol";

const SERIAL_ONLY = ["serial/port", "serial/baud"];

/** Whether a setting is shown for the chosen TNC profile: the host and port for one that is reached over TCP, the port and speed for a serial one; the access key while the daemon lets the network in (`network`) and has made one.
 * The port the search found last is no field: the port's own control says it. */
export function shownFor(key: string, profileKey: string | undefined, network = true): boolean {
  if (key === "web/key" || key === "web/https") return network;
  if (key === "serial/last_port") return false;
  const profile = profileOf(profileKey);
  if (!profile) return true;
  if (key.startsWith("tcp/")) return profile.transport === "tcp";
  if (key.startsWith("mercury/")) return profile.transport === "modem";
  if (SERIAL_ONLY.includes(key)) return profile.transport === "serial";
  return true;
}

/** The keys that are there only on a radio whose network has digipeaters (FM): the path and the digipeater. */
const PATH_KEYS = ["beacon/path", "digi/enabled"];
/** The keys of a moving station: where the position comes from and how it travels, which a radio without SmartBeaconing (HF) has no use for. */
const MOVING_KEYS = ["gps/source", "gps/host", "gps/device", "gps/baud", "beacon/travel"];

/** Whether a setting is there for the rules of the radio in use (the `rules` of the tnc topic, the daemon's one fact about the radio; null before it has said: everything is there, as before): the HF beacon's own
 * interval only on an HF radio and the usual one only elsewhere, the path and the digipeater only where the network has digipeaters, the moving station's keys only where SmartBeaconing applies. */
export function shownByRules(key: string, rules: RadioRulesState | null): boolean {
  if (rules === null) return key !== "hf/beacon_interval_min";
  if (key === "hf/beacon_interval_min") return rules.kind === "hf";
  if (key === "beacon/interval_min") return rules.kind !== "hf";
  if (PATH_KEYS.includes(key)) return rules.paths;
  if (MOVING_KEYS.includes(key)) return rules.smart_beacon;
  return true;
}
