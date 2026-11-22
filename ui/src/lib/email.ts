// The Email tab's rules (the APRS email gateway, aprs-is.net/Email.aspx): a message to EMAIL-2 is
// the addressee (an email address), a space and the text, at most as many UTF-8 bytes as a message
// may have; `get` asks for the mail the gateway kept; used addressees are kept, newest first. The
// gateway's shortcuts (`name address`, `name L`, `name R`) are not used. The daemon sends it as an
// ordinary message: the page only stops what the gateway would refuse and reports honestly what
// became of a mail (acks reach this station only through an iGate). The address list is kept by
// composables/useAddressBook.ts.
import { t } from "@/i18n";
import { markOf, textBytes } from "@/lib/messages";
import { textRefusal } from "@/lib/recipients";
import { LIMITS } from "@/protocol/lists";
import type { MessageRow } from "@/protocol/protocol";

/** What is sent to the gateway to hand over the mail it holds (Check email). */
export const GET_HELD = "get";
/** How many addressees are kept. */
export const ADDRESSES_KEPT = 12;

/** Whether a message text to the gateway is the `get` of Check email. */
export function isCheck(text: string): boolean {
  return text.trim().toLowerCase() === GET_HELD;
}

/**
 * Whether a `get` of ours is still being sent: Check email waits for it so the gateway is not asked
 * twice.
 */
export function checkingMail(thread: readonly MessageRow[]): boolean {
  return thread.some((row) => row.direction === "out" && row.state === "sending" && isCheck(row.text));
}

export function emailLine(to: string, text: string): string {
  return `${to.trim()} ${text}`;
}

/**
 * How many bytes the line may still have; negative when too long. The addressee and the space count
 * with the text.
 */
export function emailBytesLeft(to: string, text: string): number {
  return LIMITS.message.textMax - textBytes(emailLine(to, text));
}

/**
 * Whether Send is on: the TNC is connected, there is an addressee (one word) and a text, and the
 * line fits with only characters a message carries (lib/recipients.ts `textRefusal`).
 */
export function canSendEmail(connected: boolean, to: string, text: string): boolean {
  const addressee = to.trim();
  return (
    connected &&
    addressee !== "" &&
    !/\s/.test(addressee) &&
    text.trim() !== "" &&
    emailBytesLeft(to, text) >= 0 &&
    textRefusal(emailLine(to, text)) === null
  );
}

/**
 * Whether a message of ours to the gateway used its attempts without an ack. Not known to have
 * failed: acks need an iGate in reach.
 */
export function isNotConfirmed(row: MessageRow): boolean {
  return row.direction === "out" && (row.state === "failed" || row.state === "unconfirmed");
}

/**
 * The mark of a message to the gateway: the hollow check, never the cross, for one sent and not
 * confirmed.
 */
export function mailMarkOf(row: MessageRow): ReturnType<typeof markOf> {
  return isNotConfirmed(row) ? { kind: "hollow", title: t("email.not_confirmed") } : markOf(row);
}

/**
 * The addressees with `to` first (the same address in other letters is not listed twice), at most
 * ADDRESSES_KEPT.
 */
export function rememberAddress(list: readonly string[], to: string): string[] {
  const name = to.trim();
  if (name === "") return [...list];
  return [name, ...list.filter((a) => a.toLowerCase() !== name.toLowerCase())].slice(0, ADDRESSES_KEPT);
}

export function forgetAddress(list: readonly string[], name: string): string[] {
  return list.filter((a) => a !== name);
}

/** The addressees as stored (a JSON list of texts); anything else is no addressees. */
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
