// The Email tab's rules (the APRS email gateway, aprs-is.net/Email.aspx): a message to EMAIL-2 has the addressee (an address, or the name of a shortcut), a space and the text, 67 bytes of UTF-8 in all; the
// gateway's own commands (`name L`, `name R`, `get`) are messages to it too; and the addressees used before are kept, the newest first. The daemon sends it all as an ordinary message: the page only keeps the
// user from sending what the gateway would refuse. Where the list is kept (the browser) is composables/useAddressBook.ts.
import { textBytes } from "@/lib/messages";
import { MESSAGE_TEXT_MAX } from "@/protocol/lists";

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

/** What the gateway is sent to have it email the list of the station's shortcuts to this shortcut's address. */
export function listShortcuts(name: string): string {
  return `${name.trim()} L`;
}

/** What the gateway is sent to remove a shortcut. */
export function removeShortcut(name: string): string {
  return `${name.trim()} R`;
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
