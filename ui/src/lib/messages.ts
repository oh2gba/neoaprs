// The messages of the topic `messages`: grouped into conversations (one for each other station), the thread of one, how many are unread, and the rules the compose box shows (the call, the bytes
// a message may still have). Messages we only overheard (sent to another station) are no conversation of ours: with `showOverheard` each pair of stations is listed as one, read-only in spirit.
// The daemon checks all of this again; the page only keeps the user from sending what it would refuse. What a call is, and a path, is lib/calls.ts.
import { t } from "@/i18n";
import { normalizeCall } from "@/lib/calls";
import { dateTimeText } from "@/lib/format";
import type { QueryKind } from "@/lib/stations";
import { LIMITS } from "@/protocol/lists";
import type { MessageRow } from "@/protocol/protocol";

export interface Conversation {
  /** the other station */
  call: string;
  /** the newest message of the conversation */
  last: MessageRow;
  count: number;
  /** messages that came in after the newest one the user has seen (never an overheard one) */
  unread: number;
  /** a pair of other stations, "OH2AAA>OH2BBB", whose messages we only heard */
  overheard: boolean;
}

/** The APRS email gateway (aprs-is.net/Email.aspx): messages to and from it are the Email tab's, not conversations of the Messages tab. */
export const EMAIL_GATEWAY = LIMITS.message.gateway;

const encoder = new TextEncoder();

/** Whether the call, as it is typed, is the email gateway. */
export function isGateway(call: string): boolean {
  return normalizeCall(call) === EMAIL_GATEWAY;
}

/** The other station of a message: who sent it when it came in, who it went to when we sent it; for one we overheard the pair "sender>addressee". */
export function peerOf(row: MessageRow): string {
  if (row.state === "overheard") return `${row.from_call}>${row.to_call}`;
  return row.direction === "in" ? row.from_call : row.to_call;
}

/** The call to write to from a conversation: the other station, or the sender of an overheard pair. */
export function replyTo(call: string): string {
  return call.split(">")[0] ?? call;
}

/** Whether the conversation is of a pair of other stations. */
export function isOverheard(call: string): boolean {
  return call.includes(">");
}

/** The sender and the addressee of an overheard pair ("OH2AAA>OH2BBB"); null for a conversation. */
export function overheardPair(call: string): [string, string] | null {
  const at = call.indexOf(">");
  return at < 0 ? null : [call.slice(0, at), call.slice(at + 1)];
}

/** A conversation as its row and its thread name it: the call, or the pair of an overheard one with room round the arrow, "OH2AAA > OH2BBB". */
export function conversationName(call: string): string {
  return call.replace(">", " > ");
}

const QUERY_TEXT: Record<string, QueryKind> = { "?APRSP": "position", "?APRSS": "status", "?APRSD": "heard", "?APRST": "trace" };

/** The query a row of the conversation is the note of: a message of ours with no message id whose text is one of the four queries (what the menu of the Stations table sends: once, with no id, so that no ack is waited for); null for any other message. The thread shows such a row as a grey line, "You asked for its status", not as a bubble. */
export function queryKind(row: Pick<MessageRow, "direction" | "msg_id" | "text" | "state">): QueryKind | null {
  return row.direction === "out" && row.msg_id === null && row.state !== "overheard" ? (QUERY_TEXT[row.text] ?? null) : null;
}

/** The note of a query in words: "You asked for its status". */
export function askedText(kind: QueryKind): string {
  return t(`messages.asked.${kind}`);
}

/** How many bytes the text takes in a message (UTF-8). */
export function textBytes(text: string): number {
  return encoder.encode(text).length;
}

/** How many bytes more the text may have; negative when it is too long. */
export function bytesLeft(text: string): number {
  return LIMITS.message.textMax - textBytes(text);
}

/** The conversations, the one with the newest message first; the email gateway's is not among them. `readUpTo(call)` is the highest message id the user has seen in the conversation. */
export function conversations(rows: Iterable<MessageRow>, readUpTo: (call: string) => number, showOverheard = false): Conversation[] {
  const byCall = new Map<string, Conversation>();
  for (const row of rows) {
    if (row.state === "overheard" && !showOverheard) continue;
    const call = peerOf(row);
    if (call === EMAIL_GATEWAY) continue;
    const found = byCall.get(call);
    const unread = isUnread(row, readUpTo(call)) ? 1 : 0;
    if (found === undefined) {
      byCall.set(call, { call, last: row, count: 1, unread, overheard: row.state === "overheard" });
      continue;
    }
    found.count++;
    found.unread += unread;
    if (isNewer(row, found.last)) found.last = row;
  }
  return [...byCall.values()].sort((a, b) => (isNewer(a.last, b.last) ? -1 : 1));
}

/** Whether the message came in after the newest one the user has seen (`readUpTo`, a message id). */
function isUnread(row: MessageRow, readUpTo: number): boolean {
  return row.state === "received" && row.id > readUpTo;
}

/** How many messages of the thread came in after the newest one the user has seen. */
export function threadUnread(thread: readonly MessageRow[], readUpTo: number): number {
  return thread.filter((row) => isUnread(row, readUpTo)).length;
}

function isNewer(a: MessageRow, b: MessageRow): boolean {
  return a.at === b.at ? a.id > b.id : a.at > b.at;
}

export function unreadTotal(list: readonly Conversation[]): number {
  return list.reduce((sum, c) => sum + c.unread, 0);
}

/** The messages with one station, the oldest first. */
export function threadOf(rows: Iterable<MessageRow>, call: string): MessageRow[] {
  return [...rows].filter((r) => peerOf(r) === call).sort((a, b) => a.id - b.id);
}

/** The highest id among the messages that were sent to us; 0 for none. */
export function newestIncomingId(rows: readonly MessageRow[]): number {
  return rows.reduce((most, r) => (r.state === "received" && r.id > most ? r.id : most), 0);
}

/** Which attempt a message that is being sent is at, of how many it was given when it was sent: "attempt 3 of 6". */
export function attemptText(row: MessageRow): string {
  return t("messages.attempt", { attempt: row.attempts, max: row.attempts_max });
}

/** The state of a message in words, with its attempts. Nothing for a message that came in. */
export function stateText(row: MessageRow): string {
  const n = row.attempts;
  switch (row.state) {
    case "received":
      return "";
    case "overheard":
      return t("messages.state.overheard", { call: row.to_call });
    case "queued":
      return t("messages.state.queued");
    case "sending":
      return n === 0 ? t("messages.state.waiting") : t("messages.state.sending", { attempt: n, max: row.attempts_max });
    case "acked":
      return t("messages.state.acked", { n });
    case "rejected":
      return t("messages.state.rejected");
    case "failed":
      return t("messages.state.failed", { n });
    case "unconfirmed":
      return t("messages.state.unconfirmed", { n });
    case "cancelled":
      return t("messages.state.cancelled", { n });
  }
}

/** A message of ours that did not get through can be sent again. */
export function canRetry(row: MessageRow): boolean {
  return row.direction === "out" && (row.state === "failed" || row.state === "unconfirmed" || row.state === "rejected" || row.state === "cancelled");
}

/** A message of ours that is no longer being sent and was never acked (failed, unconfirmed, refused or cancelled) can be deleted from the conversation. */
export function canDelete(row: MessageRow): boolean {
  return canRetry(row);
}

/** A message of ours that is being sent, or waits for the one before it to the same station (queued), can be stopped. */
export function canCancel(row: MessageRow): boolean {
  return row.direction === "out" && (row.state === "sending" || row.state === "queued");
}

/** The path a message to the station goes by: its own when it has one (empty is direct), else the beacon's. `own` says which. */
export function effectivePath(paths: ReadonlyMap<string, string>, fallback: string, call: string): { text: string; own: boolean } {
  const own = paths.get(normalizeCall(call));
  return own === undefined ? { text: fallback, own: false } : { text: own, own: true };
}

type MarkKind = "clock" | "check" | "hollow" | "cross" | "dash";

interface Mark {
  kind: MarkKind;
  /** what hovering over the mark says */
  title: string;
}

/** The small mark on a message of ours: a clock while it is being sent (the title says which attempt) or waits for the message before it to the station (queued), a check once acked (the title has the time of the ack), a hollow check when its attempts were used up with no ack and none was expected (the station was given 1 or 2), a cross when it failed or was rejected, a dash when
 * it was cancelled. None for a message that came in or was overheard: it has its time only. */
export function markOf(row: MessageRow): Mark | null {
  if (row.direction !== "out") return null;
  switch (row.state) {
    case "queued":
      return { kind: "clock", title: t("messages.state.queued") };
    case "sending":
      return { kind: "clock", title: row.attempts === 0 ? t("messages.state.waiting") : attemptText(row) };
    case "acked":
      return { kind: "check", title: row.acked_at === null ? t("messages.mark.acked") : t("messages.mark.acked_at", { time: dateTimeText(row.acked_at) }) };
    case "rejected":
    case "failed":
      return { kind: "cross", title: row.state === "failed" ? t("messages.mark.failed") : t("messages.state.rejected") };
    case "unconfirmed":
      return { kind: "hollow", title: t("messages.mark.no_ack_expected") };
    case "cancelled":
      return { kind: "dash", title: t("messages.mark.cancelled") };
    default:
      return null;
  }
}

/** Whether the conversation is shown as one with something new in it: it has messages not seen, and it is not the one that is open. */
export function isHighlighted(unread: number, call: string, open: string | null): boolean {
  return unread > 0 && call !== open;
}
