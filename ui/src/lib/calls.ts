// A call as the page checks it before the daemon does (neoaprs/callsign.py): 1 to 6 letters and digits and an SSID from 0 to 15 if it has one; the calls a station may transmit under (an amateur call: not a placeholder such as N0CALL, 3 to 6
// characters with a digit and a letter); and a list of calls separated by commas, which is how a path is written (a station's own path, the setting beacon/path). The daemon checks all of it again, and
// ui/src/protocol/vectors.json holds the two to the same answers; the page only keeps the user from sending what it would refuse.
import { LIMITS } from "@/protocol/lists";

const CALL = new RegExp(`^[A-Z0-9]{1,${LIMITS.call.baseMax}}(-[0-9]{1,2})?$`);
const AMATEUR = new RegExp(`^(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z0-9]{${LIMITS.call.amateurBaseMin},${LIMITS.call.baseMax}}$`);

/** A call as it is typed: spaces off, upper case. */
export function normalizeCall(text: string): string {
  return text.trim().toUpperCase();
}

/** The base of a call as it is typed, in capitals: the call without its SSID. */
export function baseCall(text: string): string {
  return normalizeCall(text).split("-")[0] ?? "";
}

/** A call with an optional SSID from 0 to 15 (written with one or two digits), as the daemon takes it (it also takes `-0`, which it writes without). */
export function validCall(text: string): boolean {
  const call = text.trim();
  if ([...call].some((c) => c.charCodeAt(0) > 127)) return false;
  const found = CALL.exec(call.toUpperCase());
  return found !== null && (found[1] === undefined || Number(found[1].slice(1)) <= LIMITS.call.maxSsid);
}

/** Whether the call is a placeholder that programs ship with (N0CALL, NOCALL, MYCALL): never the call of anybody. */
export function placeholderCall(text: string): boolean {
  return (LIMITS.call.placeholders as readonly string[]).includes(baseCall(text));
}

/** Whether the station may transmit under the call: a call (validCall) of an amateur's shape and no placeholder. */
export function mayTransmitAs(text: string): boolean {
  return validCall(text) && !placeholderCall(text) && AMATEUR.test(baseCall(text));
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

/** The pieces of a list as `callList` has them, written with commas: how the daemon keeps a path. */
export const callListText = (text: string): string => callList(text).join(",");

/** The word that stands for no digipeaters at all in a path that is typed (the daemon's `DIRECT`); it is no call and stands alone. */
export const DIRECT = LIMITS.path.direct;

/** The calls of a list of digipeaters as the daemon reads it (capitals, no blanks); null when a piece is no call (DIRECT is none) or there are more than the daemon takes. An empty text is a list of no calls. */
export function parsePath(text: string): string[] | null {
  const calls = callList(text);
  return calls.length <= LIMITS.path.maxCalls && calls.every((call) => validCall(call) && call !== DIRECT) ? calls : null;
}

/** What a path that is typed says: nothing (`auto`: the recommended or automatic path, never no digipeaters), DIRECT alone (`direct`: no digipeaters, explicitly) or digipeaters; null when it is none of them. */
export type PathSetting = { kind: "auto" } | { kind: "direct" } | { kind: "calls"; calls: string[] };

export function parsePathSetting(text: string): PathSetting | null {
  const calls = callList(text);
  if (calls.length === 0) return { kind: "auto" };
  if (calls.length === 1 && calls[0] === DIRECT) return { kind: "direct" };
  const parsed = parsePath(text);
  return parsed === null ? null : { kind: "calls", calls: parsed };
}

/** The digipeaters a path setting stands for (the beacon's: empty is `recommended`, the path of the station's symbol (`recommendedPath` of lib/symbols.ts), DIRECT is none); null when the text is no path. */
export function pathCalls(text: string, recommended: string): string[] | null {
  const setting = parsePathSetting(text);
  return setting === null ? null : setting.kind === "direct" ? [] : setting.kind === "auto" ? recommended.split(",") : setting.calls;
}
