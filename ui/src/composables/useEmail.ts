// The Email tab: the thread with the gateway EMAIL-2, its unseen count (only while the tab is
// shown), the addressees used before and the messages it sends: mail, and `get` (Check email).
import { computed, shallowRef, watch, type Ref } from "vue";
import { useAddressBook } from "@/composables/useAddressBook";
import { useReadMarks } from "@/composables/useConversations";
import { useViewing, type Panel } from "@/composables/usePanel";
import { GET_HELD, emailLine } from "@/lib/email";
import { seenAtStart } from "@/lib/firststart";
import { EMAIL_GATEWAY, newestIncomingId, threadOf, threadUnread } from "@/lib/messages";
import type { Command, MessageRow } from "@/protocol/protocol";

/** `loaded`: the daemon sent all messages (in a window with a new store, they count as seen). */
export function useEmail(messages: ReadonlyMap<string, MessageRow>, panel: Panel, send: (command: Command) => boolean, loaded?: Readonly<Ref<boolean>>) {
  const viewing = useViewing(panel, "email");
  const marks = useReadMarks();
  const book = useAddressBook();
  const thread = computed(() => threadOf(messages.values(), EMAIL_GATEWAY));
  const unread = computed(() => threadUnread(thread.value, marks.readUpTo(EMAIL_GATEWAY)));
  watch(
    thread,
    (now) => {
      if (now.length > 0) marks.settle(EMAIL_GATEWAY, newestIncomingId(now));
    },
    { immediate: true },
  );

  // Rows after `freshAfter` show as new until the tab is closed; the mark is what was seen when the
  // tab last came on show.
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
  if (loaded)
    seenAtStart(loaded, () => {
      marks.mark(EMAIL_GATEWAY, newestIncomingId(thread.value));
      freshAfter.value = marks.readUpTo(EMAIL_GATEWAY);
    });

  const toGateway = (text: string): boolean => send({ cmd: "send_message", to: EMAIL_GATEWAY, text });

  function viaGateway(to: string | null, line: string): void {
    if (toGateway(line) && to !== null) book.remember(to);
  }

  const sendMail = (to: string, text: string): void => viaGateway(to, emailLine(to, text));

  const checkMail = (): void => viaGateway(null, GET_HELD);

  /** Delete a row (a mail still being sent is cancelled first). */
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
