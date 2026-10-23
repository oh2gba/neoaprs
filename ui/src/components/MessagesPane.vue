<script setup lang="ts">
// The Messages tab, laid out like Signal by the width of the tab itself (not of the window: the panel beside the map can be narrow on a wide screen; MESSAGES_WIDE, lib/layout.ts). Wide: the list of conversations (ConversationList) at the left, a divider, and the open
// conversation (ConversationView) at the right, or "Choose a conversation" while none is open. Narrow: one of the two fills the tab, the list until a conversation is picked, then the conversation with a back arrow (and Esc) to the list. A conversation counts as open
// (and its messages as seen, composables/useConversations.ts) while `selected` is a call, so on a narrow page the list showing means no conversation is open: going back says `select` null. "New message" opens an empty conversation with the cursor in To, which
// is no conversation until a message is sent. The text being written is kept here, so that it is there when the user goes back to the list and in again. Everything the tab can do is an event; App.vue passes the daemon's state in and sends the commands.
import { computed, nextTick, ref, watch } from "vue";
import ConversationList from "@/components/ConversationList.vue";
import ConversationView from "@/components/ConversationView.vue";
import { useElementWidth } from "@/composables/useElementWidth";
import { MESSAGES_WIDE } from "@/lib/layout";
import type { Conversation } from "@/lib/messages";
import type { Candidate } from "@/lib/recipients";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    conversations: readonly Conversation[];
    selected: string | null;
    thread: readonly MessageRow[];
    connected: boolean;
    now: number;
    showOverheard: boolean;
    paths: ReadonlyMap<string, string>;
    /** the path to send by that the daemon suggests for each station that has one (see the station card) */
    suggestions?: ReadonlyMap<string, string | null>;
    /** the path of the setting beacon/path, which a station without one of its own has */
    fallbackPath: string;
    /** the stations that are RF only */
    rfOnly?: ReadonlySet<string>;
    /** the stations heard direct, which the chain under a message judges a digipeater that was not heard by */
    heardDirect?: ReadonlySet<string>;
    /** the stations that can be picked in the compose box's list "Stations" (lib/recipients.ts) */
    candidates?: readonly Candidate[];
  }>(),
  { rfOnly: () => new Set<string>(), suggestions: () => new Map<string, string | null>(), heardDirect: () => new Set<string>(), candidates: () => [] },
);
const emit = defineEmits<{
  /** a conversation was picked; null: the open one was left (the way back on a narrow page) */
  select: [call: string | null];
  send: [to: string, text: string];
  /** one text to several stations: a message of its own for each */
  sendMany: [to: string[], text: string];
  retry: [id: number];
  cancel: [id: number];
  deleteConversation: [call: string];
  /** every overheard message of the pair: who sent it, who it was for */
  deleteOverheard: [from: string, to: string];
  "update:showOverheard": [show: boolean];
  path: [call: string, path: string];
  clearPath: [call: string];
  setRfOnly: [call: string, on: boolean];
}>();

const root = ref<HTMLElement | null>(null);
const width = useElementWidth(root);
const wide = computed(() => width.value >= MESSAGES_WIDE);
/** A new message is being written (no conversation open), and how many were begun: a new one starts empty. */
const composing = ref(false);
const begun = ref(0);
const draft = ref("");

/** Whether a conversation, or a new message, is shown (on a narrow page: instead of the list). */
const isOpen = computed(() => props.selected !== null || composing.value);

watch(
  () => props.selected,
  (call) => {
    if (call !== null) composing.value = false;
  },
);

function newMessage(): void {
  composing.value = true;
  begun.value++;
  if (props.selected !== null) emit("select", null);
}

function pick(call: string): void {
  composing.value = false;
  emit("select", call);
}

/** Back to the list (narrow): leaves the conversation, and puts the focus on its row again. */
async function back(): Promise<void> {
  const was = props.selected;
  composing.value = false;
  if (was === null) return;
  emit("select", null);
  await nextTick();
  [...(root.value?.querySelectorAll<HTMLElement>(".conv") ?? [])].find((row) => row.dataset.call === was)?.focus({ preventScroll: true });
}

function onEsc(event: KeyboardEvent): void {
  if (!wide.value && isOpen.value && !event.defaultPrevented) void back();
}

function sendMany(to: string[], text: string): void {
  if (props.selected === null) composing.value = false;
  emit("sendMany", to, text);
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
      @select="pick"
      @new-message="newMessage"
      @update:show-overheard="emit('update:showOverheard', $event)"
      @delete-conversation="emit('deleteConversation', $event)"
      @delete-overheard="(from, to) => emit('deleteOverheard', from, to)"
    />
    <ConversationView
      v-if="isOpen"
      :key="selected ?? `new${begun}`"
      v-model:text="draft"
      :selected="selected"
      :narrow="!wide"
      :thread="thread"
      :connected="connected"
      :paths="paths"
      :suggestions="suggestions"
      :fallback-path="fallbackPath"
      :rf-only="rfOnly"
      :heard-direct="heardDirect"
      :candidates="candidates"
      @back="back"
      @send="(to, text) => emit('send', to, text)"
      @send-many="sendMany"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
      @path="(c, p) => emit('path', c, p)"
      @clear-path="emit('clearPath', $event)"
      @set-rf-only="(c, on) => emit('setRfOnly', c, on)"
    />
    <div v-else-if="wide" class="convo-empty">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" aria-hidden="true">
        <path d="M4 5.5h16v10H10l-4.5 3.5V15.5H4z" />
      </svg>
      <p>Choose a conversation</p>
      <button type="button" class="btn primary" @click="newMessage">New message</button>
    </div>
  </div>
</template>
