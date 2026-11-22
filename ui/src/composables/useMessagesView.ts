// The Messages tab state: the conversations, whether overheard messages are listed, the group
// compose (`group`, `openGroup`), and the ways to the tab (a card's Message button, the header
// mail, a sent message, a deleted conversation).
import { ref, watch, type Ref } from "vue";
import { useViewing, type Panel } from "@/composables/usePanel";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useConversations } from "@/composables/useConversations";
import { normalizeCall } from "@/lib/calls";
import { isGateway } from "@/lib/messages";
import { addable } from "@/lib/recipients";
import type { Command, MessageRow } from "@/protocol/protocol";

export function useMessagesView(
  messages: ReadonlyMap<string, MessageRow>,
  panel: Panel,
  send: (command: Command) => boolean,
  loaded?: Readonly<Ref<boolean>>,
) {
  const viewing = useViewing(panel, "messages");
  const showOverheard = usePersistedFlag("overheard", ["on", "off"], false);
  const talk = useConversations(messages, viewing, showOverheard, loaded);
  /** The calls of the open group compose, null if none; it excludes an open conversation. */
  const group = ref<string[] | null>(null);

  watch(talk.selected, (call) => {
    if (call !== null) group.value = null;
  });

  /**
   * Open the group compose for `calls`. The open conversation is left, and an invalid call, the
   * email gateway or a duplicate is dropped; with none left nothing opens.
   */
  function openGroup(calls: readonly string[]): void {
    const list = calls.reduce<string[]>(
      (kept, call) => (addable(call, kept) ? [...kept, normalizeCall(call)] : kept),
      [],
    );
    if (list.length === 0) return;
    talk.selected.value = null;
    group.value = list;
    panel.show("messages");
  }

  /** Open the Messages tab on that station (the Email tab for the email gateway). */
  function writeTo(call: string): void {
    if (isGateway(call)) {
      panel.show("email");
      return;
    }
    talk.selected.value = call;
    panel.show("messages");
  }

  /** Open the newest conversation with something unseen, unless the open one has. */
  function openMessages(): void {
    const open = talk.list.value.find((c) => c.call === talk.selected.value);
    const fresh = talk.list.value.find((c) => c.unread > 0);
    if (fresh !== undefined && (open === undefined || open.unread === 0)) talk.selected.value = fresh.call;
    panel.show("messages");
  }

  function deleteConversation(call: string): void {
    if (send({ cmd: "conversation_delete", call }) && talk.selected.value === call) talk.selected.value = null;
  }

  function deleteOverheard(from: string, to: string): void {
    if (send({ cmd: "overheard_delete", from_call: from, to_call: to }) && talk.selected.value === `${from}>${to}`)
      talk.selected.value = null;
  }

  function sendMessage(to: string, text: string, locked = false): void {
    if (send(locked ? { cmd: "send_message", to, text, locked: true } : { cmd: "send_message", to, text }))
      talk.selected.value = to;
  }

  /** Send the same text to several stations, one message each, and close the group compose. */
  function sendMessages(to: readonly string[], text: string): void {
    for (const call of to) send({ cmd: "send_message", to: call, text });
  }

  return {
    ...talk,
    group,
    openGroup,
    showOverheard,
    writeTo,
    openMessages,
    deleteConversation,
    deleteOverheard,
    sendMessage,
    sendMessages,
  };
}
