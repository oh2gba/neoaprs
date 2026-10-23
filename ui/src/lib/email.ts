// The Email tab's rules (the APRS email gateway, aprs-is.net/Email.aspx): a message to EMAIL-2 has the addressee (an address, or the name of a shortcut), a space and the text, 67 bytes of UTF-8 in all; a shortcut
// is made by sending `name address`; the gateway's own commands (`name L`, `name R`, `get`) are messages to it too; and the addressees used before are kept, the newest first. The daemon sends it all as an ordinary
// message: the page only keeps the user from sending what the gateway would refuse, and says honestly what became of a mail (its acks reach this station only through an iGate). Where the list is kept (the browser)
// is composables/useAddressBook.ts.
import { markOf, stateText, textBytes } from "@/lib/messages";
import { MESSAGE_TEXT_MAX } from "@/protocol/lists";
import type { MessageRow } from "@/protocol/protocol";

/** What the gateway is sent to hand over the mail it holds for the station. */
export const GET_HELD = "get";
/** How many addressees are kept. */
export const ADDRESSES_KEPT = 12;

/** The text of the message to the gateway: the addressee, a space, the text. */
export function emailLine(to: string, text: string): string {
  return `${to.trim()} ${text}`;
}

/** How many bytes the line may still have; negative when it is too long. The addressee and the space count with the text. */
export function emailBytesLeft(to: string, text: string): number {
  return MESSAGE_TEXT_MAX - textBytes(emailLine(to, text));
}

/** Whether Send is on: the TNC is connected, there is an addressee (one word) and a text, and the line fits. */
export function canSendEmail(connected: boolean, to: string, text: string): boolean {
  const addressee = to.trim();
  return connected && addressee !== "" && !/\s/.test(addressee) && text.trim() !== "" && emailBytesLeft(to, text) >= 0;
}

/** A shortcut is a name of letters and digits. */
export function validShortcut(name: string): boolean {
  return /^[A-Za-z0-9]+$/.test(name.trim());
}

/** Whether the text is one email address (something, an @, something, no blank). */
export function validAddress(address: string): boolean {
  return /^[^\s@]+@[^\s@]+$/.test(address.trim());
}

/** What the gateway is sent to have it email the list of the station's shortcuts to this shortcut's address. */
export function listShortcuts(name: string): string {
  return `${name.trim()} L`;
}

/** What the gateway is sent to remove a shortcut. */
export function removeShortcut(name: string): string {
  return `${name.trim()} R`;
}

const NOT_CONFIRMED = "sent, not confirmed: the gateway's ack reaches you only through an iGate, so the mail may well have gone through";

/** Whether a message of ours to the gateway used its attempts without an ack: it is not known to have failed, since the gateway's acks need an iGate in reach of our radio. */
export function isNotConfirmed(row: MessageRow): boolean {
  return row.direction === "out" && (row.state === "failed" || row.state === "unconfirmed");
}

/** The state of a message to the gateway in words: "sent twice, not confirmed" where the Messages tab would say failed or "no ack". */
export function mailStateText(row: MessageRow): string {
  if (!isNotConfirmed(row)) return stateText(row);
  return `sent ${row.attempts === 1 ? "once" : row.attempts === 2 ? "twice" : `${row.attempts} times`}, not confirmed`;
}

/** The mark of a message to the gateway: the hollow check, never the cross, for one that was sent and not confirmed. */
export function mailMarkOf(row: MessageRow): ReturnType<typeof markOf> {
  return isNotConfirmed(row) ? { kind: "hollow", title: NOT_CONFIRMED } : markOf(row);
}

/** The addressees with `to` first (the same one typed in other letters is not listed twice); at most ADDRESSES_KEPT. Nothing for an empty one. */
export function rememberAddress(list: readonly string[], to: string): string[] {
  const name = to.trim();
  if (name === "") return [...list];
  return [name, ...list.filter((a) => a.toLowerCase() !== name.toLowerCase())].slice(0, ADDRESSES_KEPT);
}

/** The addressees without `name`. */
export function forgetAddress(list: readonly string[], name: string): string[] {
  return list.filter((a) => a !== name);
}

/** The addressees as they were stored (a JSON list of texts); anything else is no addressees. */
export function parseAddresses(stored: string | null): string[] {
  if (stored === null) return [];
  try {
    const value: unknown = JSON.parse(stored);
    if (!Array.isArray(value)) return [];
    return value.filter((a): a is string => typeof a === "string" && a.trim() !== "").slice(0, ADDRESSES_KEPT);
  } catch {
    return [];
  }
}
