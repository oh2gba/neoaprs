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

/** The SSIDs a call may carry, as the text of the number: "1" to "15" (no SSID, and `-0`, is the empty text). */
export const SSIDS: readonly string[] = Array.from({ length: LIMITS.call.maxSsid }, (_, i) => String(i + 1));

/** A call as the settings keep it, taken apart for the call field: the call and its SSID ("" for none, else "1" to "15"; a `-0` is none). A text that has no SSID of this kind is all call. */
export function splitCall(text: string): { base: string; ssid: string } {
  const call = normalizeCall(text);
  const found = /^(.*)-(\d{1,2})$/.exec(call);
  const number = found === null ? NaN : Number(found[2]);
  return found !== null && number <= LIMITS.call.maxSsid ? { base: found[1] ?? "", ssid: number === 0 ? "" : String(number) } : { base: call, ssid: "" };
}

/** The call and its SSID put together as the settings keep them: the SSID after a dash, none for "" (and a call that is not there has no SSID). */
export function joinCall(base: string, ssid: string): string {
  return base === "" || ssid === "" || ssid === "0" ? base : `${base}-${ssid}`;
}

/** What is typed or pasted into the field of the call: the call is the letters and digits in capitals; a dash with a number from 0 to 15 after it (`OH2GBA-9`) is the SSID, which the field moves to its dropdown (`ssid`, "" for none, null when
 * there is none or it is not a number the dropdown has); a dash alone, or one with a number still being typed, is kept in `text` for the moment, the rest of what is typed is not a call's and goes. */
export function callInput(raw: string): { base: string; ssid: string | null; text: string } {
  const typed = raw.toUpperCase().trim();
  const found = /^([^-]*)-(\d{0,2})$/.exec(typed);
  const clean = (part: string): string => part.replace(/[^A-Z0-9]/g, "");
  if (found === null) return { base: clean(typed), ssid: null, text: clean(typed) };
  const base = clean(found[1] ?? "");
  const digits = found[2] ?? "";
  const ssid = digits !== "" && Number(digits) <= LIMITS.call.maxSsid ? (Number(digits) === 0 ? "" : String(Number(digits))) : null;
  return { base, ssid, text: base === "" ? "" : `${base}-${digits}` };
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
