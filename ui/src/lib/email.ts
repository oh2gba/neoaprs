// The Email tab's rules (the APRS email gateway, aprs-is.net/Email.aspx): a message to EMAIL-2 has the addressee (an email address), a space and the text, as many bytes of UTF-8 in all as a message may have; `get` asks it for the mail it kept; and the addressees used before are
// kept, the newest first. (The gateway's shortcuts, `name address`, `name L`, `name R`, are not used by the page.) The daemon sends it all as an ordinary
// message: the page only keeps the user from sending what the gateway would refuse, and says honestly what became of a mail (its acks reach this station only through an iGate). Where the list is kept (the browser)
// is composables/useAddressBook.ts.
import { t } from "@/i18n";
import { markOf, textBytes } from "@/lib/messages";
import { LIMITS } from "@/protocol/lists";
import type { MessageRow } from "@/protocol/protocol";

/** What the gateway is sent to hand over the mail it holds for the station (Check email). */
export const GET_HELD = "get";
/** How many addressees are kept. */
export const ADDRESSES_KEPT = 12;

/** Whether the text of a message to the gateway is the `get` of Check email. */
export function isCheck(text: string): boolean {
  return text.trim().toLowerCase() === GET_HELD;
}

/** Whether a `get` of ours is still being sent: Check email waits for it to settle, so the gateway is not asked twice. */
export function checkingMail(thread: readonly MessageRow[]): boolean {
  return thread.some((row) => row.direction === "out" && row.state === "sending" && isCheck(row.text));
}

/** The text of the message to the gateway: the addressee, a space, the text. */
export function emailLine(to: string, text: string): string {
  return `${to.trim()} ${text}`;
}

/** How many bytes the line may still have; negative when it is too long. The addressee and the space count with the text. */
export function emailBytesLeft(to: string, text: string): number {
  return LIMITS.message.textMax - textBytes(emailLine(to, text));
}

/** Whether Send is on: the TNC is connected, there is an addressee (one word) and a text, and the line fits. */
export function canSendEmail(connected: boolean, to: string, text: string): boolean {
  const addressee = to.trim();
  return connected && addressee !== "" && !/\s/.test(addressee) && text.trim() !== "" && emailBytesLeft(to, text) >= 0;
}

/** Whether a message of ours to the gateway used its attempts without an ack: it is not known to have failed, since the gateway's acks need an iGate in reach of our radio. */
export function isNotConfirmed(row: MessageRow): boolean {
  return row.direction === "out" && (row.state === "failed" || row.state === "unconfirmed");
}

/** The mark of a message to the gateway: the hollow check, never the cross, for one that was sent and not confirmed. */
export function mailMarkOf(row: MessageRow): ReturnType<typeof markOf> {
  return isNotConfirmed(row) ? { kind: "hollow", title: t("email.not_confirmed") } : markOf(row);
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
