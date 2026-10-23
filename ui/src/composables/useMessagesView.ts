// The Messages tab as the page runs it: the conversations (a message is seen only while the tab is in front of the user, lib/unread.ts), whether the overheard ones are listed (remembered), the group compose (one text to several stations: `group`, opened by `openGroup`), and the ways to the tab: the Message button of a station's card, the mail in the header, a message sent, a conversation deleted.
import { computed, ref, watch } from "vue";
import type { Panel } from "@/composables/usePanel";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useConversations } from "@/composables/useConversations";
import { useVisible } from "@/composables/useVisible";
import { normalizeCall } from "@/lib/calls";
import { isGateway } from "@/lib/messages";
import { addable } from "@/lib/recipients";
import { isViewingTab } from "@/lib/unread";
import type { Command, MessageRow } from "@/protocol/protocol";

export function useMessagesView(messages: ReadonlyMap<string, MessageRow>, panel: Panel, send: (command: Command) => boolean) {
  const visible = useVisible();
  const viewing = computed(() => isViewingTab({ tab: panel.tab.value, collapsed: panel.collapsed.value, visible: visible.value }, "messages"));
  const showOverheard = usePersistedFlag("overheard", ["on", "off"], false);
  const talk = useConversations(messages, viewing, showOverheard);
  /** The calls of the group compose that is open, null when there is none. It and an open conversation exclude each other. */
  const group = ref<string[] | null>(null);

  watch(talk.selected, (call) => {
    if (call !== null) group.value = null;
  });

  /**
   * One text to several stations: the Messages tab, unfolded, with the group compose for `calls` (the card stack's "Message these 3"). The open conversation is left (nothing is seen while the group is open), and a call that is no call, the email gateway or a duplicate is left out;
   * with none left nothing is opened. It takes the place of a group that is open.
   */
  function openGroup(calls: readonly string[]): void {
    const list = calls.reduce<string[]>((kept, call) => (addable(call, kept) ? [...kept, normalizeCall(call)] : kept), []);
    if (list.length === 0) return;
    talk.selected.value = null;
    group.value = list;
    panel.show("messages");
  }

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

  /** Sends the same text to several stations, a message to each (the daemon spaces them), exactly as if sent one by one; the group compose that sent them closes itself. */
  function sendMessages(to: readonly string[], text: string): void {
    for (const call of to) send({ cmd: "send_message", to: call, text });
  }

  return { ...talk, group, openGroup, showOverheard, writeTo, openMessages, deleteConversation, deleteOverheard, sendMessage, sendMessages };
}
