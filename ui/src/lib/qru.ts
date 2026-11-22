// Asking QRU for local info (the Nearby tab): the request text from the word (INFO or a group)
// and the typed distance, how long Ask waits after a request, and what the section's row says
// of the last one. The daemon checks the text again; its limits are LIMITS.qru (the farthest,
// the seconds between requests).
import { t } from "@/i18n";
import { hourMinuteText } from "@/lib/format";
import { LIMITS } from "@/protocol/lists";
import type { QruAsked, QruServer } from "@/protocol/protocol";

/**
 * The typed distance in whole km; null if empty (the servers' own range), NaN if not 1 to the
 * maximum.
 */
export function kmOf(text: string): number | null {
  const typed = text.trim();
  if (typed === "") return null;
  const km = /^\d{1,5}$/.test(typed) ? Number(typed) : NaN;
  return km >= 1 && km <= LIMITS.qru.kmMax ? km : NaN;
}

/** Whether the typed distance is wrong (not empty, and not 1 to the maximum). */
export function kmWrong(text: string): boolean {
  return Number.isNaN(kmOf(text));
}

/**
 * The request text: `INFO` or the group, with the distance when there is one; null while the
 * distance is wrong.
 */
export function requestText(word: string, km: string): string | null {
  const distance = kmOf(km);
  if (Number.isNaN(distance)) return null;
  return distance === null ? word : `${word} ${distance}`;
}

/**
 * The seconds a request is still held for, 0 when it may go: the same text once per
 * LIMITS.qru.askEverySec, any two LIMITS.qru.askGapSec apart (the daemon's rule). `text` is the
 * request that would go; null counts only the gap.
 */
export function askWait(asked: QruAsked | null, nowMs: number, text: string | null = null): number {
  if (asked === null) return 0;
  const hold = text !== null && text === asked.text ? LIMITS.qru.askEverySec : LIMITS.qru.askGapSec;
  return Math.max(0, Math.ceil((Date.parse(asked.at) + hold * 1000 - nowMs) / 1000));
}

/**
 * How many servers have answered since the request was sent (one that listed groups for an
 * earlier request does not count).
 */
export function answeredSince(asked: QruAsked, servers: readonly QruServer[]): number {
  const sent = Date.parse(asked.at);
  return servers.filter((server) => Date.parse(server.at) >= sent).length;
}

export interface QruLook {
  state: string;
  /** The class that colours the state (the radio's `tnc-*`). */
  tone: string;
  line: string;
}

/**
 * The section's row: a refusal reason while there is one; else the last request with its send
 * time, waiting while the minute runs, then how many servers answered or none; null before a
 * request.
 */
export function qruLook(
  asked: QruAsked | null,
  servers: readonly QruServer[],
  refusal: string,
  nowMs: number,
): QruLook | null {
  if (refusal !== "") return { state: t("objects.qru_refused"), tone: "tnc-waiting", line: refusal };
  if (asked === null) return null;
  const time = hourMinuteText(asked.at);
  const state = t("objects.qru_state");
  if (askWait(asked, nowMs, asked.text) > 0)
    return { state, tone: "tnc-waiting", line: t("objects.qru_waiting", { time }) };
  const n = answeredSince(asked, servers);
  return n > 0
    ? { state, tone: "tnc-connected", line: t("objects.qru_answered", { time, n }) }
    : { state, tone: "tnc-stopped", line: t("objects.qru_no_answer", { time }) };
}

/**
 * The objects that answered our requests, by name, with the call of the server that sent each
 * (shown in the Stations tab hover).
 */
export function receivedFrom(servers: readonly QruServer[]): Map<string, string> {
  const found = new Map<string, string>();
  for (const server of servers) for (const name of server.received) found.set(name, server.call);
  return found;
}

export interface QruSentLine {
  /** "sent 1 · 1 arrived", or "1 arrived" when no closing line was heard. */
  text: string;
  /** Fewer arrived than the closing line says, and the wait for late ones is over. */
  warn: boolean;
  /** The request that Ask again sends; null unless `warn`. */
  again: string | null;
}

/**
 * What a server's row says of its last request: how many objects its closing line says it sent
 * and how many arrived. Fewer than sent, once the wait for late ones is over, gives the warn
 * colour and the request to ask again; null when there is nothing to say.
 */
export function sentLine(server: QruServer, nowMs: number): QruSentLine | null {
  const arrived = server.received.length;
  if (server.sent_objects === null)
    return arrived > 0 ? { text: t("objects.qru_got", { arrived }), warn: false, again: null } : null;
  const settled = server.settles_at !== null && Date.parse(server.settles_at) <= nowMs;
  const warn = settled && arrived < server.sent_objects;
  return {
    text: t("objects.qru_arrived", { sent: server.sent_objects, arrived }),
    warn,
    again: warn && server.request !== "" ? server.request : null,
  };
}
