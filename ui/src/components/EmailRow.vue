<script setup lang="ts">
// One row of the Email tab's list (lib/mailitems.ts): "To jane@example.com" or "From EMAIL-2" over the text (one line; a click opens the row to show it whole, with the time, the route and the chain of digipeaters), and for
// a message of ours its state in words with its mark (Sending (1 of 2), Delivered, Not confirmed, Rejected) and Retry or Cancel where they apply. The corner has the trash can, which asks twice. A row that came in and has not
// been seen is bold with a bar at its left (`fresh`).
import { computed, ref } from "vue";
import IconButton from "@/components/IconButton.vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import { useSure } from "@/composables/useSure";
import { dateTimeText } from "@/lib/format";
import { mailState, mailTime, type MailItem } from "@/lib/mailitems";
import { canCancel, canRetry } from "@/lib/messages";

const props = defineProps<{ item: MailItem; fresh: boolean; now: number; heardDirect: ReadonlySet<string> }>();
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number]; delete: [id: number] }>();

const open = ref(false);
const sure = useSure<number>(); // (the id of the row, armed by the first press of the trash can)
const row = computed(() => props.item.row);
const state = computed(() => mailState(row.value));
</script>

<template>
  <li class="mail" :class="[row.direction, { fresh, open }]">
    <div class="mail-top">
      <button type="button" class="mail-body" :aria-expanded="open" :title="item.line" @click="open = !open">
        <span class="mail-title">{{ item.title }}</span>
        <span v-if="item.text" class="mail-text">{{ item.text }}</span>
      </button>
      <IconButton
        kind="delete"
        class="mail-delete"
        :armed="sure.armed.value === row.id"
        :label="`Delete: ${item.title}`"
        @click="sure.press(row.id, () => emit('delete', row.id))"
      />
    </div>
    <p class="mail-meta muted">
      <template v-if="state">
        <MessageMark :row="row" mail />
        <span class="mail-state" :class="`tone-${state.tone}`">{{ state.word }}</span>
        <span aria-hidden="true">·</span>
      </template>
      <span :title="dateTimeText(row.at)">{{ mailTime(row.at, now) }}</span>
      <button v-if="canRetry(row)" type="button" class="btn small" @click="emit('retry', row.id)">Retry</button>
      <button v-if="canCancel(row)" type="button" class="btn small" @click="emit('cancel', row.id)">Cancel</button>
    </p>
    <div v-if="open" class="mail-detail muted">
      <span>{{ dateTimeText(row.at) }}</span>
      <span v-if="row.route" title="How the packet reached us">{{ row.route }}</span>
      <MessageChain v-if="row.direction === 'out'" :row="row" :heard-direct="heardDirect" mail />
    </div>
  </li>
</template>
