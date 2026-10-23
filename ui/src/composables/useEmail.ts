// The Email tab as the page runs it: the thread with the gateway EMAIL-2, how many of its messages are not seen (only while the Email tab is on show, the panel open and the page visible, lib/unread.ts),
// the addressees used before, and the messages the tab sends: mail, and `get` (Check email). The daemon sends a message to the gateway twice at most, the gateway's acks reaching a station only through an iGate.
import { computed, shallowRef, watch } from "vue";
import { useAddressBook } from "@/composables/useAddressBook";
import { useReadMarks } from "@/composables/useConversations";
import type { Panel } from "@/composables/usePanel";
import { useVisible } from "@/composables/useVisible";
import { GET_HELD, emailLine } from "@/lib/email";
import { EMAIL_GATEWAY, newestIncomingId, threadOf, threadUnread } from "@/lib/messages";
import { isViewingTab } from "@/lib/unread";
import type { Command, MessageRow } from "@/protocol/protocol";

export function useEmail(messages: ReadonlyMap<string, MessageRow>, panel: Panel, send: (command: Command) => boolean) {
  const visible = useVisible();
  const viewing = computed(() => isViewingTab({ tab: panel.tab.value, collapsed: panel.collapsed.value, visible: visible.value }, "email"));
  const marks = useReadMarks();
  const book = useAddressBook();
  const thread = computed(() => threadOf(messages.values(), EMAIL_GATEWAY));
  const unread = computed(() => threadUnread(thread.value, marks.readUpTo(EMAIL_GATEWAY)));

  // The rows that came in after `freshAfter` are shown as new (bold): the mark of what was seen when the tab last came on show, so that they stay new for as long as the tab is open and are not new the next time.
  const freshAfter = shallowRef(marks.readUpTo(EMAIL_GATEWAY));
  watch(
    [viewing, () => newestIncomingId(thread.value)],
    ([showing, newest], [wasShowing]) => {
      if (!showing) return;
      if (!wasShowing) freshAfter.value = marks.readUpTo(EMAIL_GATEWAY);
      marks.mark(EMAIL_GATEWAY, newest);
    },
    { immediate: true },
  );

  const toGateway = (text: string): boolean => send({ cmd: "send_message", to: EMAIL_GATEWAY, text });

  /** Sends the line to the gateway, and remembers `to` (when there is one) once it is sent. */
  function viaGateway(to: string | null, line: string): void {
    if (toGateway(line) && to !== null) book.remember(to);
  }

  /** Sends mail: the line "to text" to the gateway. */
  const sendMail = (to: string, text: string): void => viaGateway(to, emailLine(to, text));

  /** Check email: the gateway sends again the mail it kept for the station. */
  const checkMail = (): void => viaGateway(null, GET_HELD);

  /** Takes a row out of the list (the daemon deletes it; a mail still being sent is cancelled first). */
  const remove = (id: number): void => void send({ cmd: "message_delete", id });

  return {
    thread,
    unread,
    freshAfter,
    remove,
    addresses: book.addresses,
    forget: book.forget,
    sendMail,
    checkMail,
  };
}
