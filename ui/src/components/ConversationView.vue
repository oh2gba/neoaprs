<script setup lang="ts">
// One conversation of the Messages tab, filling its column: a header bar (on a narrow page the back arrow "‹" to the list; the call; "Route" for the path and RF only), the bubbles (ConversationThread) filling the height and the box to write in (MessageCompose: the text,
// "12 left" and Send, no To: the conversation is the station) fixed at the bottom. An overheard pair has no Route and no box to write in (the messages are not ours: only the bubbles, and the delete in the list). It is the page's to put a new one in place of this when
// another conversation is picked (a `key`), and on a narrow page it takes the focus when it appears, so that Esc goes back.
import { computed, onMounted, ref } from "vue";
import ConversationThread from "@/components/ConversationThread.vue";
import MessageCompose from "@/components/MessageCompose.vue";
import RouteMenu from "@/components/RouteMenu.vue";
import { t } from "@/i18n";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { conversationName, isOverheard, replyTo } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = defineProps<{
  selected: string;
  /** one column at a time: the header has the way back to the list */
  narrow: boolean;
  thread: readonly MessageRow[];
}>();
const text = defineModel<string>("text", { default: "" });
const emit = defineEmits<{
  back: [];
  send: [to: string, text: string];
  retry: [id: number];
  cancel: [id: number];
}>();
const { connected, heardDirect, suggestions, fallbackPath, prefs } = useDaemonContext();
const { paths, rfOnly } = prefs;

const root = ref<HTMLElement | null>(null);
const heard = computed(() => isOverheard(props.selected));

onMounted(() => {
  if (props.narrow) root.value?.focus({ preventScroll: true });
});
</script>

<template>
  <section ref="root" class="convo" tabindex="-1" :aria-label="t('messages.conversation_with', { name: conversationName(selected) })">
    <header class="convo-head">
      <button v-if="narrow" type="button" class="convo-back" :aria-label="t('messages.back_label')" :title="t('messages.back')" @click="emit('back')">
        <span aria-hidden="true">‹</span>
      </button>
      <h3 class="convo-title">
        <template v-if="heard">{{ t("messages.overheard_title", { name: conversationName(selected) }) }}</template>
        <template v-else>{{ selected }}</template>
      </h3>
      <RouteMenu
        v-if="!heard"
        :key="selected"
        :call="selected"
        :paths="paths"
        :fallback-path="fallbackPath"
        :rf-only="rfOnly"
        :suggested="suggestions.get(selected) ?? null"
        @path="prefs.setPath"
        @clear-path="prefs.clearPath"
        @set-rf-only="prefs.setRfOnly"
      />
    </header>
    <ConversationThread :thread="thread" :peer="selected" :heard-direct="heardDirect" @retry="emit('retry', $event)" @cancel="emit('cancel', $event)" />
    <MessageCompose v-if="!heard" v-model:text="text" :to="[replyTo(selected)]" :connected="connected" @send="(to, body) => emit('send', to, body)" />
  </section>
</template>
