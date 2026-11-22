<script setup lang="ts">
// The top line: the title link, the "no call set" button, the status marks (lib/pills.ts, each a
// button that opens where it is set) and the count of unseen messages. The call and the version
// are shown in Settings, not here.
import TagMark from "@/components/TagMark.vue";
import MessageGlyph from "@/components/MessageGlyph.vue";
import { t } from "@/i18n";
import type { HeaderPill, PillTarget } from "@/lib/pills";
import { unreadText } from "@/lib/unread";

defineProps<{
  /** The station call from the settings; null until the daemon has reported it. */
  call: string | null;
  unread: number;
  /** The marks before the count. */
  pills?: readonly HeaderPill[];
}>();
const emit = defineEmits<{ messages: []; setup: []; open: [target: PillTarget, focus: string] }>();

const PROJECT_URL = "https://neo.oh2gba.eu/";
</script>

<template>
  <header class="appheader">
    <h1>
      <a class="brand" :href="PROJECT_URL" target="_blank" rel="noopener" :title="t('header.project_title')"
        >Neo<b>APRS</b></a
      >
    </h1>
    <button v-if="call === ''" type="button" class="nocall" :title="t('header.no_call_title')" @click="emit('setup')">
      {{ t("header.no_call") }}
    </button>
    <span v-if="pills?.length" class="headpills">
      <TagMark
        v-for="pill in pills"
        :key="pill.id"
        :as="pill.target === null ? 'span' : 'button'"
        :tone="pill.tone"
        :class="['headpill', `pill-${pill.id}`, { rxonly: pill.id === 'rx' }]"
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
      <MessageGlyph :size="14" /> {{ unread }}<span class="sr-only"> {{ unreadText(unread) }}</span>
    </TagMark>
  </header>
</template>
