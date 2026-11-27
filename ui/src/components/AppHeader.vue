<script setup lang="ts">
// The top line: the title link, the "no call set" button, the status marks (lib/pills.ts, each a
// button that opens where it is set), the count of unseen messages and, last, the RX only switch,
// which never folds. The call and the version are shown in Settings, not here. The marks keep their
// order; when the row is too narrow the ones `foldAway` names are not drawn. Their widths come from
// a hidden copy of the row, measured whenever it or the room changes, before the frame is painted.
import { PROJECT_URL } from "@/lib/links";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import TagMark from "@/components/TagMark.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import RxSwitch from "@/components/RxSwitch.vue";
import { t } from "@/i18n";
import { foldAway, type HeaderPill, type PillTarget } from "@/lib/pills";
import type { RxSwitch as RxSwitchState } from "@/lib/rxswitch";
import { unreadText } from "@/lib/unread";

const props = defineProps<{
  /** The station call from the settings; null until the daemon has reported it. */
  call: string | null;
  unread: number;
  /** The marks before the count. */
  pills?: readonly HeaderPill[];
  /** The RX only switch; null until the daemon has sent the settings. */
  rx?: RxSwitchState | null;
}>();
const emit = defineEmits<{
  messages: [];
  setup: [];
  open: [target: PillTarget, focus: string];
  transmit: [on: boolean];
}>();

const row = ref<HTMLElement | null>(null);
const copy = ref<HTMLElement | null>(null);
const folded = ref<ReadonlySet<HeaderPill["id"]>>(new Set());

function fold(): void {
  const marks = props.pills ?? [];
  if (!row.value || !copy.value || marks.length === 0) return;
  const widths = [...copy.value.children].map((mark) => mark.getBoundingClientRect().width);
  const gap = parseFloat(getComputedStyle(row.value).columnGap) || 0;
  const next = foldAway(marks, widths, row.value.getBoundingClientRect().width + 0.01, gap);
  const same = next.size === folded.value.size && [...next].every((id) => folded.value.has(id));
  if (!same) folded.value = next;
}

let sizes: ResizeObserver | null = null;
watch(() => props.pills, fold, { flush: "post" });
watch([row, copy], ([shown, hidden]) => {
  sizes?.disconnect();
  if (typeof ResizeObserver !== "function" || !shown || !hidden) return;
  sizes = new ResizeObserver(fold);
  sizes.observe(shown);
  sizes.observe(hidden);
});
onMounted(fold);
onBeforeUnmount(() => sizes?.disconnect());
</script>

<template>
  <header class="appheader">
    <span v-if="pills?.length" ref="copy" class="headpills-copy" aria-hidden="true">
      <TagMark v-for="pill in pills" :key="pill.id" :tone="pill.tone">{{ t(pill.text, pill.textValues) }}</TagMark>
    </span>
    <h1>
      <a class="brand" :href="PROJECT_URL" target="_blank" rel="noopener" :title="t('header.project_title')"
        >Neo<b>APRS</b></a
      >
    </h1>
    <button v-if="call === ''" type="button" class="nocall" :title="t('header.no_call_title')" @click="emit('setup')">
      <span class="nocall-text">{{ t("header.no_call") }}</span>
    </button>
    <span v-if="pills?.length" ref="row" class="headpills">
      <TagMark
        v-for="pill in pills.filter((one) => !folded.has(one.id))"
        :key="pill.id"
        :as="pill.target === null ? 'span' : 'button'"
        :tone="pill.tone"
        :class="['headpill', `pill-${pill.id}`]"
        :title="t(pill.title, pill.titleValues)"
        :role="pill.target === null ? 'status' : undefined"
        @click="pill.target !== null && emit('open', pill.target, pill.focus)"
        >{{ t(pill.text, pill.textValues) }}</TagMark
      >
    </span>
    <TagMark
      v-if="unread > 0"
      as="button"
      class="badge headmail"
      :title="t('header.unread_open', { n: unread })"
      @click="emit('messages')"
    >
      <MessageGlyph :size="16" /> {{ unread }}<span class="sr-only"> {{ unreadText(unread) }}</span>
    </TagMark>
    <RxSwitch
      v-if="rx"
      :rx="rx"
      @transmit="emit('transmit', $event)"
      @open="(target, focus) => emit('open', target, focus)"
    />
  </header>
</template>
