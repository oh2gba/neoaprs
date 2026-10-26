// What the chosen TNC profile means for the speed and the port of the radio.

import { TNC_PROFILES } from "@/protocol/lists";

/** The profile a form shows (its draft or the daemon's value), or undefined for a key this page does not know. */
export function profileOf(key: string | undefined) {
  return TNC_PROFILES.find((p) => p.key === key);
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
