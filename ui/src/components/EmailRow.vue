<script setup lang="ts">
// One row of the Email tab's list (lib/mailitems.ts): "To jane@example.com" or "From EMAIL-2"
// over the text; a click shows the whole row. For ours it shows the state with its mark and
// Retry or Cancel. The corner trash asks twice. An unseen incoming row is bold with a bar
// (`fresh`). Retry is off while the mail cannot go (`offline`). Right-click copies (CopyMenu).
import { computed, ref } from "vue";
import CopyMenu from "@/components/CopyMenu.vue";
import IconButton from "@/components/IconButton.vue";
import MessageChain from "@/components/MessageChain.vue";
import MessageMark from "@/components/MessageMark.vue";
import TagMark from "@/components/TagMark.vue";
import { t } from "@/i18n";
import { useCopyMenu } from "@/composables/useCopyMenu";
import { useCameOn } from "@/composables/useStationRadio";
import { radioTone } from "@/lib/channels";
import { routeWords } from "@/lib/routes";
import { useSure } from "@/composables/useSure";
import { dateTimeText } from "@/lib/format";
import { mailState, mailTime, type MailItem } from "@/lib/mailitems";
import { canCancel, canRetry } from "@/lib/messages";

const props = withDefaults(
  defineProps<{ item: MailItem; fresh: boolean; now: number; heardDirect: ReadonlySet<string>; offline?: string }>(),
  {
    offline: undefined,
  },
);
const emit = defineEmits<{ retry: [id: number]; cancel: [id: number]; delete: [id: number] }>();

const open = ref(false);
const sure = useSure<number>();
const row = computed(() => props.item.row);
const state = computed(() => mailState(row.value));
/** The radio an incoming mail came on, where radios are named. */
const cameOn = useCameOn();
const on = computed(() => cameOn(row.value));
/** The copy menu of the row: its text and address, when present. */
const copy = useCopyMenu(() => [
  ...(props.item.text === "" ? [] : [{ kind: "message" as const, text: props.item.text }]),
  ...(props.item.address === "" ? [] : [{ kind: "address" as const, text: props.item.address }]),
]);
</script>

<template>
  <li class="mail copysource" tabindex="0" :class="[row.direction, { fresh, open }]" v-on="copy.on.value">
    <div class="mail-top">
      <button
        type="button"
        class="mail-body"
        :aria-expanded="open"
        :title="item.line"
        @click="copy.unlessHeld(() => (open = !open))"
      >
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
      <button
        v-if="canRetry(row)"
        type="button"
        class="btn small"
        :disabled="offline !== undefined"
        :title="offline"
        @click="emit('retry', row.id)"
      >
        {{ t("messages.retry") }}
      </button>
      <button v-if="canCancel(row)" type="button" class="btn small" @click="emit('cancel', row.id)">
        {{ t("messages.cancel") }}
      </button>
    </p>
    <div v-if="open" class="mail-detail muted">
      <span>{{ dateTimeText(row.at) }}</span>
      <span v-if="row.route || on" :title="t('messages.route_title')">
        <TagMark v-if="on" :tone="radioTone(on)" :title="t('radio.heard_on', { name: on.name })">{{ on.name }}</TagMark>
        {{ routeWords(row.route) }}
      </span>
      <MessageChain v-if="row.direction === 'out'" :row="row" :heard-direct="heardDirect" mail />
    </div>
    <CopyMenu v-if="copy.menu.value" :key="copy.key.value" v-bind="copy.menu.value" @close="copy.close()" />
  </li>
</template>
