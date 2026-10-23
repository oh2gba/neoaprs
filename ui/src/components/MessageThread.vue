<script setup lang="ts">
// The messages with one station, the oldest first, as the Messages tab and the Email tab show them: the text, the time, the route a message that came in came by, and for ours the mark, the state with its attempts
// and Retry or Cancel where they apply, and under it the chain of the digipeaters its packet went by (MessageChain). `heardDirect` are the stations heard direct, which a hop that was not heard is judged by. It keeps itself scrolled to the newest. `peer` is the station the thread is with (null: none picked, and nothing is said).
import { nextTick, ref, watch } from "vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import { clockText, dateTimeText } from "@/lib/format";
import { canCancel, canRetry, stateText } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; peer: string | null; heardDirect?: ReadonlySet<string> }>(), {
  heardDirect: () => new Set<string>(),
});
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number] }>();

const log = ref<HTMLElement | null>(null);

watch(
  () => props.thread.length,
  async () => {
    await nextTick();
    if (log.value) log.value.scrollTop = log.value.scrollHeight;
  },
);
</script>

<template>
  <div ref="log" class="thread" role="log" :aria-label="peer === null ? 'Messages' : `Messages with ${peer}`">
    <p v-if="peer !== null && thread.length === 0" class="empty">No message with {{ peer }} yet.</p>
    <div v-for="m in thread" :key="m.id" class="msg" :class="m.direction">
      <p class="msg-text">{{ m.text }}</p>
      <p class="msg-meta muted">
        <span :title="dateTimeText(m.at)">{{ clockText(m.at) }}</span>
        <MessageMark :row="m" />
        <span v-if="m.direction === 'out'" class="msg-state" :class="`state-${m.state}`">{{ stateText(m) }}</span>
        <button v-if="canRetry(m)" type="button" class="btn small" @click="emit('retry', m.id)">Retry</button>
        <button v-if="canCancel(m)" type="button" class="btn small" @click="emit('cancel', m.id)">Cancel</button>
      </p>
      <MessageChain v-if="m.direction === 'out'" :row="m" :heard-direct="heardDirect" />
      <p v-if="m.route" class="msg-route muted" title="How the packet reached us">{{ m.route }}</p>
    </div>
  </div>
</template>
