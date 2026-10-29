<script setup lang="ts">
// The messages with one station as bubbles, the oldest first: ours at the right, theirs at the left. In a bubble the text, and under it, small, the time, for ours the mark and the state with Retry or Cancel where they apply (and a small trash can, pressed twice, for one that is no longer being sent and was never acked), the delivery chain
// of the digipeaters its packet went by (MessageChain) under ours, and under one that came in the route it came by ("via OH2RCH-2"). It is scrolled to the newest when it is shown and whenever a message is added. `peer` is the station the thread is with
// (null: a new message is being written, and nothing is said). A right-click on a bubble (a long press on a touch screen) offers to copy its text (CopyMenu). A query we sent (the Stations table's menu: `?APRSS` and the like, sent with no message id) is no bubble but a small grey line in the middle, "You asked for its status", with the time. The Email tab has its own list (EmailList).
import { computed, ref } from "vue";
import CopyMenu from "@/components/CopyMenu.vue";
import IconButton from "@/components/IconButton.vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import { t } from "@/i18n";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useSure } from "@/composables/useSure";
import { useToNewest } from "@/composables/useToNewest";
import { clockText, dateTimeText } from "@/lib/format";
import { askedNote, canCancel, canDelete, canRetry, stateText } from "@/lib/messages";
import type { MessageRow } from "@/protocol/protocol";

const props = withDefaults(defineProps<{ thread: readonly MessageRow[]; peer: string | null; heardDirect?: ReadonlySet<string> }>(), {
  heardDirect: () => new Set<string>(),
});
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number]; delete: [id: number] }>();
const sure = useSure<number>(); // (the id of the message, armed by the first press of its trash can)

const log = ref<HTMLElement | null>(null);
/** Each message with the note of the query it is, if it is one. */
const items = computed(() => props.thread.map((m) => ({ m, asked: askedNote(m) })));

useToNewest(log, () => [props.peer, props.thread.length]);
/** The copy menu of a bubble: the text of its message. */
const copy = useCopyMenu((bubble) => {
  const row = props.thread.find((m) => String(m.id) === bubble.dataset["id"]);
  return row === undefined ? [] : [{ kind: "message", text: row.text }];
});
</script>

<template>
  <div ref="log" class="bubbles" role="log" :aria-label="peer === null ? t('messages.thread') : t('messages.thread_with', { peer })">
    <p v-if="peer !== null && thread.length === 0" class="empty">{{ t("messages.thread_empty", { peer }) }}</p>
    <template v-for="{ m, asked } in items" :key="m.id">
      <p v-if="asked" class="asked muted" data-asked>
        <span>{{ asked }}</span>
        <span :title="dateTimeText(m.at)">{{ clockText(m.at) }}</span>
        <MessageMark v-if="m.state === 'sending'" :row="m" />
      </p>
      <div
        v-else
        class="bubble copysource"
        :class="[m.direction === 'in' ? 'in' : 'out', { queued: m.state === 'queued' }]"
        :data-direction="m.direction"
        :data-id="m.id"
        v-on="copy.on.value"
      >
        <p class="bubble-text">{{ m.text }}</p>
        <p class="bubble-meta muted">
          <span :title="dateTimeText(m.at)">{{ clockText(m.at) }}</span>
          <MessageMark :row="m" />
          <span v-if="m.direction === 'out'" class="msg-state" :class="`state-${m.state}`">{{ stateText(m) }}</span>
          <button v-if="canRetry(m)" type="button" class="btn small" @click="emit('retry', m.id)">{{ t("messages.retry") }}</button>
          <button v-if="canCancel(m)" type="button" class="btn small" @click="emit('cancel', m.id)">{{ t("messages.cancel") }}</button>
          <IconButton
            v-if="canDelete(m)"
            kind="delete"
            class="bubble-delete"
            :armed="sure.armed.value === m.id"
            :label="t('messages.delete')"
            :title="t('messages.delete')"
            @click="sure.press(m.id, () => emit('delete', m.id))"
          />
        </p>
        <MessageChain v-if="m.direction === 'out'" :row="m" :heard-direct="heardDirect" />
        <p v-if="m.route" class="bubble-route muted" :title="t('messages.route_title')">{{ m.route }}</p>
      </div>
    </template>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </div>
</template>
