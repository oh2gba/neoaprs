<script setup lang="ts">
// One conversation of the Messages tab, filling its column: a header bar (on a narrow page the back arrow "‹" to the list; the call; "Route" for the path and RF only), the bubbles (ConversationThread) filling the height and the box to write in (MessageCompose) fixed at
// the bottom. `selected` null is a new message: the title says so, the thread is empty and the cursor is in To. An overheard pair has no Route (the messages are not ours); the box writes to the sender of it. It is the page's to put a new one in place of this when another
// conversation is picked (a `key`), and on a narrow page it takes the focus when it appears, so that Esc goes back.
import { onMounted, ref } from "vue";
import ConversationThread from "@/components/ConversationThread.vue";
import MessageCompose from "@/components/MessageCompose.vue";
import RouteMenu from "@/components/RouteMenu.vue";
import { conversationName, isOverheard } from "@/lib/messages";
import type { Candidate } from "@/lib/recipients";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(
  defineProps<{
    selected: string | null;
    /** one column at a time: the header has the way back to the list */
    narrow: boolean;
    thread: readonly MessageRow[];
    connected: boolean;
    paths: ReadonlyMap<string, string>;
    suggestions?: ReadonlyMap<string, string | null>;
    fallbackPath: string;
    rfOnly?: ReadonlySet<string>;
    heardDirect?: ReadonlySet<string>;
    candidates?: readonly Candidate[];
  }>(),
  { suggestions: () => new Map<string, string | null>(), rfOnly: () => new Set<string>(), heardDirect: () => new Set<string>(), candidates: () => [] },
);
const text = defineModel<string>("text", { default: "" });
const emit = defineEmits<{
  back: [];
  send: [to: string, text: string];
  sendMany: [to: string[], text: string];
  retry: [id: number];
  cancel: [id: number];
  path: [call: string, path: string];
  clearPath: [call: string];
  setRfOnly: [call: string, on: boolean];
}>();

const root = ref<HTMLElement | null>(null);
const compose = ref<InstanceType<typeof MessageCompose> | null>(null);

onMounted(() => {
  if (props.selected === null) compose.value?.focusTo();
  else if (props.narrow) root.value?.focus({ preventScroll: true });
});
</script>

<template>
  <section ref="root" class="convo" tabindex="-1" :aria-label="selected === null ? 'New message' : `Conversation with ${conversationName(selected)}`">
    <header class="convo-head">
      <button v-if="narrow" type="button" class="convo-back" aria-label="Back to the conversations" title="Back" @click="emit('back')">
        <span aria-hidden="true">‹</span>
      </button>
      <h3 class="convo-title">
        <template v-if="selected === null">New message</template>
        <template v-else-if="isOverheard(selected)">Overheard: {{ conversationName(selected) }}</template>
        <template v-else>{{ selected }}</template>
      </h3>
      <RouteMenu
        v-if="selected !== null && !isOverheard(selected)"
        :key="selected"
        :call="selected"
        :paths="paths"
        :fallback-path="fallbackPath"
        :rf-only="rfOnly"
        :suggested="suggestions.get(selected) ?? null"
        @path="(c, p) => emit('path', c, p)"
        @clear-path="emit('clearPath', $event)"
        @set-rf-only="(c, on) => emit('setRfOnly', c, on)"
      />
    </header>
    <ConversationThread :thread="thread" :peer="selected" :heard-direct="heardDirect" @retry="emit('retry', $event)" @cancel="emit('cancel', $event)" />
    <MessageCompose
      ref="compose"
      v-model:text="text"
      :selected="selected"
      :connected="connected"
      :candidates="candidates"
      @send="(to, body) => emit('send', to, body)"
      @send-many="(to, body) => emit('sendMany', to, body)"
    />
  </section>
</template>
