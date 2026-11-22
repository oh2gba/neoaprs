// The calls of one message to several stations (a group, opened from the map's station cards:
// composables/useMessagesView.ts `openGroup`): which calls may be recipients, who a text goes
// to, and whether Send is on. Each recipient gets an ordinary message of its own (its own id,
// acknowledgement, attempts and conversation); the daemon spaces them on the air.
import { normalizeCall, validName } from "@/lib/calls";
import { bytesLeft, isGateway, isPrintable } from "@/lib/messages";
import { LIMITS } from "@/protocol/lists";

/**
 * Whether a call may be added as a recipient: a station's name (a call or a name APRS-IS
 * allows), not the email gateway and not one already there.
 */
export function addable(call: string, chosen: readonly string[]): boolean {
  return validName(call) && !isGateway(call) && !chosen.includes(normalizeCall(call));
}

/**
 * The calls the message goes to: those picked, then the one typed in the To box when it is a name
 * of its own.
 */
export function recipientsOf(chosen: readonly string[], typed: string): string[] {
  return addable(typed, chosen) ? [...chosen, normalizeCall(typed)] : [...chosen];
}

/**
 * Why the daemon would refuse the characters of a message's text (its rule is
 * neoaprs/message.py `check_text`; this is the page's one copy): a character the format has no
 * place for (LIMITS.message.forbidden), then a non-ASCII one, then a control character. Returns
 * the code and values of the refusal, null for a text it carries.
 */
export function textRefusal(text: string): { code: string; params: { chars: string } } | null {
  const bad = [...LIMITS.message.forbidden].filter((c) => text.includes(c));
  if (bad.length > 0) return { code: "message.forbidden", params: { chars: bad.join(" ") } };
  if (isPrintable(text)) return null;
  if ([...text].some((c) => c > "\x7f"))
    return { code: "message.not_ascii", params: { chars: [...new Set([...text].filter((c) => c > "\x7f" && !/[\p{C}\p{Z}]/u.test(c)))].join("") } };
  return { code: "message.control", params: { chars: "" } };
}

/**
 * Whether Send is on: the TNC is connected, there is a recipient, what is typed in the To box
 * (if anything) is a station's name, and the text is there, fits and has only characters a
 * message carries.
 */
export function canSendAll(connected: boolean, chosen: readonly string[], typed: string, text: string): boolean {
  const typedOk = typed.trim() === "" || (validName(typed) && !isGateway(typed));
  return connected && typedOk && recipientsOf(chosen, typed).length > 0 && text.trim() !== "" && bytesLeft(text) >= 0 && textRefusal(text) === null;
}
