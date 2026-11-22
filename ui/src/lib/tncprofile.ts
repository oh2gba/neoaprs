// What the chosen TNC profile means for the speed and the port of the radio.

import { TNC_PROFILES } from "@/protocol/lists";

/** The profile a form shows (its draft or the daemon's value); undefined for an unknown key. */
function profileOf(key: string | undefined) {
  return TNC_PROFILES.find((p) => p.key === key);
}

/** The placeholder for an empty speed: the profile's own speed, else the daemon's default. */
export function speedFallback(profileKey: string | undefined, fallback: string): string {
  const baud = profileOf(profileKey)?.baud;
  return baud ? String(baud) : fallback;
}
