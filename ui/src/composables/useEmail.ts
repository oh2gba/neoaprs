// The Email tab as the page runs it: the thread with the gateway EMAIL-2, how many of its messages are not seen (only while the Email tab is on show, the panel open and the page visible, lib/unread.ts),
// the addressees used before, and the messages the tab sends: mail, a new shortcut, and the gateway's own commands. The gateway's acks reach this station only through an iGate, so the first time the tab sends anything and the
// gateway has no count of attempts of its own, the page gives it 2 (once: the browser remembers it, so that a count cleared on purpose stays cleared); the message waits for the daemon to say it has the count, because the
// daemon runs the two commands side by side and a message takes the count it finds when it is sent.
import { computed, onScopeDispose, watch, type Ref } from "vue";
import { useAddressBook } from "@/composables/useAddressBook";
import { useReadMarks } from "@/composables/useConversations";
import type { Panel } from "@/composables/usePanel";
import { useVisible } from "@/composables/useVisible";
import { GET_HELD, emailLine, listShortcuts, removeShortcut } from "@/lib/email";
import { EMAIL_GATEWAY, newestIncomingId, threadOf, threadUnread } from "@/lib/messages";
import { readStored, writeStored } from "@/lib/storage";
import { isViewingTab } from "@/lib/unread";
import type { Command, MessageRow } from "@/protocol/protocol";

/** How many attempts the gateway is given when the page sets it, and how long mail waits for the daemon to have said so. */
const EMAIL_ATTEMPTS = 2;
const SETTLE_MS = 3000;
const APPLIED_KEY = "emailattempts";

export function useEmail(
  messages: ReadonlyMap<string, MessageRow>,
  panel: Panel,
  send: (command: Command) => boolean,
  attempts: Ref<ReadonlyMap<string, number>>,
) {
  const visible = useVisible();
  const viewing = computed(() => isViewingTab({ tab: panel.tab.value, collapsed: panel.collapsed.value, visible: visible.value }, "email"));
  const marks = useReadMarks();
  const book = useAddressBook();
  const thread = computed(() => threadOf(messages.values(), EMAIL_GATEWAY));
  const unread = computed(() => threadUnread(thread.value, marks.readUpTo(EMAIL_GATEWAY)));

  watch(
    [viewing, () => newestIncomingId(thread.value)],
    ([showing, newest]) => {
      if (showing) marks.mark(EMAIL_GATEWAY, newest);
    },
    { immediate: true },
  );

  const toGateway = (text: string): boolean => send({ cmd: "send_message", to: EMAIL_GATEWAY, text });

  const held: { to: string | null; line: string }[] = []; // (messages waiting for the gateway's count of attempts; `to` is the addressee to remember, null for a command)
  let waiting: ReturnType<typeof setTimeout> | undefined;
  let applied = readStored(APPLIED_KEY) === "yes";

  function deliver(to: string | null, line: string): void {
    if (toGateway(line) && to !== null) book.remember(to);
  }

  function release(): void {
    clearTimeout(waiting);
    for (const mail of held.splice(0)) deliver(mail.to, mail.line);
  }

  watch(
    () => attempts.value.has(EMAIL_GATEWAY),
    (has) => {
      if (has) release();
    },
  );
  onScopeDispose(() => clearTimeout(waiting));

  function markApplied(): void {
    applied = true;
    writeStored(APPLIED_KEY, "yes");
  }

  /** Sends the line to the gateway, and remembers `to` once it is sent. The first time, with no count of attempts of the gateway's own, the page gives it one and sends the line when the daemon has it. */
  function viaGateway(to: string | null, line: string): void {
    if (held.length > 0) {
      held.push({ to, line });
      return;
    }
    if (attempts.value.has(EMAIL_GATEWAY)) markApplied();
    if (applied || !send({ cmd: "set_station_attempts", call: EMAIL_GATEWAY, attempts: EMAIL_ATTEMPTS })) {
      deliver(to, line);
      return;
    }
    markApplied();
    waiting = setTimeout(release, SETTLE_MS);
    held.push({ to, line });
  }

  /** Sends mail: the line "to text" to the gateway. */
  const sendMail = (to: string, text: string): void => viaGateway(to, emailLine(to, text));

  /** Makes a shortcut: the line "name address" (the name is remembered as an addressee, like the ones mail went to). */
  const registerShortcut = (name: string, address: string): void => viaGateway(name.trim(), emailLine(name, address));

  /** The gateway's three commands. */
  const listShortcutsOf = (name: string): void => viaGateway(null, listShortcuts(name));
  const removeShortcutNamed = (name: string): void => viaGateway(null, removeShortcut(name));
  const getHeld = (): void => viaGateway(null, GET_HELD);

  return {
    thread,
    unread,
    addresses: book.addresses,
    forget: book.forget,
    sendMail,
    registerShortcut,
    listShortcuts: listShortcutsOf,
    removeShortcut: removeShortcutNamed,
    getHeld,
  };
}
