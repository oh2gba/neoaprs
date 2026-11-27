<script setup lang="ts">
// The Messages tab, laid out by the tab's own width (MESSAGES_WIDE, lib/layout.ts): wide shows
// the list (ConversationList) and the open conversation (ConversationView) side by side; narrow
// shows one of them, with a back arrow and Esc to the list. A conversation counts as open while
// `selected` is a call, so on a narrow page a visible list means none is open. `group` is the
// compose for one text to several stations (GroupCompose). Everything the tab does is an event;
// App.vue passes the state in.
import { computed, nextTick, ref } from "vue";
import ConversationList from "@/components/ConversationList.vue";
import ConversationView from "@/components/ConversationView.vue";
import GroupCompose from "@/components/GroupCompose.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useElementWidth } from "@/composables/useElementWidth";
import { useRadios } from "@/composables/useRadios";
import { MESSAGES_WIDE } from "@/lib/layout";
import type { Conversation } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    conversations: readonly Conversation[];
    selected: string | null;
    thread: readonly MessageRow[];
    showOverheard: boolean;
    /** the calls of the open group compose; null when none (opened by useMessagesView
     * `openGroup`) */
    group?: readonly string[] | null;
  }>(),
  { group: null },
);
const emit = defineEmits<{
  /** a conversation was picked; null: the open one was left (back on a narrow page) */
  select: [call: string | null];
  /** the recipients still in the group compose; null: it was closed */
  "update:group": [calls: string[] | null];
  send: [to: string, text: string, locked: boolean];
  /** one text to several stations: a separate message for each */
  sendMany: [to: string[], text: string];
  retry: [id: number];
  cancel: [id: number];
  deleteMessage: [id: number];
  deleteConversation: [call: string];
  /** every overheard message of the pair: who sent it, who it was for */
  deleteOverheard: [from: string, to: string];
  "update:showOverheard": [show: boolean];
}>();
const { now, stations } = useDaemonContext();
const radios = useRadios();

/** Whether the link of each group recipient's radio is up (each text is a separate message). */
const groupConnected = computed(() =>
  (props.group ?? []).every(
    (call) => (radios.forStation(stations.value.get(call) ?? null) ?? radios.unheard.value)?.connected === true,
  ),
);

const root = ref<HTMLElement | null>(null);
const width = useElementWidth(root);
const wide = computed(() => width.value >= MESSAGES_WIDE);
const draft = ref("");
const groupDraft = ref("");

/** Whether a conversation or the group compose is shown (on a narrow page: instead of the list). */
const isOpen = computed(() => props.selected !== null || props.group !== null);

/** Leave the conversation (back to the list on a narrow page, Esc on either) and refocus its
 * row. */
async function back(): Promise<void> {
  const was = props.selected;
  if (was === null) return;
  emit("select", null);
  await nextTick();
  [...(root.value?.querySelectorAll<HTMLElement>(".conv") ?? [])]
    .find((row) => row.dataset.call === was)
    ?.focus({ preventScroll: true });
}

/** Esc closes the group compose or leaves the open conversation. Inner Esc handlers go first
 * (they stop propagation), and a text box with text keeps its text; an empty box lets Esc
 * through. */
function onEsc(event: KeyboardEvent): void {
  if (event.defaultPrevented) return;
  if (event.target instanceof HTMLInputElement && event.target.type === "text" && event.target.value !== "") return;
  if (props.group !== null && props.selected === null) emit("update:group", null);
  else if (props.selected !== null) void back();
}

/** A ready-made message to a service: its conversation opens with the start of the text in the
 * box and the cursor after it. */
async function write(to: string, text: string): Promise<void> {
  emit("update:group", null);
  emit("select", to);
  draft.value = text;
  await nextTick();
  const box = root.value?.querySelector<HTMLInputElement>("#msg-text");
  box?.focus();
  box?.setSelectionRange(text.length, text.length);
}

/** A text sent from the group compose goes out and the view closes; no conversation is opened. */
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
      @write="write"
    />
    <GroupCompose
      v-if="group !== null && selected === null"
      v-model:text="groupDraft"
      :calls="group"
      :narrow="!wide"
      :connected="groupConnected"
      @update="emit('update:group', $event)"
      @close="emit('update:group', null)"
      @send="(to, text) => sent(() => emit('send', to, text, false))"
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
      @send="(to, text, locked) => emit('send', to, text, locked)"
      @retry="emit('retry', $event)"
      @cancel="emit('cancel', $event)"
      @delete="emit('deleteMessage', $event)"
    />
    <div v-else-if="wide" class="convo-empty">
      <svg
        width="40"
        height="40"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.4"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M4 5.5h16v10H10l-4.5 3.5V15.5H4z" />
      </svg>
      <p>{{ t("messages.choose") }}</p>
    </div>
  </div>
</template>
