// Asking QRU for local info (the Nearby tab): the text of a request, from the word (INFO or a group) and the distance the person typed, how long Ask waits after a request, and what the row of the section says of the last one.
// The daemon checks the text again; the numbers it is held to are LIMITS.qru (the farthest, the seconds between two requests).
import { t } from "@/i18n";
import { hourMinuteText } from "@/lib/format";
import { LIMITS } from "@/protocol/lists";
import type { QruAsked, QruServer } from "@/protocol/protocol";

/** The distance typed, as a whole number of kilometres: null for an empty field (the servers' own range), NaN for anything that is not 1 to the most. */
export function kmOf(text: string): number | null {
  const typed = text.trim();
  if (typed === "") return null;
  const km = /^\d{1,5}$/.test(typed) ? Number(typed) : NaN;
  return km >= 1 && km <= LIMITS.qru.kmMax ? km : NaN;
}

/** Whether the distance typed is wrong (not empty, and not 1 to the most). */
export function kmWrong(text: string): boolean {
  return Number.isNaN(kmOf(text));
}

/** The text of a request: `INFO` or the group, and the distance after it when there is one; null while the distance is wrong. */
export function requestText(word: string, km: string): string | null {
  const distance = kmOf(km);
  if (Number.isNaN(distance)) return null;
  return distance === null ? word : `${word} ${distance}`;
}

/** The seconds a request is still held for, 0 when it may go: the same text once in LIMITS.qru.askEverySec, any two LIMITS.qru.askGapSec apart (the daemon's rule), so a group can be asked for right after
 * a server listed it. `text` is the request that would go (requestText); null counts only the gap. */
export function askWait(asked: QruAsked | null, nowMs: number, text: string | null = null): number {
  if (asked === null) return 0;
  const hold = text !== null && text === asked.text ? LIMITS.qru.askEverySec : LIMITS.qru.askGapSec;
  return Math.max(0, Math.ceil((Date.parse(asked.at) + hold * 1000 - nowMs) / 1000));
}

/** How many servers have answered since the request was sent (a server that listed its groups for an earlier one does not count). */
export function answeredSince(asked: QruAsked, servers: readonly QruServer[]): number {
  const sent = Date.parse(asked.at);
  return servers.filter((server) => Date.parse(server.at) >= sent).length;
}

export interface QruLook {
  state: string;
  /** the class that colours the state (the radio's `tnc-*`) */
  tone: string;
  line: string;
}

/** The row of the section: a refusal (the reason, as the daemon's code has it) while there is one; else the last request with the time it was sent, waiting for answers while the minute runs, then how many servers answered or that none did; null before a request. */
export function qruLook(asked: QruAsked | null, servers: readonly QruServer[], refusal: string, nowMs: number): QruLook | null {
  if (refusal !== "") return { state: t("objects.qru_refused"), tone: "tnc-waiting", line: refusal };
  if (asked === null) return null;
  const time = hourMinuteText(asked.at);
  const state = t("objects.qru_state");
  if (askWait(asked, nowMs, asked.text) > 0) return { state, tone: "tnc-waiting", line: t("objects.qru_waiting", { time }) };
  const n = answeredSince(asked, servers);
  return n > 0
    ? { state, tone: "tnc-connected", line: t("objects.qru_answered", { time, n }) }
    : { state, tone: "tnc-stopped", line: t("objects.qru_no_answer", { time }) };
}

/** The objects that came in answer to our requests, by name: the call of the server that sent each (the Stations tab marks them, with the server in the hover). */
export function receivedFrom(servers: readonly QruServer[]): Map<string, string> {
  const found = new Map<string, string>();
  for (const server of servers) for (const name of server.received) found.set(name, server.call);
  return found;
}

export interface QruSentLine {
  /** "sent 1 · 1 arrived", or "1 arrived" when no closing line was heard */
  text: string;
  /** fewer arrived than the closing line says, and the time to wait for late ones is over */
  warn: boolean;
  /** the request that Ask again sends; null unless `warn` */
  again: string | null;
}

/** What a server's row says of its last request: how many objects its closing line says it sent and how many arrived. Fewer than sent, once the daemon's time for late ones is over, is the warn colour with the request to ask again;
 * null when there is nothing to say (no closing line and nothing arrived). */
export function sentLine(server: QruServer, nowMs: number): QruSentLine | null {
  const arrived = server.received.length;
  if (server.sent_objects === null) return arrived > 0 ? { text: t("objects.qru_got", { arrived }), warn: false, again: null } : null;
  const settled = server.settles_at !== null && Date.parse(server.settles_at) <= nowMs;
  const warn = settled && arrived < server.sent_objects;
  return { text: t("objects.qru_arrived", { sent: server.sent_objects, arrived }), warn, again: warn && server.request !== "" ? server.request : null };
}
