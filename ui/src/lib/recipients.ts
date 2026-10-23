// The calls of one message to several stations (a group, opened from the map's station cards: composables/useMessagesView.ts `openGroup`): which calls may be recipients, who a text goes to, and whether Send is on. Each recipient gets an ordinary message of its
// own (its own id, acknowledgement, attempts and conversation); the daemon spaces them on the air.
import { normalizeCall, validCall } from "@/lib/calls";
import { bytesLeft, isGateway } from "@/lib/messages";

/** Whether a call may be added as a recipient: a call, not the email gateway and not one that is there already. */
export function addable(call: string, chosen: readonly string[]): boolean {
  return validCall(call) && !isGateway(call) && !chosen.includes(normalizeCall(call));
}

/** The calls the message goes to: those picked, then the one typed in the To box when it is a call of its own. */
export function recipientsOf(chosen: readonly string[], typed: string): string[] {
  return addable(typed, chosen) ? [...chosen, normalizeCall(typed)] : [...chosen];
}

/** Whether Send is on: the TNC is connected, there is a recipient, what is typed in the To box (if anything) is a call, and the text is there and fits. */
export function canSendAll(connected: boolean, chosen: readonly string[], typed: string, text: string): boolean {
  const typedOk = typed.trim() === "" || (validCall(typed) && !isGateway(typed));
  return connected && typedOk && recipientsOf(chosen, typed).length > 0 && text.trim() !== "" && bytesLeft(text) >= 0;
}
