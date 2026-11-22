// The Email tab's list: every message to and from the gateway EMAIL-2 as one row of a mail list.
// A message of ours is a mail ("To jane@example.com") or the `get` of Check email, with its state
// in words. What the gateway sent is "From EMAIL-2" (its replies) or, when its text starts with an
// email address, the mail it forwards. The gateway's acks are no rows: the daemon uses them to
// settle the mail they belong to.
import { monthShort, t } from "@/i18n";
import { isCheck } from "@/lib/email";
import { dateTimeText, pad2 } from "@/lib/format";
import type { MessageRow } from "@/protocol/protocol";

type MailKind = "mail" | "get" | "reply" | "forwarded";

export interface MailItem {
  row: MessageRow;
  kind: MailKind;
  /** the first line: "To jane@example.com", "From EMAIL-2", "Checked email" */
  title: string;
  /** the text under it (empty for a command, which says all in its title) */
  text: string;
  /** the line as sent or received, for the text's title */
  line: string;
  /** the email address the mail is to or from; empty for the gateway's own reply and the check */
  address: string;
}

export interface MailState {
  /** the words: "Sending (1 of 2)", "Delivered", "Not confirmed", "Rejected", "Cancelled" */
  word: string;
  /** the colour of the words: ok (plain text), bad (orange) or plain */
  tone: "ok" | "bad" | "plain";
}

/** A message of ours: the `get` of Check email, else a mail to the first word. */
function outgoing(row: MessageRow): MailItem {
  const line = row.text.trim();
  if (isCheck(line)) return { row, kind: "get", title: t("email.checked"), text: "", line, address: "" };
  const split = /^(\S+)\s+(.+)$/.exec(line);
  const to = split?.[1];
  const text = split?.[2]?.trim();
  if (to === undefined || text === undefined)
    return { row, kind: "mail", title: t("email.to", { address: line }), text: "", line, address: line };
  return { row, kind: "mail", title: t("email.to", { address: to }), text, line, address: to };
}

/**
 * What came in from the gateway: text starting with an email address (`<jane@example.com>` and
 * `jane@example.com:` too) is a forwarded mail from it; else the gateway's own reply.
 */
function incoming(row: MessageRow): MailItem {
  const line = row.text.trim();
  const forwarded = /^<?([^\s@<>]+@[^\s@<>:]+?)>?:?\s+(.+)$/.exec(line);
  const from = forwarded?.[1];
  const text = forwarded?.[2];
  if (from !== undefined && text !== undefined)
    return { row, kind: "forwarded", title: t("email.from", { address: from }), text, line, address: from };
  return { row, kind: "reply", title: t("email.from", { address: row.from_call }), text: line, line, address: "" };
}

/** The list row for a message to or from the gateway. */
export function mailItem(row: MessageRow): MailItem {
  return row.direction === "in" ? incoming(row) : outgoing(row);
}

/** The rows, oldest first, so the newest is next to the form (as in the Messages tab). */
export function mailItems(thread: readonly MessageRow[]): MailItem[] {
  return [...thread].sort((a, b) => a.id - b.id).map(mailItem);
}

/**
 * The state of a message of ours in words. A mail whose attempts ran out without an ack is "Not
 * confirmed", never failed (acks reach us only through an iGate). Null for an incoming message.
 */
export function mailState(row: MessageRow): MailState | null {
  if (row.direction !== "out") return null;
  switch (row.state) {
    case "sending":
      return {
        word:
          row.attempts === 0
            ? t("email.state.waiting")
            : t("email.state.sending", { attempt: row.attempts, max: row.attempts_max }),
        tone: "plain",
      };
    case "acked":
      return { word: t("email.state.delivered"), tone: "ok" };
    case "rejected":
      return { word: t("email.state.rejected"), tone: "bad" };
    case "cancelled":
      return { word: t("email.state.cancelled"), tone: "plain" };
    case "failed":
      if (row.failure === "too_long_for_radio") return { word: t("email.state.too_long_for_radio"), tone: "bad" };
      return { word: t("email.state.unconfirmed"), tone: "plain" };
    case "unconfirmed":
      return { word: t("email.state.unconfirmed"), tone: "plain" };
    default:
      return null;
  }
}

/** A short time: "12:41" today, "21 Oct 12:41" before; the full time is its title. */
export function mailTime(iso: string, nowMs: number): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return dateTimeText(iso);
  const clock = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  return d.toDateString() === new Date(nowMs).toDateString()
    ? clock
    : t("email.date_time", { day: d.getDate(), month: monthShort(d), time: clock });
}
