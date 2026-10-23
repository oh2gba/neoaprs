// The stations a message may be written to at once, as the Messages tab's "Stations" list offers them: the stations heard in the last day (not objects, not items, not ourselves, not the email gateway, which
// has a tab of its own), the ones heard direct first and then the newest, and the calls of one message to several: the ones picked plus the one typed. Each recipient gets an ordinary message of its own
// (its own id, acknowledgement, attempts and conversation); the daemon spaces them on the air.
import { normalizeCall, validCall } from "@/lib/calls";
import { bytesLeft, isGateway } from "@/lib/messages";
import type { StationRow } from "@/protocol/protocol";

/** A station that can be picked. */
export interface Candidate {
  call: string;
  /** heard direct, with no digipeater in between */
  direct: boolean;
  /** UTC, ISO 8601 */
  heardAt: string;
}

/** How long ago a station was last heard to be in the list. */
const RECENT_MS = 24 * 3600 * 1000;

/** The stations to pick from: heard in the last day, those heard direct first, then the newest. */
export function candidates(stations: ReadonlyMap<string, StationRow>, own: string | null, now: number): Candidate[] {
  const ours = own === null ? "" : normalizeCall(own);
  return [...stations.values()]
    .filter(
      (s) => s.kind === "station" && !s.is_me && s.call !== ours && validCall(s.call) && !isGateway(s.call) && now - Date.parse(s.last_heard) <= RECENT_MS,
    )
    .map((s) => ({ call: s.call, direct: s.heard_direct > 0, heardAt: s.last_heard }))
    .sort((a, b) => Number(b.direct) - Number(a.direct) || (a.heardAt < b.heardAt ? 1 : a.heardAt > b.heardAt ? -1 : a.call.localeCompare(b.call)));
}

/** The candidates whose call contains what was typed in the filter box (capitals or not). */
export function matching(list: readonly Candidate[], filter: string): Candidate[] {
  const wanted = normalizeCall(filter);
  return wanted === "" ? [...list] : list.filter((c) => c.call.includes(wanted));
}

/** Whether a call may be added as a recipient: a call, not the email gateway and not one that is there already. */
export function addable(call: string, chosen: readonly string[]): boolean {
  return validCall(call) && !isGateway(call) && !chosen.includes(normalizeCall(call));
}

/** The calls the message goes to: those picked, then the one typed in the To box when it is a call of its own. */
export function recipientsOf(chosen: readonly string[], typed: string): string[] {
  return addable(typed, chosen) ? [...chosen, normalizeCall(typed)] : [...chosen];
}

/** Whether Send is on: the TNC is connected, there is a recipient, what is typed in the To box (if anything) is a call, and the text is there and fits. */
export function canSendAll(connected: boolean, chosen: readonly string[], typed: string, text: string): boolean {
  const typedOk = typed.trim() === "" || (validCall(typed) && !isGateway(typed));
  return connected && typedOk && recipientsOf(chosen, typed).length > 0 && text.trim() !== "" && bytesLeft(text) >= 0;
}
