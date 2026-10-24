<script setup lang="ts">
// The messages with one station as bubbles, the oldest first: ours at the right, theirs at the left. In a bubble the text, and under it, small, the time, for ours the mark and the state with Retry or Cancel where they apply, the delivery chain
// of the digipeaters its packet went by (MessageChain) under ours, and under one that came in the route it came by ("via OH2RCH-2"). It is scrolled to the newest when it is shown and whenever a message is added. `peer` is the station the thread is with
// (null: a new message is being written, and nothing is said). A query we sent (the Stations table's menu: `?APRSS` and the like, sent with no message id) is no bubble but a small grey line in the middle, "You asked for its status", with the time. The Email tab has its own list (EmailList).
import { computed, ref } from "vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import { t } from "@/i18n";
import { useToNewest } from "@/composables/useToNewest";
import { clockText, dateTimeText } from "@/lib/format";
import { askedText, canCancel, canRetry, queryKind, stateText } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; peer: string | null; heardDirect?: ReadonlySet<string> }>(), {
  heardDirect: () => new Set<string>(),
});
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number] }>();

const log = ref<HTMLElement | null>(null);
/** Each message with the query it is the note of, if it is. */
const items = computed(() => props.thread.map((m) => ({ m, asked: queryKind(m) })));

useToNewest(log, () => [props.peer, props.thread.length]);
</script>

<template>
  <div ref="log" class="bubbles" role="log" :aria-label="peer === null ? t('messages.thread') : t('messages.thread_with', { peer })">
    <p v-if="peer !== null && thread.length === 0" class="empty">{{ t("messages.thread_empty", { peer }) }}</p>
    <template v-for="{ m, asked } in items" :key="m.id">
      <p v-if="asked" class="asked muted" data-asked>
        <span>{{ askedText(asked) }}</span>
        <span :title="dateTimeText(m.at)">{{ clockText(m.at) }}</span>
        <MessageMark v-if="m.state === 'sending'" :row="m" />
      </p>
      <div v-else class="bubble" :class="m.direction === 'in' ? 'in' : 'out'" :data-direction="m.direction">
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
    </template>
  </div>
</template>
