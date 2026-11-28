// Messages of the topic `messages`: conversations (one per other station), a thread, unread counts
// and the compose-box rules (the call, the bytes a message may still have).
// Overheard messages (sent to another station) are no conversation of ours; with `showOverheard`
// each pair of stations is listed as one.
// The daemon checks all of this again; the page only stops the user sending what it would refuse.
// What a call or a path is lives in lib/calls.ts.
import { t } from "@/i18n";
import { normalizeCall } from "@/lib/calls";
import { dateTimeText } from "@/lib/format";
import { readingText } from "@/lib/signal";
import type { QueryKind } from "@/lib/stations";
import { LIMITS } from "@/protocol/lists";
import type { IgateState, MessageRow } from "@/protocol/protocol";

export interface Conversation {
  /** The other station. */
  call: string;
  /** The newest message of the conversation. */
  last: MessageRow;
  count: number;
  /** Messages that came in after the newest one the user has seen (never an overheard one). */
  unread: number;
  /** A pair of other stations, "OH2AAA>OH2BBB", whose messages we only heard. */
  overheard: boolean;
}

/** The APRS email gateway (aprs-is.net/Email.aspx); its messages belong to the Email tab. */
export const EMAIL_GATEWAY = LIMITS.message.gateway;

const encoder = new TextEncoder();

/** Whether the call, as typed, is the email gateway. */
export function isGateway(call: string): boolean {
  return normalizeCall(call) === EMAIL_GATEWAY;
}

/** Whether the call is one of the internet services (`LIMITS.message.services`), exactly. */
export function isInternetService(call: string): boolean {
  return LIMITS.message.services.some((service) => service === call.trim().toUpperCase());
}

/** Whether the Internet connection carries the messages to the internet services: Send what I hear is on and the
 * login is verified. */
export function internetCarries(igate: IgateState | null): boolean {
  return igate !== null && igate.gate && igate.state === "connected";
}

/** The other station of a message: the sender if it came in, else the addressee; "sender>addressee"
 * if overheard. */
export function peerOf(row: MessageRow): string {
  if (row.state === "overheard") return `${row.from_call}>${row.to_call}`;
  return row.direction === "in" ? row.from_call : row.to_call;
}

/** The call to write to from a conversation: the other station, or the sender of an overheard pair.
 */
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

/** A conversation as its row and thread name it: the call, or "OH2AAA > OH2BBB" for an overheard
 * pair. */
export function conversationName(call: string): string {
  return call.replaceAll(">", " > ");
}

const QUERY_TEXT: Record<string, QueryKind> = {
  "?APRSP": "position",
  "?APRSS": "status",
  "?APRSD": "heard",
  "?APRST": "trace",
  "?WX?": "weather",
};

/** The note for a row that is a query of ours: a message of ours with no id whose text begins with
 * "?"
 * (no ack is waited for), such as "You asked for its status"; null for any other message.
 * The thread shows such a row as a grey line, not a bubble. */
export function askedNote(row: Pick<MessageRow, "direction" | "msg_id" | "text" | "state">): string | null {
  if (row.direction !== "out" || row.msg_id !== null || row.state === "overheard" || !row.text.startsWith("?"))
    return null;
  const kind = QUERY_TEXT[row.text];
  return kind === undefined ? t("messages.asked.custom", { text: row.text }) : t(`messages.asked.${kind}`);
}

/** Whether the text is printable ASCII only (space to tilde), as everything the daemon sends on the
 * air must be. */
export function isPrintable(text: string): boolean {
  return /^[\x20-\x7e]*$/.test(text);
}

/** How many bytes the text takes in a message (UTF-8). */
export function textBytes(text: string): number {
  return encoder.encode(text).length;
}

/** How many bytes more the text may have; negative when it is too long. */
export function bytesLeft(text: string): number {
  return LIMITS.message.textMax - textBytes(text);
}

/** The conversations, newest message first; the email gateway's is not among them.
 * `readUpTo(call)` is the highest message id the user has seen in the conversation. */
export function conversations(
  rows: Iterable<MessageRow>,
  readUpTo: (call: string) => number,
  showOverheard = false,
): Conversation[] {
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

/** Whether the message came in after the newest one the user has seen (`readUpTo`, a message id).
 */
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

/** The messages with one station, oldest first. */
export function threadOf(rows: Iterable<MessageRow>, call: string): MessageRow[] {
  return [...rows].filter((r) => peerOf(r) === call).sort((a, b) => a.id - b.id);
}

/** The highest id among the messages sent to us; 0 for none. */
export function newestIncomingId(rows: readonly MessageRow[]): number {
  return rows.reduce((most, r) => (r.state === "received" && r.id > most ? r.id : most), 0);
}

/** The highest id among the messages sent to us, by sender. */
export function newestIncomingByCall(rows: Iterable<MessageRow>): Map<string, number> {
  const newest = new Map<string, number>();
  for (const row of rows) {
    if (row.state !== "received") continue;
    const call = peerOf(row);
    if (row.id > (newest.get(call) ?? 0)) newest.set(call, row.id);
  }
  return newest;
}

/** Which attempt a message being sent is at, of how many it was given: "attempt 3 of 6". */
export function attemptText(row: MessageRow): string {
  return t("messages.attempt", { attempt: row.attempts, max: row.attempts_max });
}

/** Why a failed message of ours failed: its reason if it has one, else that no answer came. */
export function failedText(row: MessageRow): string {
  return row.failure === "too_long_for_radio"
    ? t("messages.state.too_long_for_radio")
    : t("messages.state.failed", { n: row.attempts });
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
      return failedText(row);
    case "unconfirmed":
      return t("messages.state.unconfirmed", { n });
    case "cancelled":
      return t("messages.state.cancelled", { n });
  }
}

/** A message of ours that did not get through can be sent again. */
export function canRetry(row: MessageRow): boolean {
  return (
    row.direction === "out" &&
    (row.state === "failed" || row.state === "unconfirmed" || row.state === "rejected" || row.state === "cancelled")
  );
}

/** A message of ours that is no longer being sent and was never acked can be deleted. */
export function canDelete(row: MessageRow): boolean {
  return canRetry(row);
}

/** A message of ours that is being sent, or queued behind one to the same station, can be stopped.
 */
export function canCancel(row: MessageRow): boolean {
  return row.direction === "out" && (row.state === "sending" || row.state === "queued");
}

/** The path a message to the station goes by: its own if it has one (empty is direct), else the
 * beacon's. */
export function effectivePath(
  paths: ReadonlyMap<string, string>,
  fallback: string,
  call: string,
): { text: string; own: boolean } {
  const own = paths.get(normalizeCall(call));
  return own === undefined ? { text: fallback, own: false } : { text: own, own: true };
}

type MarkKind = "clock" | "check" | "hollow" | "cross" | "dash";

interface Mark {
  kind: MarkKind;
  /** What hovering over the mark says. */
  title: string;
}

/** The small mark on a message of ours: a clock while sending or queued, a check once acked, a
 * hollow
 * check when the attempts ran out with no ack expected, a cross when it failed or was rejected, a
 * dash
 * when cancelled. The title of a settled one adds the SNR the radio measured. None for a message
 * that came in or was overheard. */
export function markOf(row: MessageRow): Mark | null {
  const mark = markWithoutSignal(row);
  const signal = mark === null ? null : readingText(row);
  return mark === null || signal === null
    ? mark
    : { ...mark, title: t("messages.mark.with_signal", { mark: mark.title, signal }) };
}

/** The mark as `markOf` says it, with the SNR of the returned ack added to the title (null until
 * then). */
function markWithoutSignal(row: MessageRow): Mark | null {
  if (row.direction !== "out") return null;
  switch (row.state) {
    case "queued":
      return { kind: "clock", title: t("messages.state.queued") };
    case "sending":
      return { kind: "clock", title: row.attempts === 0 ? t("messages.state.waiting") : attemptText(row) };
    case "acked":
      return {
        kind: "check",
        title:
          row.acked_at === null
            ? t("messages.mark.acked")
            : t("messages.mark.acked_at", { time: dateTimeText(row.acked_at) }),
      };
    case "rejected":
    case "failed":
      return {
        kind: "cross",
        title: row.state === "failed" ? t("messages.mark.failed") : t("messages.state.rejected"),
      };
    case "unconfirmed":
      return { kind: "hollow", title: t("messages.mark.no_ack_expected") };
    case "cancelled":
      return { kind: "dash", title: t("messages.mark.cancelled") };
    default:
      return null;
  }
}

/** Whether the conversation has unseen messages and is not the one that is open. */
export function isHighlighted(unread: number, call: string, open: string | null): boolean {
  return unread > 0 && call !== open;
}
