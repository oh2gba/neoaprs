<script setup lang="ts">
// The messages with one station, the oldest first, as the Messages tab and the Email tab show them: the text, the time, the route a message that came in came by, and for ours the mark, the state with its attempts
// and Retry or Cancel where they apply, and under it the chain of the digipeaters its packet went by (MessageChain). `heardDirect` are the stations heard direct, which a hop that was not heard is judged by. It keeps itself scrolled to the newest. `peer` is the station the thread is with (null: none picked, and nothing is said).
// With `gateway` (the Email tab) a message that came in is labelled as the gateway's answer, one of ours is shown as a mail "to jane@example.com" (or as what the gateway's own command does: lib/email.ts `mailLine`), and one of ours that got no ack is "sent, not confirmed" and not failed: the gateway's acks reach us only through an iGate.
import { nextTick, ref, watch } from "vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import { isNotConfirmed, mailLine, mailStateText } from "@/lib/email";
import { clockText, dateTimeText } from "@/lib/format";
import { canCancel, canRetry, stateText } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; peer: string | null; heardDirect?: ReadonlySet<string>; gateway?: boolean }>(), {
  heardDirect: () => new Set<string>(),
  gateway: false,
});

const stateOf = (m: MessageRow): string => (props.gateway ? mailStateText(m) : stateText(m));
const stateClass = (m: MessageRow): string => (props.gateway && isNotConfirmed(m) ? "state-unconfirmed" : `state-${m.state}`);
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
      <p v-if="gateway && m.direction === 'in'" class="msg-from muted">{{ peer }} answers</p>
      <p v-if="gateway && m.direction === 'out' && mailLine(m.text).head" class="msg-from muted">{{ mailLine(m.text).head }}</p>
      <p class="msg-text" :title="gateway && m.direction === 'out' ? m.text : undefined">
        {{ gateway && m.direction === "out" ? mailLine(m.text).body : m.text }}
      </p>
      <p class="msg-meta muted">
        <span :title="dateTimeText(m.at)">{{ clockText(m.at) }}</span>
        <MessageMark :row="m" :mail="gateway" />
        <span v-if="m.direction === 'out'" class="msg-state" :class="stateClass(m)">{{ stateOf(m) }}</span>
        <button v-if="canRetry(m)" type="button" class="btn small" @click="emit('retry', m.id)">Retry</button>
        <button v-if="canCancel(m)" type="button" class="btn small" @click="emit('cancel', m.id)">Cancel</button>
      </p>
      <MessageChain v-if="m.direction === 'out'" :row="m" :heard-direct="heardDirect" :mail="gateway" />
      <p v-if="m.route" class="msg-route muted" title="How the packet reached us">{{ m.route }}</p>
    </div>
  </div>
</template>
