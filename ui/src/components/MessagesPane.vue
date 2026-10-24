<script setup lang="ts">
// The Messages tab, laid out like Signal by the width of the tab itself (not of the window: the panel beside the map can be narrow on a wide screen; MESSAGES_WIDE, lib/layout.ts). Wide: the list of conversations (ConversationList) at the left, a divider, and the open
// conversation (ConversationView) at the right, or a quiet "Choose a conversation" while none is open. Narrow: one of the two fills the tab, the list until a conversation is picked, then the conversation with a back arrow (and Esc) to the list. A conversation counts as open
// (and its messages as seen, composables/useConversations.ts) while `selected` is a call, so on a narrow page the list showing means no conversation is open: going back says `select` null. A chat starts from a station (its card's Message button), not here. `group` is the
// compose for one text to several stations (GroupCompose), which the page opens with a list of calls and which takes the place of the conversation. The text being written is kept here, so that it is there when the user goes back to the list and in again. Everything the
// tab can do is an event; App.vue passes the daemon's state in and sends the commands.
import { computed, nextTick, ref } from "vue";
import ConversationList from "@/components/ConversationList.vue";
import ConversationView from "@/components/ConversationView.vue";
import GroupCompose from "@/components/GroupCompose.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useElementWidth } from "@/composables/useElementWidth";
import { MESSAGES_WIDE } from "@/lib/layout";
import type { Conversation } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    conversations: readonly Conversation[];
    selected: string | null;
    thread: readonly MessageRow[];
    showOverheard: boolean;
    /** the calls of the group compose that is open (one text to several stations), null when there is none; the page opens it (useMessagesView `openGroup`) */
    group?: readonly string[] | null;
  }>(),
  { group: null },
);
const emit = defineEmits<{
  /** a conversation was picked; null: the open one was left (the way back on a narrow page) */
  select: [call: string | null];
  /** the recipients of the group compose that are left, or null: it was closed */
  "update:group": [calls: string[] | null];
  send: [to: string, text: string];
  /** one text to several stations: a message of its own for each */
  sendMany: [to: string[], text: string];
  retry: [id: number];
  cancel: [id: number];
  deleteMessage: [id: number];
  deleteConversation: [call: string];
  /** every overheard message of the pair: who sent it, who it was for */
  deleteOverheard: [from: string, to: string];
  "update:showOverheard": [show: boolean];
}>();
const { connected, now } = useDaemonContext();

const root = ref<HTMLElement | null>(null);
const width = useElementWidth(root);
const wide = computed(() => width.value >= MESSAGES_WIDE);
const draft = ref("");
const groupDraft = ref("");

/** Whether a conversation, or the group compose, is shown (on a narrow page: instead of the list). */
const isOpen = computed(() => props.selected !== null || props.group !== null);

/** Leaves the conversation (the way back to the list on a narrow page, Esc on either), and puts the focus on its row again. */
async function back(): Promise<void> {
  const was = props.selected;
  if (was === null) return;
  emit("select", null);
  await nextTick();
  [...(root.value?.querySelectorAll<HTMLElement>(".conv") ?? [])].find((row) => row.dataset.call === was)?.focus({ preventScroll: true });
}

/**
 * Esc deselects: the group compose is closed, or the open conversation is left (wide: the right side shows the empty state; narrow: back to the list). What is inside goes first: the Route box and the list of a box in it take their own Esc (and say so with
 * stopPropagation), and a text box with text in it keeps the text, so that one Esc does nothing to the selection; with the box empty Esc goes through.
 */
function onEsc(event: KeyboardEvent): void {
  if (event.defaultPrevented) return;
  if (event.target instanceof HTMLInputElement && event.target.type === "text" && event.target.value !== "") return;
  if (props.group !== null && props.selected === null) emit("update:group", null);
  else if (props.selected !== null) void back();
}

/** A text sent from the group compose goes out and the view closes: nothing is opened (the conversations are in the list as the messages go out). */
function sent(send: () => void): void {
  send();
  groupDraft.value = "";
  emit("update:group", null);
}
</script>

<template>
  <div ref="root" class="msgpane" :class="wide ? 'wide' : 'narrow'" @keydown.esc="onEsc">
    <ConversationList
      v-if="wide || !isOpen"
      :conversations="conversations"
      :selected="selected"
      :now="now"
      :show-overheard="showOverheard"
      @select="emit('select', $event)"
      @update:show-overheard="emit('update:showOverheard', $event)"
      @delete-conversation="emit('deleteConversation', $event)"
      @delete-overheard="(from, to) => emit('deleteOverheard', from, to)"
    />
    <GroupCompose
      v-if="group !== null && selected === null"
      v-model:text="groupDraft"
      :calls="group"
      :narrow="!wide"
      :connected="connected"
      @update="emit('update:group', $event)"
      @close="emit('update:group', null)"
      @send="(to, text) => sent(() => emit('send', to, text))"
      @send-many="(to, text) => sent(() => emit('sendMany', to, text))"
    />
    <ConversationView
      v-else-if="selected !== null"
      :key="selected"
      v-model:text="draft"
      :selected="selected"
      :narrow="!wide"
      :thread="thread"
      @back="back"
      @send="(to, text) => emit('send', to, text)"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
      @delete="emit('deleteMessage', $event)"
    />
    <div v-else-if="wide" class="convo-empty">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 5.5h16v10H10l-4.5 3.5V15.5H4z" />
      </svg>
      <p>{{ t("messages.choose") }}</p>
    </div>
  </div>
</template>
