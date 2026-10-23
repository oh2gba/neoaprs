// A call as the page checks it before the daemon does (neoaprs/callsign.py): 1 to 6 letters and digits and an SSID from 0 to 15 if it has one; and a list of calls separated by commas, which is how a
// path is written (a station's own path, the setting beacon/path). The daemon checks all of it again; the page only keeps the user from sending what it would refuse.

const CALL = /^[A-Z0-9]{1,6}(-([0-9]|1[0-5]))?$/;
/** The most digipeaters a path may have (MAX_PATH of neoaprs/ax25.py). */
const MAX_PATH = 8;

/** A call as it is typed: spaces off, upper case. */
export function normalizeCall(text: string): string {
  return text.trim().toUpperCase();
}

/** A call with an optional SSID from 0 to 15, as the daemon takes it (it also takes `-0`, which it writes without). */
export function validCall(text: string): boolean {
  return CALL.test(normalizeCall(text));
}

/** The address of the call's page on QRZ.com, which is the base call's (the SSID off); null for a name that is no call. */
export function qrzUrl(text: string): string | null {
  const call = normalizeCall(text);
  return validCall(call) ? `https://www.qrz.com/db/${call.split("-")[0]}` : null;
}

/** The pieces of a list separated by commas, each as a call is typed (capitals, no blanks); the empty ones left out. */
export function callList(text: string): string[] {
  return text
    .split(",")
    .map(normalizeCall)
    .filter((piece) => piece !== "");
}

/** The calls of a path as the daemon reads it (capitals, no blanks); null when a piece is no call or there are more than 8. An empty text is a path of no calls: direct. */
export function parsePath(text: string): string[] | null {
  const calls = callList(text);
  return calls.length <= MAX_PATH && calls.every(validCall) ? calls : null;
}
