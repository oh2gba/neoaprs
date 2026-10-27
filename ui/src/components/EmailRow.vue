<script setup lang="ts">
// One row of the Email tab's list (lib/mailitems.ts): "To jane@example.com" or "From EMAIL-2" over the text (one line; a click opens the row to show it whole, with the time, the route and the chain of digipeaters), and for
// a message of ours its state in words with its mark (Sending (1 of 2), Delivered, Not confirmed, Rejected) and Retry or Cancel where they apply. The corner has the trash can, which asks twice. A row that came in and has not
// been seen is bold with a bar at its left (`fresh`). A right-click on the row (a long press on a touch screen) offers to copy its text and the address (CopyMenu).
import { computed, ref } from "vue";
import CopyMenu from "@/components/CopyMenu.vue";
import IconButton from "@/components/IconButton.vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import { t } from "@/i18n";
import { useCopyMenu } from "@/composables/useCopyMenu";
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
/** The copy menu of the row: the text (when there is one) and the address (when there is one). */
const copy = useCopyMenu(() => [
  ...(props.item.text === "" ? [] : [{ kind: "message" as const, text: props.item.text }]),
  ...(props.item.address === "" ? [] : [{ kind: "address" as const, text: props.item.address }]),
]);
</script>

<template>
  <li class="mail copysource" :class="[row.direction, { fresh, open }]" v-on="copy.on.value">
    <div class="mail-top">
      <button type="button" class="mail-body" :aria-expanded="open" :title="item.line" @click="copy.unlessHeld(() => (open = !open))">
        <span class="mail-title">{{ item.title }}</span>
        <span v-if="item.text" class="mail-text">{{ item.text }}</span>
      </button>
      <IconButton
        kind="delete"
        class="mail-delete"
        :armed="sure.armed.value === row.id"
        :label="t('email.delete', { title: item.title })"
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
      <button v-if="canRetry(row)" type="button" class="btn small" @click="emit('retry', row.id)">{{ t("messages.retry") }}</button>
      <button v-if="canCancel(row)" type="button" class="btn small" @click="emit('cancel', row.id)">{{ t("messages.cancel") }}</button>
    </p>
    <div v-if="open" class="mail-detail muted">
      <span>{{ dateTimeText(row.at) }}</span>
      <span v-if="row.route" :title="t('messages.route_title')">{{ row.route }}</span>
      <MessageChain v-if="row.direction === 'out'" :row="row" :heard-direct="heardDirect" mail />
    </div>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </li>
</template>
