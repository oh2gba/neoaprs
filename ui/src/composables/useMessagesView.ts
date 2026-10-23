// The Messages tab as the page runs it: the conversations (a message is seen only while the tab is in front of the user, lib/unread.ts), whether the overheard ones are listed (remembered), and the ways to the tab: the Message button of a station's card, the mail in the header, a message sent, a conversation deleted.
import { computed } from "vue";
import type { Panel } from "@/composables/usePanel";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useConversations } from "@/composables/useConversations";
import { useVisible } from "@/composables/useVisible";
import { isGateway } from "@/lib/messages";
import { isViewingTab } from "@/lib/unread";
import type { Command, MessageRow } from "@/protocol/protocol";

export function useMessagesView(messages: ReadonlyMap<string, MessageRow>, panel: Panel, send: (command: Command) => boolean) {
  const visible = useVisible();
  const viewing = computed(() => isViewingTab({ tab: panel.tab.value, collapsed: panel.collapsed.value, visible: visible.value }, "messages"));
  const showOverheard = usePersistedFlag("overheard", ["on", "off"], false);
  const talk = useConversations(messages, viewing, showOverheard);

  /** The "Message" button of a station's card: the Messages tab, open on that station (the Email tab for the email gateway, which has no conversation here). */
  function writeTo(call: string): void {
    if (isGateway(call)) {
      panel.show("email");
      return;
    }
    talk.selected.value = call;
    panel.show("messages");
  }

  /** The mail in the header: the Messages tab, on the newest conversation with something not seen unless the one open has. */
  function openMessages(): void {
    const open = talk.list.value.find((c) => c.call === talk.selected.value);
    const fresh = talk.list.value.find((c) => c.unread > 0);
    if (fresh !== undefined && (open === undefined || open.unread === 0)) talk.selected.value = fresh.call;
    panel.show("messages");
  }

  /** Deletes the whole conversation with a station; its thread closes if it was the open one. */
  function deleteConversation(call: string): void {
    if (send({ cmd: "conversation_delete", call }) && talk.selected.value === call) talk.selected.value = null;
  }

  /** Deletes every overheard message of a pair ("OH2AAA>OH2BBB"); its thread closes if it was the open one. */
  function deleteOverheard(from: string, to: string): void {
    if (send({ cmd: "overheard_delete", from_call: from, to_call: to }) && talk.selected.value === `${from}>${to}`) talk.selected.value = null;
  }

  /** Sends a message and opens the conversation it belongs to. */
  function sendMessage(to: string, text: string): void {
    if (send({ cmd: "send_message", to, text })) talk.selected.value = to;
  }

  return { ...talk, showOverheard, writeTo, openMessages, deleteConversation, deleteOverheard, sendMessage };
}
