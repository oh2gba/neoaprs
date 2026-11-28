// The lines put on APRS-IS that the Internet box lists (components/IgateSent.vue): what the page
// keeps of them as the daemon tells them (`igate_sent`).
import type { IgateSentLine, IgateSentMessage } from "@/protocol/protocol";

/** As many as the daemon keeps (neoaprs/services/igate.py SENT_KEPT). */
export const SENT_KEPT = 200;

/** The list after a message: told whole it replaces the list, else its lines are added at the end. */
export function sentAfter(held: readonly IgateSentLine[], message: IgateSentMessage): readonly IgateSentLine[] {
  return message.whole ? message.lines : [...held, ...message.lines].slice(-SENT_KEPT);
}
