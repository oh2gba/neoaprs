<script setup lang="ts">
// The messages with one station as bubbles, the oldest first: ours at the right, theirs at the left. In a bubble the text, and under it, small, the time, for ours the mark and the state with Retry or Cancel where they apply, the delivery chain
// of the digipeaters its packet went by (MessageChain) under ours, and under one that came in the route it came by ("via OH2RCH-2"). It is scrolled to the newest when it is shown and whenever a message is added. `peer` is the station the thread is with
// (null: a new message is being written, and nothing is said). The Email tab has its own list (EmailList).
import { ref } from "vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import { t } from "@/i18n";
import { useToNewest } from "@/composables/useToNewest";
import { clockText, dateTimeText } from "@/lib/format";
import { canCancel, canRetry, stateText } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; peer: string | null; heardDirect?: ReadonlySet<string> }>(), {
  heardDirect: () => new Set<string>(),
});
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number] }>();

const log = ref<HTMLElement | null>(null);

useToNewest(log, () => [props.peer, props.thread.length]);
</script>

<template>
  <div ref="log" class="bubbles" role="log" :aria-label="peer === null ? t('messages.thread') : t('messages.thread_with', { peer })">
    <p v-if="peer !== null && thread.length === 0" class="empty">{{ t("messages.thread_empty", { peer }) }}</p>
    <div v-for="m in thread" :key="m.id" class="bubble" :class="m.direction === 'in' ? 'in' : 'out'" :data-direction="m.direction">
      <p class="bubble-text">{{ m.text }}</p>
      <p class="bubble-meta muted">
        <span :title="dateTimeText(m.at)">{{ clockText(m.at) }}</span>
        <MessageMark :row="m" />
        <span v-if="m.direction === 'out'" class="msg-state" :class="`state-${m.state}`">{{ stateText(m) }}</span>
        <button v-if="canRetry(m)" type="button" class="btn small" @click="emit('retry', m.id)">{{ t("messages.retry") }}</button>
        <button v-if="canCancel(m)" type="button" class="btn small" @click="emit('cancel', m.id)">{{ t("messages.cancel") }}</button>
      </p>
      <MessageChain v-if="m.direction === 'out'" :row="m" :heard-direct="heardDirect" />
      <p v-if="m.route" class="bubble-route muted" :title="t('messages.route_title')">{{ m.route }}</p>
    </div>
  </div>
</template>
