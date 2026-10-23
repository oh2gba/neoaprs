// The Email tab's list: every message to and from the gateway EMAIL-2 as one row of a mail list (not a conversation). A message of ours is a mail ("To jane@example.com" and its text) or one of the gateway's
// commands in words ("Fetch held mail", "Shortcut 'me' → jane@example.com"), with its state in words: Sending (1 of 2), Delivered, Not confirmed, Rejected. What the gateway sent is "From EMAIL-2" (its
// replies to a command) or, when its text starts with an email address, the mail it forwards, "From jane@example.com". The gateway's acks are no rows: the daemon uses them to settle the mail they belong to.
import { GET_HELD, validAddress } from "@/lib/email";
import { dateTimeText } from "@/lib/format";
import type { MessageRow } from "@/protocol/protocol";

type MailKind = "mail" | "shortcut" | "list" | "remove" | "get" | "reply" | "forwarded";

export interface MailItem {
  row: MessageRow;
  kind: MailKind;
  /** the first line: "To jane@example.com", "From EMAIL-2", "Fetch held mail" */
  title: string;
  /** the text under it (empty for a command, which says all in its title) */
  text: string;
  /** the line as it was sent or came in, for the title of the text */
  line: string;
}

export interface MailState {
  /** the words: "Sending (1 of 2)", "Delivered", "Not confirmed", "Rejected", "Cancelled" */
  word: string;
  /** green, red or plain, for the colour of the words */
  tone: "ok" | "bad" | "plain";
}

/** A message of ours, read: the gateway's commands (`get`, `name address`, `name L`, `name R`) in words, anything else a mail to the first word. */
function outgoing(row: MessageRow): MailItem {
  const line = row.text.trim();
  const make = (kind: MailKind, title: string, text = ""): MailItem => ({ row, kind, title, text, line });
  if (line.toLowerCase() === GET_HELD) return make("get", "Fetch held mail");
  const split = /^(\S+)\s+(.+)$/.exec(line);
  const first = split?.[1];
  const rest = split?.[2]?.trim();
  if (first === undefined || rest === undefined) return make("mail", `To ${line}`);
  const named = !first.includes("@");
  if (named && rest === "L") return make("list", `Asked for the shortcut list (${first})`);
  if (named && rest === "R") return make("remove", `Remove shortcut '${first}'`);
  if (named && validAddress(rest)) return make("shortcut", `Shortcut '${first}' → ${rest}`);
  return make("mail", `To ${first}`, rest);
}

/** What came in from the gateway: its text starting with an email address and a blank (`<jane@example.com>` or `jane@example.com:` too) is mail it forwards, from that address; else it is the gateway's own reply. */
function incoming(row: MessageRow): MailItem {
  const line = row.text.trim();
  const forwarded = /^<?([^\s@<>]+@[^\s@<>:]+?)>?:?\s+(.+)$/.exec(line);
  const from = forwarded?.[1];
  const text = forwarded?.[2];
  if (from !== undefined && text !== undefined) return { row, kind: "forwarded", title: `From ${from}`, text, line };
  return { row, kind: "reply", title: `From ${row.from_call}`, text: line, line };
}

/** The row of the list for a message to or from the gateway. */
export function mailItem(row: MessageRow): MailItem {
  return row.direction === "in" ? incoming(row) : outgoing(row);
}

/** The rows of the list, the newest first. */
export function mailItems(thread: readonly MessageRow[]): MailItem[] {
  return [...thread].sort((a, b) => b.id - a.id).map(mailItem);
}

/** The state of a message of ours in words. A mail whose attempts ran out without an ack is "Not confirmed", never failed: the gateway's acks reach us only through an iGate. Null for a message that came in. */
export function mailState(row: MessageRow): MailState | null {
  if (row.direction !== "out") return null;
  switch (row.state) {
    case "sending":
      return { word: row.attempts === 0 ? "Waiting for the radio" : `Sending (${row.attempts} of ${row.attempts_max})`, tone: "plain" };
    case "acked":
      return { word: "Delivered", tone: "ok" };
    case "rejected":
      return { word: "Rejected", tone: "bad" };
    case "cancelled":
      return { word: "Cancelled", tone: "plain" };
    case "failed":
    case "unconfirmed":
      return { word: "Not confirmed", tone: "plain" };
    default:
      return null;
  }
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n: number): string => String(n).padStart(2, "0");

/** When a row is from, short: "12:41" today, "21 Oct 12:41" before; the full date and time is the title of it. */
export function mailTime(iso: string, nowMs: number): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return dateTimeText(iso);
  const clock = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return d.toDateString() === new Date(nowMs).toDateString() ? clock : `${d.getDate()} ${MONTHS[d.getMonth()]} ${clock}`;
}
